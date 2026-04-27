"""Central dispatcher for control-bot commands executed on the user account."""

from __future__ import annotations

# === MODIFIED ===

import asyncio
from pathlib import Path

from aiogram.types import FSInputFile, Message
from loguru import logger
from telethon.errors import ChatAdminRequiredError, UserNotParticipantError

from userbot_remote.ai_engine.gemini_client import GeminiClient
from userbot_remote.bot.handlers.message_handler import KeywordMonitor
from userbot_remote.config.settings import Settings
from userbot_remote.db.repository import Repository
from userbot_remote.plugins.daily_logger import DailyLogger
from userbot_remote.plugins.smart_scheduler import SmartScheduler
from userbot_remote.plugins.voice_sender import VoiceSender
from userbot_remote.userbot.channel_ops import create_channel, create_group, get_channel_info, post_to_channel
from userbot_remote.userbot.chat_ops import (
    forward_messages,
    get_chat_summary,
    read_messages,
    search_messages,
    send_message,
    smart_search,
)
from userbot_remote.userbot.contact_ops import get_all_dialogs
from userbot_remote.userbot.media_ops import collect_and_archive, send_uploaded_file
from userbot_remote.utils.formatters import format_dialogs, format_messages, format_search_results
from userbot_remote.utils.helpers import chunk_text


class UserbotExecutor:
    """Execute parsed bot commands against the Telethon userbot client."""

    def __init__(
        self,
        client,
        repository: Repository,
        settings: Settings,
        scheduler_plugin: SmartScheduler,
        gemini_client: GeminiClient,
        daily_logger: DailyLogger,
        keyword_monitor: KeywordMonitor,
        voice_sender: VoiceSender,
    ) -> None:
        """Store dependencies for command execution."""

        self.client = client
        self.repository = repository
        self.settings = settings
        self.scheduler_plugin = scheduler_plugin
        self.gemini_client = gemini_client
        self.daily_logger = daily_logger
        self.keyword_monitor = keyword_monitor
        self.voice_sender = voice_sender

    async def execute(self, command, bot_event: Message) -> dict:
        """Execute a parsed command and notify the control-bot user."""

        status_message = await bot_event.answer("⏳ Bajarilmoqda...")
        telegram_id = bot_event.from_user.id if bot_event.from_user else None
        try:
            result_text = await self._execute_command(command, bot_event)
            await self._respond(status_message, result_text)
            await self.repository.save_command_log(command.action, telegram_id, "ok", result_text[:1000])
            return {"status": "ok", "details": result_text}
        except (UserNotParticipantError, ChatAdminRequiredError) as exc:
            error_text = f"❌ Telegram ruxsat xatosi: {exc.__class__.__name__}"
            await self._respond(status_message, error_text)
            await self.repository.save_command_log(command.action, telegram_id, "error", error_text)
            return {"status": "error", "details": error_text}
        except Exception as exc:
            logger.exception("Command execution failed for action '{}'.", command.action)
            error_text = f"❌ Xato: {exc}"
            await self._respond(status_message, error_text)
            await self.repository.save_command_log(command.action, telegram_id, "error", error_text)
            return {"status": "error", "details": error_text}

    async def send_uploaded_media(
        self,
        bot_event: Message,
        target: str,
        file_path: str,
        caption: str | None = None,
    ) -> dict:
        """Send a previously uploaded file from the control bot to Telegram."""

        status_message = await bot_event.answer("⏳ Bajarilmoqda...")
        try:
            await send_uploaded_file(self.client, target=target, file_path=file_path, caption=caption)
            result_text = f"✅ Fayl '{target}' chatiga yuborildi."
            await self._respond(status_message, result_text)
            await self.repository.save_command_log("send_message", bot_event.from_user.id, "ok", result_text)
            return {"status": "ok", "details": result_text}
        except Exception as exc:
            logger.exception("Failed to send uploaded media to '{}'.", target)
            error_text = f"❌ Media yuborishda xato: {exc}"
            await self._respond(status_message, error_text)
            await self.repository.save_command_log("send_message", bot_event.from_user.id, "error", error_text)
            return {"status": "error", "details": error_text}
        finally:
            await asyncio.to_thread(self._cleanup_temp_file, file_path)

    async def analyze_uploaded_file(
        self,
        bot_event: Message,
        file_path: str,
        file_name: str,
        mime_type: str,
        file_size: int,
        question: str | None = None,
    ) -> dict:
        """Analyze an uploaded file with Gemini and return a formatted response."""

        status_message = await bot_event.answer("⏳ Bajarilmoqda...")
        file_kind = self._classify_file_kind(file_name=file_name, mime_type=mime_type)
        try:
            if file_kind == "audio":
                result_text = (
                    f"📎 Fayl: {file_name} ({self._format_bytes(file_size)})\n"
                    f"📋 Tur: {file_kind}\n"
                    "❌ Audio tahlili hozircha qo'llab-quvvatlanmaydi."
                )
            else:
                analysis = await self.gemini_client.analyze_file(
                    file_path=file_path,
                    mime_type=mime_type,
                    question=question or "Fayldagi asosiy ma'lumotlar, raqamlar va amaliy tavsiyalarni yozing.",
                )
                result_text = "\n".join(
                    [
                        f"📎 Fayl: {file_name} ({self._format_bytes(file_size)})",
                        f"📋 Tur: {file_kind}",
                        "🔑 Asosiy ma'lumotlar:",
                        analysis,
                        "✅ Tavsiya: yuqoridagi muhim nuqtalar asosida keyingi amaliy qadamlarni belgilang.",
                    ]
                )
            await self._respond(status_message, result_text)
            await self.repository.save_command_log("analyze_file", bot_event.from_user.id, "ok", result_text[:1000])
            return {"status": "ok", "details": result_text}
        except Exception as exc:
            logger.exception("Failed to analyze uploaded file '{}'.", file_name)
            error_text = f"❌ Xato: {exc}"
            await self._respond(status_message, error_text)
            await self.repository.save_command_log("analyze_file", bot_event.from_user.id, "error", error_text)
            return {"status": "error", "details": error_text}
        finally:
            await asyncio.to_thread(self._cleanup_temp_file, file_path)

    async def _execute_command(self, command, bot_event: Message) -> str:
        """Route command execution to the correct userbot operation."""

        if command.action == "read":
            messages = await read_messages(
                self.client,
                target=command.target,
                limit=command.count or 5,
                repository=self.repository,
                ghost_mode=self.settings.ghost_mode,
                min_delay=self.settings.min_delay,
                max_delay=self.settings.max_delay,
                read_delay_min=self.settings.read_delay_min,
                read_delay_max=self.settings.read_delay_max,
            )
            return f"✅ Oxirgi xabarlar:\n{format_messages(messages)}"

        if command.action == "read_and_voice":
            messages = await read_messages(
                self.client,
                target=command.target,
                limit=command.count or 5,
                repository=self.repository,
                ghost_mode=self.settings.ghost_mode,
                min_delay=self.settings.min_delay,
                max_delay=self.settings.max_delay,
                read_delay_min=self.settings.read_delay_min,
                read_delay_max=self.settings.read_delay_max,
            )
            await self.voice_sender.send_voice(self.client, command.target, command.text or "")
            return (
                f"✅ Xabarlar o'qildi va ovoz yuborildi:\n"
                f"{format_messages(messages)}\n\n"
                f"🎤 Matn: {command.text}"
            )

        if command.action == "send_message":
            await send_message(
                self.client,
                target=command.target,
                text=command.text or "",
                delay=True,
                ghost_mode=self.settings.ghost_mode,
                min_delay=self.settings.min_delay,
                max_delay=self.settings.max_delay,
            )
            return f"✅ Xabar yuborildi: {command.target}"

        if command.action == "forward":
            forwarded = await forward_messages(
                self.client,
                source=command.target,
                target=command.text,
                limit=command.count or 1,
            )
            return f"✅ Forward qilindi: {forwarded} ta xabar."

        if command.action == "voice":
            await self.voice_sender.send_voice(self.client, command.target, command.text or "")
            return f"✅ Ovozli xabar yuborildi: {command.target}"

        if command.action == "archive":
            archive_path = await collect_and_archive(
                self.client,
                chat=command.target,
                media_type=command.media_type or "all",
                limit=command.count or 50,
                download_dir=self.settings.media_dir,
                archive_dir=self.settings.archive_dir,
            )
            await bot_event.answer_document(FSInputFile(archive_path), caption=f"✅ Arxiv tayyor: {command.target}")
            return f"✅ Arxiv yaratildi: {archive_path}"

        if command.action == "create_channel":
            entity = await create_channel(self.client, title=command.target or "New Channel")
            info = await get_channel_info(self.client, entity)
            return f"✅ Kanal yaratildi: {info['title']} (id={info['id']})"

        if command.action == "create_group":
            entity = await create_group(self.client, title=command.target or "New Group")
            info = await get_channel_info(self.client, entity)
            return f"✅ Guruh yaratildi: {info['title']} (id={info['id']})"

        if command.action == "log":
            await self.daily_logger.write_manual(self.client, command.text or "")
            return "✅ Kunlik logga yozildi."

        if command.action == "schedule":
            task_id = await self.scheduler_plugin.schedule_message(
                self.client,
                target=command.target or "",
                text=command.text or "",
                run_at=command.schedule_time,
                voice=False,
            )
            return f"✅ Xabar rejalashtirildi: task_id={task_id}"

        if command.action == "schedule_list":
            tasks = await self.scheduler_plugin.list_tasks()
            if not tasks:
                return "Rejalashtirilgan vazifalar yo'q."
            return "\n".join(
                [
                    "✅ Faol vazifalar:",
                    *[
                        f"• ID={task['id']} | {task['task_type']} | status={task['status']} | run_at={task['run_at']}"
                        for task in tasks
                    ],
                ]
            )

        if command.action == "schedule_cancel":
            cancelled = await self.scheduler_plugin.cancel_task(int(command.target or "0"))
            return "✅ Vazifa bekor qilindi." if cancelled else "❌ Vazifa topilmadi yoki allaqachon tugagan."

        if command.action == "search":
            matches = await search_messages(
                self.client,
                target=command.target,
                keyword=command.text or "",
                repository=self.repository,
            )
            return f"✅ Qidiruv natijasi:\n{format_search_results(matches, command.text or '')}"

        if command.action == "global_search":
            chats = [command.target] if command.target else None
            matches = await smart_search(self.client, keyword=command.text or "", chats=chats, limit=30)
            if not matches:
                return "Hech narsa topilmadi."
            lines = ["✅ Qidiruv natijalari:"]
            for item in matches[:20]:
                lines.append(f"• {item['chat_title']} | {item['sender_name']}: {item['text']}")
            return "\n".join(lines)

        if command.action == "list_chats":
            dialogs = await get_all_dialogs(self.client)
            return f"✅ Chatlar ro'yxati:\n{format_dialogs(dialogs)}"

        if command.action == "post_to_channel":
            await post_to_channel(self.client, channel=command.target, text=command.text or "")
            return f"✅ Kanalga post yuborildi: {command.target}"

        if command.action == "brief":
            summary = await get_chat_summary(
                self.client,
                chat=command.target,
                days=2,
                gemini_client=self.gemini_client,
            )
            return f"✅ Briefing:\n{summary}"

        if command.action == "translate":
            translated = await self.gemini_client.translate(command.text or "", target_lang="uz")
            return f"✅ Tarjima:\n{translated}"

        if command.action == "analyze_file":
            return "❌ Ushbu buyruq uchun faylni botga biriktirib yuboring va caption sifatida .tahlil yozing."

        if command.action == "daily_report_now":
            report = await self.daily_logger.generate_report(self.client)
            return report

        if command.action == "update_keywords":
            keywords = self.keyword_monitor.update_keywords(command.text or "")
            return f"✅ Kalit so'zlar yangilandi: {', '.join(keywords)}"

        if command.action == "show_keywords":
            return f"✅ Joriy kalit so'zlar: {', '.join(self.keyword_monitor.get_keywords())}"

        if command.action == "chat_summary":
            summary = await get_chat_summary(
                self.client,
                chat=command.target,
                days=command.count or 7,
                gemini_client=self.gemini_client,
            )
            return f"✅ Chat xulosasi:\n{summary}"

        raise ValueError(f"Noma'lum action: {command.action}")

    async def _respond(self, status_message: Message, text: str) -> None:
        """Edit the status message and send extra chunks when needed."""

        chunks = chunk_text(text)
        if not chunks:
            chunks = ["✅ Bajarildi."]
        await status_message.edit_text(chunks[0])
        for chunk in chunks[1:]:
            await status_message.answer(chunk)

    @staticmethod
    def _cleanup_temp_file(path: str) -> None:
        """Delete a temporary file if it still exists."""

        temp_path = Path(path)
        if temp_path.exists():
            temp_path.unlink()

    @staticmethod
    def _classify_file_kind(file_name: str, mime_type: str) -> str:
        """Map a file into a human-readable media category."""

        lowered_name = file_name.lower()
        lowered_mime = (mime_type or "").lower()
        if lowered_mime.startswith("image/") or lowered_name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return "image"
        if lowered_mime in {"application/pdf"} or lowered_name.endswith(".pdf"):
            return "pdf"
        if lowered_name.endswith((".xlsx", ".xls")) or "sheet" in lowered_mime or "excel" in lowered_mime:
            return "excel"
        if lowered_name.endswith(".csv") or lowered_mime == "text/csv":
            return "csv"
        if lowered_mime.startswith("video/"):
            return "video"
        if lowered_mime.startswith("audio/"):
            return "audio"
        return "document"

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Convert bytes into a compact human-readable string."""

        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}"
            value /= 1024
