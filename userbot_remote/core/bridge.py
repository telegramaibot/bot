"""Command bridge from aiogram handlers to the userbot executor."""

from __future__ import annotations

# === MODIFIED ===

from aiogram.types import Message

from userbot_remote.bot.command_parser import Command, CommandParser
from userbot_remote.userbot.executor import UserbotExecutor


class CommandBridge:
    """Parse and dispatch control-bot commands."""

    def __init__(self, parser: CommandParser, executor: UserbotExecutor) -> None:
        """Store the parser and executor dependencies."""

        self.parser = parser
        self.executor = executor

    def try_parse(self, raw_text: str) -> Command | None:
        """Attempt to parse a command and return None on failure."""

        try:
            return self.parser.parse(raw_text)
        except ValueError:
            return None

    async def execute_command(self, command: Command, message: Message) -> dict:
        """Execute a parsed command through the userbot executor."""

        return await self.executor.execute(command, message)

    async def send_uploaded_media(
        self,
        message: Message,
        target: str,
        file_path: str,
        caption: str | None = None,
    ) -> dict:
        """Relay a media upload from the bot to the userbot."""

        return await self.executor.send_uploaded_media(message, target=target, file_path=file_path, caption=caption)

    async def analyze_uploaded_file(
        self,
        message: Message,
        file_path: str,
        file_name: str,
        mime_type: str,
        file_size: int,
        question: str | None = None,
    ) -> dict:
        """Ask the executor to analyze an uploaded file."""

        return await self.executor.analyze_uploaded_file(
            message,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            question=question,
        )
