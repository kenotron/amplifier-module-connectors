"""
Amplifier Tool: slack_reply

Allows the agent to proactively post messages to the Slack channel/thread
that initiated the current conversation.

Registration pattern:
1. mount() registers an empty placeholder at bundle load time
2. The bot daemon replaces it with a live instance (with client + channel context)
   after session creation via coordinator.mount("tools", live_tool, name="slack_reply")

The agent sees this tool and can call it to post intermediate updates
or structured content (code blocks, formatted text) independently of the
final session.execute() response.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SlackReplyTool:
    """
    Amplifier Tool: Post a message to the originating Slack thread.

    The agent calls this to send intermediate updates or formatted content.
    The session's final text response is ALSO posted automatically by the
    bot daemon — use this tool when you want to post something BEFORE the
    final response or with different formatting.
    """

    def __init__(
        self,
        client: Any = None,
        channel: str = "",
        thread_ts: str | None = None,
    ) -> None:
        self._client = client
        self._channel = channel
        self._thread_ts = thread_ts

    @property
    def name(self) -> str:
        return "slack_reply"

    @property
    def description(self) -> str:
        return (
            "Post a message to the Slack thread where this conversation started. "
            "Use this for intermediate updates, code blocks, or formatted content "
            "that you want to send BEFORE your final response. "
            "Your final response will be posted automatically — use this tool for "
            "additional messages or when you want finer control over formatting. "
            "Supports Slack mrkdwn: *bold*, _italic_, `code`, ```code block```."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message text. Supports Slack mrkdwn formatting.",
                },
            },
            "required": ["message"],
        }

    async def execute(self, message: str, **kwargs: Any) -> Any:
        """Post a message to the Slack thread."""
        if not self._client:
            return {"success": False, "error": "No Slack client configured (tool not yet initialized)"}

        if not message or not message.strip():
            return {"success": False, "error": "message cannot be empty"}

        try:
            await self._client.chat_postMessage(
                channel=self._channel,
                thread_ts=self._thread_ts,
                text=message,
                unfurl_links=False,
                unfurl_media=False,
            )
            preview = message[:80] + ("..." if len(message) > 80 else "")
            return {"success": True, "output": f"Posted to Slack: {preview}"}
        except Exception as e:
            logger.error(f"slack_reply failed: {e}")
            return {"success": False, "error": str(e)}


async def mount(coordinator: Any, config: dict | None = None) -> None:
    """
    Amplifier module entry point.

    Registers an empty placeholder. The bot daemon replaces this with a
    live instance (with actual client + channel) after session creation:

        live_tool = SlackReplyTool(client=slack_client, channel=channel_id, thread_ts=ts)
        await session.coordinator.mount("tools", live_tool, name="slack_reply")
    """
    tool = SlackReplyTool()  # Empty placeholder — context injected by bot daemon
    await coordinator.mount("tools", tool, name=tool.name)
