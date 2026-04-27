"""Media download, archive, upload, and voice generation operations."""

from __future__ import annotations

# === MODIFIED ===

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import zipfile

from userbot_remote.plugins.voice_sender import VoiceSender
from userbot_remote.safety.anti_ban import flood_safe, safe_send
from userbot_remote.userbot.contact_ops import resolve_entity
from userbot_remote.utils.helpers import sanitize_filename


@flood_safe
async def download_media(client, message, download_dir: str | Path) -> str:
    """Download media from a message and return the saved file path.

    Args:
        client: Active Telethon client.
        message: Telethon message containing media.
        download_dir: Destination directory.

    Returns:
        Absolute path to the downloaded file.
    """

    target_dir = Path(download_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = await client.download_media(message, file=target_dir)
    if path is None:
        raise ValueError("Media yuklab olinmadi.")
    return str(Path(path).resolve())


async def collect_and_archive(
    client,
    chat,
    media_type: str,
    limit: int,
    download_dir: str | Path,
    archive_dir: str | Path,
) -> str:
    """Collect media files from a chat, archive them, and return a ZIP path.

    Args:
        client: Active Telethon client.
        chat: Source chat identifier.
        media_type: Media filter.
        limit: Max messages to inspect.
        download_dir: Working directory for downloaded files.
        archive_dir: Destination directory for zip archives.

    Returns:
        Absolute path to the generated zip file.
    """

    entity = await resolve_entity(client, chat)
    base_download_dir = Path(download_dir).resolve()
    base_archive_dir = Path(archive_dir).resolve()
    base_download_dir.mkdir(parents=True, exist_ok=True)
    base_archive_dir.mkdir(parents=True, exist_ok=True)

    batch_name = sanitize_filename(f"{getattr(entity, 'title', None) or getattr(entity, 'first_name', 'chat')}_{media_type}")
    batch_dir = base_download_dir / f"{batch_name}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    async for message in client.iter_messages(entity, limit=max(limit, 1)):
        if not _media_matches(message, media_type):
            continue
        path = await download_media(client, message, batch_dir)
        downloaded.append(Path(path))

    if not downloaded:
        raise ValueError("Arxiv uchun mos media topilmadi.")

    archive_path = base_archive_dir / f"{batch_dir.name}.zip"
    await asyncio.to_thread(_zip_directory, batch_dir, archive_path)
    return str(archive_path.resolve())


async def send_voice(client, target, text: str, lang: str = "ru", temp_dir: str | Path = "runtime/temp") -> None:
    """Generate a voice note from text and send it to a target chat.

    Args:
        client: Active Telethon client.
        target: Target entity or identifier.
        text: Source text for TTS.
        lang: Language code.
        temp_dir: Temporary directory for audio files.
    """

    sender = VoiceSender(temp_dir=temp_dir)
    await sender.send_voice(client, target, text=text, lang=lang)


async def send_uploaded_file(
    client,
    target,
    file_path: str | Path,
    caption: str | None = None,
) -> None:
    """Send a file that was uploaded through the control bot.

    Args:
        client: Active Telethon client.
        target: Target entity or identifier.
        file_path: Uploaded file path.
        caption: Optional caption.
    """

    entity = await resolve_entity(client, target)
    await safe_send(client, entity, file=str(Path(file_path).resolve()), caption=caption)


def _media_matches(message, media_type: str) -> bool:
    """Return whether a message matches the requested media type.

    Args:
        message: Telethon message.
        media_type: Desired media type.

    Returns:
        True if the message matches the requested media type.
    """

    normalized = (media_type or "all").lower()
    if normalized == "all":
        return bool(message.media)
    if normalized == "photo":
        return bool(message.photo)
    if normalized == "video":
        return bool(message.video)
    if normalized == "document":
        return bool(message.document)
    if normalized in {"voice", "audio"}:
        return bool(message.voice or message.audio)
    return False


def _zip_directory(source_dir: Path, destination_zip: Path) -> None:
    """Create a ZIP archive from a directory tree.

    Args:
        source_dir: Directory to archive.
        destination_zip: Target zip path.
    """

    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in source_dir.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(source_dir))
