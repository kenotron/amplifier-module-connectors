"""
Core bridge: Slack Socket Mode ↔ Amplifier sessions.

Implements Pattern B (Per-Conversation Sessions) from
foundation:docs/APPLICATION_INTEGRATION_GUIDE.md.

Session model:
- PreparedBundle: singleton, loaded ONCE at startup (expensive)
- AmplifierSession: one per Slack channel, lazily created, cached
- asyncio.Lock: one per conversation, ensures ordered execution

Session IDs are stable ("slack-{channel_id}") so sessions persist
across bot restarts when using context-persistent.
"""
import asyncio
import logging
import re
from typing import Any

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackAmplifierBot:
    """
    Bridges Slack Socket Mode to Amplifier sessions.

    Usage:
        bot = SlackAmplifierBot(bundle_path="./bundle.md", ...)
        await bot.run()  # blocks until interrupted
    """

    def __init__(
        self,
        bundle_path: str,
        slack_app_token: str,
        slack_bot_token: str,
        allowed_channel: str | None = None,
    ) -> None:
        self.bundle_path = bundle_path
        self.slack_app_token = slack_app_token
        self.slack_bot_token = slack_bot_token
        self.allowed_channel = allowed_channel

        # Amplifier state
        self.prepared: Any = None
        self.sessions: dict[str, Any] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self._approval_systems: dict[str, Any] = {}  # conv_id -> SlackApprovalSystem

        # Slack state
        self.bolt_app: AsyncApp | None = None
        self.handler: AsyncSocketModeHandler | None = None
        self.bot_user_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load bundle (once) and initialize Slack Bolt app."""
        logger.info(f"Loading Amplifier bundle: {self.bundle_path}")
        try:
            from amplifier_foundation import load_bundle  # type: ignore[import]
            bundle = await load_bundle(self.bundle_path)
            self.prepared = await bundle.prepare()
            logger.info("Amplifier bundle prepared successfully")
        except ImportError as e:
            raise RuntimeError(
                "amplifier-foundation not installed. Install with: uv pip install amplifier-foundation"
            ) from e

        self.bolt_app = AsyncApp(token=self.slack_bot_token)
        self._register_handlers()

        try:
            auth = await self.bolt_app.client.auth_test()
            self.bot_user_id = auth.get("user_id")
            bot_name = auth.get("user", "unknown")
            logger.info(f"Authenticated as @{bot_name} ({self.bot_user_id})")
        except SlackApiError as e:
            logger.warning(f"Could not resolve bot user ID (loop prevention may not work): {e}")

    async def shutdown(self) -> None:
        """Gracefully disconnect and close all Amplifier sessions."""
        logger.info("Shutting down Slack connector...")

        if self.handler:
            try:
                await self.handler.close_async()
            except Exception:
                pass

        for conv_id, session in list(self.sessions.items()):
            try:
                await session.close()
                logger.debug(f"Closed session: {conv_id}")
            except Exception as e:
                logger.warning(f"Error closing session {conv_id}: {e}")

        self.sessions.clear()
        self.locks.clear()
        self._approval_systems.clear()
        logger.info("Shutdown complete")

    async def run(self) -> None:
        """Start the bot and block until stopped."""
        await self.startup()

        channel_info = (
            f" (channel: {self.allowed_channel})"
            if self.allowed_channel
            else " (all channels + @mentions)"
        )
        logger.info(f"Slack connector running{channel_info}")

        self.handler = AsyncSocketModeHandler(
            app=self.bolt_app,
            app_token=self.slack_app_token,
        )

        try:
            await self.handler.start_async()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await self.shutdown()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _conversation_id(self, channel: str, thread_ts: str | None = None) -> str:
        """
        Stable session key. Using only channel_id means the entire channel shares
        one continuous Amplifier conversation (good for a dedicated bot channel).
        Pass thread_ts to isolate each thread as its own conversation.
        """
        if thread_ts:
            return f"slack-{channel}-{thread_ts}"
        return f"slack-{channel}"

    async def _get_or_create_session(
        self,
        channel: str,
        thread_ts: str | None,
        reply_ts: str,
    ) -> tuple[Any, asyncio.Lock]:
        """Lazily create or retrieve the session and lock for a conversation."""
        conv_id = self._conversation_id(channel, thread_ts)

        if conv_id not in self.sessions:
            logger.info(f"Creating new session: {conv_id}")

            from slack_connector.bridge import SlackApprovalSystem, SlackDisplaySystem

            client = self.bolt_app.client
            approval = SlackApprovalSystem(client, channel, reply_ts)
            display = SlackDisplaySystem(client, channel, reply_ts)

            self._approval_systems[conv_id] = approval

            session = await self.prepared.create_session(
                session_id=conv_id,
                approval_system=approval,
                display_system=display,
            )

            # Inject live SlackReplyTool with active client + channel context
            try:
                from tool_slack_reply import SlackReplyTool  # type: ignore[import]
                live_tool = SlackReplyTool(client=client, channel=channel, thread_ts=reply_ts)
                await session.coordinator.mount("tools", live_tool, name="slack_reply")
                logger.debug(f"Mounted slack_reply tool for {conv_id}")
            except Exception as e:
                logger.warning(f"Could not mount slack_reply tool: {e}")

            self.sessions[conv_id] = session
            self.locks[conv_id] = asyncio.Lock()

        return self.sessions[conv_id], self.locks[conv_id]

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def handle_message(
        self,
        channel: str,
        user: str,
        text: str,
        ts: str,
        thread_ts: str | None = None,
    ) -> None:
        """Route a Slack message through an Amplifier session and reply."""
        if not text or not text.strip():
            return

        client = self.bolt_app.client
        # Always reply in a thread (start one if top-level message)
        reply_ts = thread_ts or ts

        session, lock = await self._get_or_create_session(channel, thread_ts, reply_ts)

        # Show loading reaction
        try:
            await client.reactions_add(channel=channel, timestamp=ts, name="loading")
        except SlackApiError:
            pass

        async with lock:
            from slack_connector.bridge import SlackStreamingHook

            stream_hook = SlackStreamingHook(client, channel, reply_ts)
            await stream_hook.startup()

            unreg_pre = None
            unreg_post = None

            try:
                # Register ephemeral streaming hooks (best-effort)
                try:
                    unreg_pre = session.coordinator.hooks.register(
                        "tool:pre", stream_hook.on_tool_start, priority=50
                    )
                    unreg_post = session.coordinator.hooks.register(
                        "tool:post", stream_hook.on_tool_end, priority=50
                    )
                except Exception as e:
                    logger.debug(f"Streaming hooks not available: {e}")

                # Execute through Amplifier
                prompt = f"<@{user}>: {text.strip()}"
                response = await session.execute(prompt)

                # Post the final response
                if response and response.strip():
                    await client.chat_postMessage(
                        channel=channel,
                        thread_ts=reply_ts,
                        text=response,
                        unfurl_links=False,
                        unfurl_media=False,
                    )

            except Exception as e:
                logger.exception(f"Error handling message from {user} in {channel}")
                try:
                    await client.chat_postMessage(
                        channel=channel,
                        thread_ts=reply_ts,
                        text=f":warning: An error occurred: {e}",
                    )
                except SlackApiError:
                    pass

            finally:
                # Unregister ephemeral hooks
                for unreg in (unreg_pre, unreg_post):
                    if unreg is not None:
                        try:
                            unreg()
                        except Exception:
                            pass

                await stream_hook.cleanup()

                try:
                    await client.reactions_remove(channel=channel, timestamp=ts, name="loading")
                except SlackApiError:
                    pass

    # ------------------------------------------------------------------
    # Slack event / action handlers
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        """Register all event and action handlers on self.bolt_app."""
        app = self.bolt_app

        @app.event("message")
        async def on_message(event: dict, say: Any) -> None:
            # Ignore bot messages (prevent infinite loops)
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return
            if self.bot_user_id and event.get("user") == self.bot_user_id:
                return
            # Ignore edits, deletions, file shares, etc.
            if event.get("subtype"):
                return

            channel = event.get("channel", "")

            # If restricted to a specific channel, only respond there
            if self.allowed_channel and channel != self.allowed_channel:
                return

            await self.handle_message(
                channel=channel,
                user=event.get("user", "unknown"),
                text=event.get("text", ""),
                ts=event.get("ts", ""),
                thread_ts=event.get("thread_ts"),
            )

        @app.event("app_mention")
        async def on_mention(event: dict) -> None:
            # @mentions always get a response, regardless of channel restriction
            if event.get("bot_id"):
                return
            await self.handle_message(
                channel=event.get("channel", ""),
                user=event.get("user", "unknown"),
                text=event.get("text", ""),
                ts=event.get("ts", ""),
                thread_ts=event.get("thread_ts"),
            )

        @app.action(re.compile(r"approval_\d+_(allow|deny)"))
        async def on_approval(ack: Any, body: dict) -> None:
            """Handle Block Kit approval button clicks."""
            await ack()
            action = body.get("actions", [{}])[0]
            action_id = action.get("action_id", "")
            approved = action_id.endswith("_allow")

            # Resolve the channel from the action body
            channel = body.get("channel", {}).get("id", "")
            msg_thread_ts = body.get("message", {}).get("thread_ts")
            conv_id = self._conversation_id(channel, msg_thread_ts)

            approval_system = self._approval_systems.get(conv_id)
            if approval_system:
                approval_system.resolve(action_id, approved)

        @app.error
        async def on_error(error: Exception) -> None:
            logger.error(f"Bolt app error: {error}", exc_info=error)
