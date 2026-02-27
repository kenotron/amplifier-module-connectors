"""
Protocol boundary implementations for Slack ↔ Amplifier.

These classes implement the Amplifier ApprovalSystem, DisplaySystem,
and StreamingHook protocols with Slack-specific behavior.

References:
- foundation:docs/APPLICATION_INTEGRATION_GUIDE.md
- Slack Bolt: https://slack.dev/bolt-python/
"""
import asyncio
import logging
from typing import Any

from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackApprovalSystem:
    """
    Implements the Amplifier ApprovalSystem protocol using Slack Block Kit buttons.

    When the agent needs human approval (e.g., before a destructive operation),
    this posts an interactive message with Allow/Deny buttons and waits up to
    5 minutes for the user to respond.

    The Slack action handler in bot.py calls resolve() when a button is clicked.
    """

    def __init__(self, client: Any, channel: str, thread_ts: str | None = None) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self._pending: dict[str, asyncio.Future[bool]] = {}

    async def request_approval(
        self,
        description: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Post Block Kit approval buttons and wait for response (max 5 minutes)."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[bool] = loop.create_future()
        action_prefix = f"approval_{id(future)}"
        self._pending[action_prefix] = future

        try:
            await self.client.chat_postMessage(
                channel=self.channel,
                thread_ts=self.thread_ts,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":warning: *Approval needed*\n{description}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Allow"},
                                "action_id": f"{action_prefix}_allow",
                                "style": "primary",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Deny"},
                                "action_id": f"{action_prefix}_deny",
                                "style": "danger",
                            },
                        ],
                    },
                ],
                text=f"Approval needed: {description}",
            )
            return await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            logger.warning("Approval request timed out after 5 minutes — defaulting to deny")
            return False
        except SlackApiError as e:
            logger.error(f"Could not post approval request: {e}")
            return False
        finally:
            self._pending.pop(action_prefix, None)

    def resolve(self, action_id: str, approved: bool) -> None:
        """Called by the bot's action handler when a button is clicked."""
        for suffix in ("_allow", "_deny"):
            if action_id.endswith(suffix):
                prefix = action_id[: -len(suffix)]
                future = self._pending.get(prefix)
                if future and not future.done():
                    future.set_result(approved)
                return


class SlackDisplaySystem:
    """
    Implements the Amplifier DisplaySystem protocol by posting to Slack.

    Used by the orchestrator to display structured output (formatted results,
    code blocks, etc.) during session execution. The agent can also trigger
    this by using the slack_reply tool directly.
    """

    def __init__(self, client: Any, channel: str, thread_ts: str | None = None) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts

    async def display(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        """Post content as a Slack message."""
        try:
            await self.client.chat_postMessage(
                channel=self.channel,
                thread_ts=self.thread_ts,
                text=content,
                unfurl_links=False,
                unfurl_media=False,
            )
        except SlackApiError as e:
            logger.error(f"Could not display content in Slack: {e}")


class SlackStreamingHook:
    """
    Ephemeral hook that shows live tool activity during agent execution.

    Lifecycle:
    1. Call startup() before session.execute() — posts "Thinking..." message
    2. on_tool_start() fires when agent invokes a tool — updates the message
    3. on_tool_end() fires when a tool completes — updates back to "Processing..."
    4. Call cleanup() in finally block — deletes the status message

    Always use in a try/finally:
        hook = SlackStreamingHook(client, channel, thread_ts)
        await hook.startup()
        try:
            response = await session.execute(text)
        finally:
            await hook.cleanup()
    """

    def __init__(self, client: Any, channel: str, thread_ts: str) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self._status_ts: str | None = None

    async def startup(self) -> None:
        """Post the initial thinking indicator."""
        try:
            result = await self.client.chat_postMessage(
                channel=self.channel,
                thread_ts=self.thread_ts,
                text=":thought_balloon: Thinking...",
            )
            self._status_ts = result["ts"]
        except SlackApiError as e:
            logger.debug(f"Could not post streaming indicator: {e}")

    async def on_tool_start(self, event: str, data: dict[str, Any]) -> None:
        """Update status when a tool starts."""
        tool_name = data.get("name", data.get("tool_name", "tool"))
        await self._update(f":gear: Using `{tool_name}`...")

    async def on_tool_end(self, event: str, data: dict[str, Any]) -> None:
        """Update status when a tool finishes."""
        await self._update(":thought_balloon: Processing...")

    async def _update(self, text: str) -> None:
        if not self._status_ts:
            return
        try:
            await self.client.chat_update(
                channel=self.channel,
                ts=self._status_ts,
                text=text,
            )
        except SlackApiError as e:
            logger.debug(f"Could not update streaming indicator: {e}")

    async def cleanup(self) -> None:
        """Delete the status indicator message."""
        if not self._status_ts:
            return
        try:
            await self.client.chat_delete(
                channel=self.channel,
                ts=self._status_ts,
            )
            self._status_ts = None
        except SlackApiError as e:
            logger.debug(f"Could not clean up streaming indicator: {e}")
