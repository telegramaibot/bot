"""Message read, send, forward, and search operations."""

from __future__ import annotations

# === MODIFIED ===

from datetime import timedelta

from loguru import logger

from userbot_remote.ai_engine.gemini_client import GeminiClient
from userbot_remote.db.repository import Repository
from userbot_remote.safety.anti_ban import flood_safe, human_delay, safe_forward, safe_send
from userbot_remote.safety.ghost_mode import delayed_read, simulate_typing
from userbot_remote.userbot.contact_ops import resolve_entity
from userbot_remote.utils.helpers import utc_now


async def read_messages(
    client,
    target,
    limit: int,
    repository: Repository | None = None,
    ghost_mode: bool = True,
    min_delay: int = 2,
    max_delay: int = 6,
    read_delay_min: int = 30,
    read_delay_max: int = 120,
) -> list[dict]:
    """Read recent messages from a target chat.

    Args:
        client: Active Telethon client.
        target: Chat identifier.
        limit: Number of recent messages to fetch.
        repository: Optional repository to persist fetched messages.
        ghost_mode: Whether to delay the read acknowledgement.
        min_delay: Minimum send delay in seconds.
        max_delay: Maximum send delay in seconds.
        read_delay_min: Minimum delayed-read seconds.
        read_delay_max: Maximum delayed-read seconds.

    Returns:
        Chronologically ordered list of message dictionaries.
    """

    entity = await resolve_entity(client, target)
    messages: list[dict] = []
    async for message in client.iter_messages(entity, limit=max(limit, 1)):
        sender = await message.get_sender()
        sender_name = _get_sender_name(sender)
        row = {
            "id": message.id,
            "chat_id": entity.id,
            "chat_title": getattr(entity, "title", None) or getattr(entity, "first_name", "") or str(target),
            "sender_id": getattr(sender, "id", None),
            "sender_name": sender_name,
            "text": message.message or "",
            "media_type": _detect_media_type(message),
            "file_path": None,
            "timestamp": message.date.isoformat(),
            "is_from_owner": bool(message.out),
        }
        messages.append(row)
        if repository is not None:
            await repository.save_message(
                message_id=message.id,
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                sender_id=row["sender_id"],
                sender_name=row["sender_name"],
                text=row["text"],
                media_type=row["media_type"],
                file_path=row["file_path"],
                timestamp=row["timestamp"],
                is_from_owner=row["is_from_owner"],
            )
    messages.reverse()
    if ghost_mode:
        await delayed_read(client, entity, min_delay=read_delay_min, max_delay=read_delay_max)
    else:
        await client.send_read_acknowledge(entity)
    return messages


@flood_safe
async def send_message(
    client,
    target,
    text: str,
    delay: bool = True,
    ghost_mode: bool = True,
    min_delay: int = 2,
    max_delay: int = 6,
):
    """Send a text message to a target chat with optional human-like delays."""

    entity = await resolve_entity(client, target)
    if delay:
        await human_delay(min_delay, max_delay)
    if ghost_mode:
        await simulate_typing(client, entity)
    return await safe_send(client, entity, text=text)


@flood_safe
async def forward_messages(client, source, target, limit: int) -> int:
    """Forward the latest messages from one chat to another."""

    source_entity = await resolve_entity(client, source)
    target_entity = await resolve_entity(client, target)
    messages = [message async for message in client.iter_messages(source_entity, limit=max(limit, 1))]
    if not messages:
        return 0
    messages.reverse()
    await safe_forward(client, target_entity, messages)
    return len(messages)


async def search_messages(
    client,
    target,
    keyword: str,
    limit: int = 50,
    repository: Repository | None = None,
) -> list[dict]:
    """Search for keyword matches in a chat history."""

    entity = await resolve_entity(client, target)
    matches: list[dict] = []
    async for message in client.iter_messages(entity, search=keyword, limit=max(limit, 1)):
        sender = await message.get_sender()
        row = {
            "id": message.id,
            "chat_id": entity.id,
            "chat_title": getattr(entity, "title", None) or getattr(entity, "first_name", "") or str(target),
            "sender_id": getattr(sender, "id", None),
            "sender_name": _get_sender_name(sender),
            "text": message.message or "",
            "media_type": _detect_media_type(message),
            "file_path": None,
            "timestamp": message.date.isoformat(),
            "is_from_owner": bool(message.out),
        }
        matches.append(row)
        if repository is not None:
            await repository.save_message(
                message_id=message.id,
                chat_id=row["chat_id"],
                chat_title=row["chat_title"],
                sender_id=row["sender_id"],
                sender_name=row["sender_name"],
                text=row["text"],
                media_type=row["media_type"],
                file_path=row["file_path"],
                timestamp=row["timestamp"],
                is_from_owner=row["is_from_owner"],
            )
    matches.reverse()
    logger.info("Found {} messages for keyword '{}' in '{}'.", len(matches), keyword, target)
    return matches


async def smart_search(client, keyword: str, chats: list | None = None, limit: int = 100) -> list[dict]:
    """Search for a keyword across all or selected chats.

    Args:
        client: Active Telethon client.
        keyword: Search keyword.
        chats: Optional list of target chats.
        limit: Global maximum number of matches.

    Returns:
        List of matching message dictionaries.
    """

    results: list[dict] = []
    chat_targets = chats or [dialog.entity async for dialog in client.iter_dialogs()]
    for chat in chat_targets:
        entity = await resolve_entity(client, chat)
        async for message in client.iter_messages(entity, search=keyword, limit=min(25, limit)):
            sender = await message.get_sender()
            results.append(
                {
                    "id": message.id,
                    "chat_id": entity.id,
                    "chat_title": getattr(entity, "title", None) or getattr(entity, "first_name", "") or str(chat),
                    "sender_id": getattr(sender, "id", None),
                    "sender_name": _get_sender_name(sender),
                    "text": message.message or "",
                    "media_type": _detect_media_type(message),
                    "timestamp": message.date.isoformat(),
                }
            )
            if len(results) >= limit:
                return sorted(results, key=lambda item: item["timestamp"], reverse=True)
    return sorted(results, key=lambda item: item["timestamp"], reverse=True)


async def bulk_forward(client, source, targets: list, limit: int) -> dict:
    """Forward messages from one source chat to multiple targets.

    Args:
        client: Active Telethon client.
        source: Source chat identifier.
        targets: Destination chat identifiers.
        limit: Number of recent messages to forward.

    Returns:
        Mapping of target -> forwarded count or error string.
    """

    result: dict[str, object] = {}
    for target in targets:
        try:
            result[str(target)] = await forward_messages(client, source, target, limit)
        except Exception as exc:
            result[str(target)] = f"xato: {exc}"
    return result


async def get_chat_summary(
    client,
    chat,
    days: int = 7,
    gemini_client: GeminiClient | None = None,
) -> str:
    """Summarize recent chat activity over the last N days.

    Args:
        client: Active Telethon client.
        chat: Target chat.
        days: Number of days to include.
        gemini_client: Optional Gemini wrapper.

    Returns:
        Uzbek chat summary.
    """

    entity = await resolve_entity(client, chat)
    cutoff = utc_now() - timedelta(days=max(days, 1))
    messages: list[dict] = []
    async for message in client.iter_messages(entity, limit=200):
        if message.date < cutoff:
            break
        sender = await message.get_sender()
        messages.append(
            {
                "id": message.id,
                "chat_id": entity.id,
                "chat_title": getattr(entity, "title", None) or getattr(entity, "first_name", "") or str(chat),
                "sender_id": getattr(sender, "id", None),
                "sender_name": _get_sender_name(sender),
                "text": message.message or "",
                "media_type": _detect_media_type(message),
                "timestamp": message.date.isoformat(),
            }
        )
    messages.reverse()
    if not messages:
        return "Ushbu davr uchun xabar topilmadi."
    if gemini_client is not None:
        return await gemini_client.summarize_messages(messages)
    return "\n".join(
        [f"{len(messages)} ta xabar topildi."] + [f"• {item['sender_name']}: {item['text']}" for item in messages[:10]]
    )


def _detect_media_type(message) -> str | None:
    """Infer a human-friendly media type from a Telethon message."""

    if message.voice:
        return "voice"
    if message.audio:
        return "audio"
    if message.video:
        return "video"
    if message.photo:
        return "photo"
    if message.document:
        return "document"
    if message.sticker:
        return "sticker"
    return None


def _get_sender_name(sender) -> str:
    """Create a readable sender label from a Telethon sender entity."""

    if sender is None:
        return "Noma'lum"
    parts = [getattr(sender, "first_name", None), getattr(sender, "last_name", None)]
    full_name = " ".join(part for part in parts if part).strip()
    if full_name:
        return full_name
    return getattr(sender, "username", None) or str(getattr(sender, "id", "Noma'lum"))
