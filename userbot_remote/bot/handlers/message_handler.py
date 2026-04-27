"""Incoming message monitor used by the Telethon userbot."""

from __future__ import annotations

# === NEW CODE ===

import asyncio
from pathlib import Path

from aiogram import Bot
from loguru import logger

from userbot_remote.ai_engine.gemini_client import GeminiClient
from userbot_remote.config.settings import Settings
from userbot_remote.db.repository import Repository
from userbot_remote.userbot.media_ops import download_media
from userbot_remote.utils.helpers import chunk_text


class KeywordMonitor:
    """Watch incoming Telegram messages and alert on important keywords."""

    def __init__(
        self,
        repository: Repository,
        gemini_client: GeminiClient,
        bot: Bot,
        settings: Settings,
        temp_dir: str | Path,
    ) -> None:
        """Store dependencies used by the monitor.

        Args:
            repository: Shared repository.
            gemini_client: Gemini analysis wrapper.
            bot: Aiogram control bot.
            settings: Application settings.
            temp_dir: Temporary directory for downloaded files.
        """

        self.repository = repository
        self.gemini_client = gemini_client
        self.bot = bot
        self.settings = settings
        self.temp_dir = Path(temp_dir).resolve()
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._keywords = list(settings.monitor_keywords)

    async def check_message(self, message, client) -> None:
        """Inspect an incoming message and send a briefing when needed.

        Args:
            message: Telethon incoming message.
            client: Active Telethon client.
        """

        chat = await message.get_chat()
        sender = await message.get_sender()
        chat_title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(message.chat_id)
        sender_name = " ".join(
            part for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if part
        ).strip() or getattr(sender, "username", None) or "Noma'lum"

        await self.repository.save_message(
            message_id=message.id,
            chat_id=message.chat_id or 0,
            chat_title=chat_title,
            sender_id=getattr(sender, "id", None),
            sender_name=sender_name,
            text=message.message or "",
            media_type=self._detect_media_type(message),
            file_path=None,
            timestamp=message.date.isoformat(),
            is_from_owner=bool(message.out),
        )

        text = (message.raw_text or "").strip()
        if not text:
            return

        keyword = self._match_keyword(text)
        if keyword is None:
            return

        if await self.repository.monitor_log_exists(message.chat_id or 0, message.id, keyword):
            return

        context_messages = await self._fetch_context_messages(client, chat, limit=10)
        context_summary = await self.gemini_client.summarize_messages(context_messages)

        downloaded_path: str | None = None
        try:
            file_analysis = ""
            if message.media:
                downloaded_path = await download_media(client, message, self.temp_dir)
                mime_type = getattr(getattr(message, "file", None), "mime_type", None)
                file_analysis = await self.gemini_client.analyze_file(
                    downloaded_path,
                    mime_type,
                    "Ushbu biriktirma va suhbat konteksti asosida asosiy ma'lumotlarni ajratib bering.",
                )

            summary = context_summary
            if file_analysis:
                summary = await self.gemini_client.analyze_text(
                    "\n\n".join(
                        [
                            f"Chat: {chat_title}",
                            f"Kalit so'z: {keyword}",
                            f"Kontekst: {context_summary}",
                            f"Fayl tahlili: {file_analysis}",
                        ]
                    )
                )

            alert = "\n".join(
                [
                    f"📌 Manba: {chat_title}",
                    f"🕐 Vaqt: {message.date.isoformat().replace('T', ' ')}",
                    f"🔑 Kalit so'z: {keyword}",
                    "📋 Xulosa:",
                    summary,
                ]
            )

            if self.settings.log_channel_id is not None:
                for chunk in chunk_text(alert):
                    await self.bot.send_message(self.settings.log_channel_id, chunk)

            await self.repository.save_monitor_log(
                chat_id=message.chat_id or 0,
                message_id=message.id,
                chat_title=chat_title,
                keyword=keyword,
                message_text=text,
                summary=summary,
                file_path=downloaded_path,
            )
            await self.repository.save_command_log("monitor_briefing", self.settings.owner_id, "ok", keyword)
            logger.info("Keyword '{}' detected in chat '{}'.", keyword, chat_title)
        finally:
            if downloaded_path is not None:
                await asyncio.to_thread(self._cleanup_file, downloaded_path)

    def update_keywords(self, raw_words: str) -> list[str]:
        """Update in-memory monitor keywords at runtime.

        Args:
            raw_words: Comma- or space-separated keywords.

        Returns:
            Updated keyword list.
        """

        if "," in raw_words:
            items = [item.strip().lower() for item in raw_words.split(",") if item.strip()]
        else:
            items = [item.strip().lower() for item in raw_words.split() if item.strip()]
        if not items:
            raise ValueError("Kamida bitta kalit so'z kiriting.")
        self._keywords = items
        self.settings.monitor_keywords = items
        return list(self._keywords)

    def get_keywords(self) -> list[str]:
        """Return the active runtime keyword list."""

        return list(self._keywords)

    async def _fetch_context_messages(self, client, chat, limit: int = 10) -> list[dict]:
        """Fetch recent messages from a chat for AI context.

        Args:
            client: Active Telethon client.
            chat: Telethon chat entity.
            limit: Number of messages to fetch.

        Returns:
            Chronologically ordered message dictionaries.
        """

        messages: list[dict] = []
        async for item in client.iter_messages(chat, limit=max(limit, 1)):
            sender = await item.get_sender()
            sender_name = " ".join(
                part for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if part
            ).strip() or getattr(sender, "username", None) or "Noma'lum"
            messages.append(
                {
                    "id": item.id,
                    "chat_id": getattr(chat, "id", 0),
                    "chat_title": getattr(chat, "title", None) or getattr(chat, "first_name", None) or "Chat",
                    "sender_id": getattr(sender, "id", None),
                    "sender_name": sender_name,
                    "text": item.message or "",
                    "media_type": self._detect_media_type(item),
                    "timestamp": item.date.isoformat(),
                }
            )
        messages.reverse()
        return messages

    def _match_keyword(self, text: str) -> str | None:
        """Find the first configured keyword present in a message."""

        lowered = text.lower()
        for keyword in self._keywords:
            if keyword in lowered:
                return keyword
        return None

    @staticmethod
    def _detect_media_type(message) -> str | None:
        """Infer a simple media type string for a Telethon message."""

        if message.photo:
            return "photo"
        if message.video:
            return "video"
        if message.voice:
            return "voice"
        if message.audio:
            return "audio"
        if message.document:
            return "document"
        return None

    @staticmethod
    def _cleanup_file(path: str) -> None:
        """Delete a temporary file if it exists.

        Args:
            path: File path string.
        """

        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
