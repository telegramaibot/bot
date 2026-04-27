"""Handlers for media uploads routed through the control bot."""

from __future__ import annotations

# === MODIFIED ===

from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message

from userbot_remote.bot.command_parser import CommandParser
from userbot_remote.config.settings import Settings
from userbot_remote.core.bridge import CommandBridge
from userbot_remote.utils.helpers import sanitize_filename


def build_media_router(bridge: CommandBridge, parser: CommandParser, settings: Settings) -> Router:
    """Create the media upload router."""

    router = Router(name="media")

    @router.message(F.caption)
    async def media_upload_handler(message: Message) -> None:
        """Download uploaded bot media and either send or analyze it."""

        if not _has_supported_media(message):
            return
        caption = (message.caption or "").strip()
        if not caption.startswith(settings.command_prefix):
            return
        try:
            command = parser.parse(caption)
        except ValueError:
            await message.answer("❌ Caption formati noto'g'ri.")
            return

        file_id, file_name, mime_type, file_size = _extract_file_meta(message)
        if file_id is None or file_name is None:
            await message.answer("❌ Media aniqlanmadi.")
            return

        temp_dir = Path("/tmp/userbot_remote")
        temp_dir.mkdir(parents=True, exist_ok=True)
        tg_file = await message.bot.get_file(file_id)
        destination = temp_dir / file_name
        await message.bot.download_file(tg_file.file_path, destination=destination)
        if command.action == "send_message":
            await bridge.send_uploaded_media(
                message,
                target=command.target or "",
                file_path=str(destination),
                caption=command.text,
            )
            return

        if command.action == "analyze_file":
            await bridge.analyze_uploaded_file(
                message,
                file_path=str(destination),
                file_name=file_name,
                mime_type=mime_type or "application/octet-stream",
                file_size=file_size,
                question=command.text,
            )
            return

        if destination.exists():
            destination.unlink()
        await message.answer("❌ Media uchun faqat .yubor yoki .tahlil buyrug'i ishlaydi.")

    return router


def _has_supported_media(message: Message) -> bool:
    """Check whether a message contains a supported file payload."""

    return any([message.document, message.photo, message.video, message.audio, message.voice])


def _extract_file_meta(message: Message) -> tuple[str | None, str | None, str | None, int]:
    """Extract file id, safe filename, mime type, and size from a message."""

    if message.document:
        name = sanitize_filename(message.document.file_name or f"document_{message.document.file_unique_id}")
        return (
            message.document.file_id,
            name,
            message.document.mime_type,
            message.document.file_size or 0,
        )
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, f"photo_{photo.file_unique_id}.jpg", "image/jpeg", photo.file_size or 0
    if message.video:
        name = sanitize_filename(message.video.file_name or f"video_{message.video.file_unique_id}.mp4")
        return message.video.file_id, name, message.video.mime_type, message.video.file_size or 0
    if message.audio:
        name = sanitize_filename(message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3")
        return message.audio.file_id, name, message.audio.mime_type, message.audio.file_size or 0
    if message.voice:
        return message.voice.file_id, f"voice_{message.voice.file_unique_id}.ogg", "audio/ogg", message.voice.file_size or 0
    return None, None, None, 0
