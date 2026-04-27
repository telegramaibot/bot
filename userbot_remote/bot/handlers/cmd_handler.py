"""Standard command handlers that bridge bot commands to the userbot."""

from __future__ import annotations

# === MODIFIED ===

from aiogram import F, Router
from aiogram.types import Message

from userbot_remote.bot.command_parser import ADMIN_ACTIONS
from userbot_remote.bot.responses import command_help
from userbot_remote.config.settings import Settings
from userbot_remote.core.bridge import CommandBridge


def build_command_router(bridge: CommandBridge, settings: Settings) -> Router:
    """Create the main command router."""

    router = Router(name="commands")

    @router.message(F.text)
    async def command_handler(message: Message) -> None:
        """Parse and execute non-admin prefixed commands."""

        text = (message.text or "").strip()
        if not text.startswith(settings.command_prefix):
            return

        command = bridge.try_parse(text)
        if command is None:
            await message.answer(command_help(settings.command_prefix))
            return

        if command.action in ADMIN_ACTIONS:
            return

        if command.action == "help":
            await message.answer(command_help(settings.command_prefix))
            return

        await bridge.execute_command(command, message)

    return router
