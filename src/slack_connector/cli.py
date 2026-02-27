"""CLI entry point for the Slack connector daemon."""
import asyncio
import logging
import os
import signal
from pathlib import Path

import click
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """Amplifier Slack Connector — bridges Slack messages to Amplifier sessions."""


@cli.command()
@click.option("--bundle", default=None, help="Path to bundle.md (default: <repo root>/bundle.md)")
@click.option("--channel", default=None, help="Slack channel ID to watch (overrides .env)")
@click.option("--env-file", default=".env", show_default=True, help="Path to .env file")
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
def start(bundle: str | None, channel: str | None, env_file: str, debug: bool) -> None:
    """Start the Slack connector bot daemon."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("slack_bolt").setLevel(logging.DEBUG)

    load_dotenv(env_file)

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")

    if not bot_token:
        raise click.ClickException("SLACK_BOT_TOKEN not set. Check your .env file.")
    if not app_token:
        raise click.ClickException("SLACK_APP_TOKEN not set. Check your .env file.")

    bundle_path = bundle or str(Path(__file__).parent.parent.parent / "bundle.md")
    allowed_channel = channel or os.environ.get("SLACK_CHANNEL_ID")

    if not Path(bundle_path).exists():
        raise click.ClickException(f"Bundle not found: {bundle_path}")

    from slack_connector.bot import SlackAmplifierBot

    bot = SlackAmplifierBot(
        bundle_path=bundle_path,
        slack_app_token=app_token,
        slack_bot_token=bot_token,
        allowed_channel=allowed_channel,
    )

    async def run() -> None:
        loop = asyncio.get_event_loop()

        def _shutdown(*_) -> None:
            logger.info("Received shutdown signal")
            for task in asyncio.all_tasks(loop):
                task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _shutdown)

        await bot.run()

    channel_info = f" (channel: {allowed_channel})" if allowed_channel else " (all channels + @mentions)"
    click.echo(f"Starting Amplifier Slack connector{channel_info}")
    click.echo(f"Bundle: {bundle_path}")
    click.echo("Press Ctrl+C to stop.")

    asyncio.run(run())


def main() -> None:
    cli()
