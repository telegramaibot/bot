"""Flood protection, owner alerts, and safe Telegram send wrappers."""

from __future__ import annotations

# === MODIFIED ===

import asyncio
from collections import defaultdict, deque
from functools import wraps
from typing import Awaitable, Callable
import random
import time

from loguru import logger
from telethon.errors import ChatAdminRequiredError, FloodWaitError, UserNotParticipantError


OwnerNotifier = Callable[[str], Awaitable[None]]

_CHAT_HOURLY_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_CHAT_WARNING_TIMESTAMPS: dict[str, float] = {}
_OWNER_NOTIFIER: OwnerNotifier | None = None


def configure_safety(notifier: OwnerNotifier | None) -> None:
    """Register a coroutine used for owner-facing safety alerts.

    Args:
        notifier: Async callback that sends a text alert to the owner.
    """

    global _OWNER_NOTIFIER
    _OWNER_NOTIFIER = notifier


async def human_delay(min_seconds: int, max_seconds: int) -> None:
    """Sleep for a randomized amount of time to simulate human pacing.

    Args:
        min_seconds: Minimum delay in seconds.
        max_seconds: Maximum delay in seconds.
    """

    if max_seconds <= 0:
        return
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


def flood_safe(func):
    """Retry a Telethon operation after FloodWait errors with owner alerts."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        retries = 0
        while True:
            try:
                return await func(*args, **kwargs)
            except FloodWaitError as exc:
                retries += 1
                wait_seconds = max(int(exc.seconds), 1)
                logger.warning(
                    "FloodWait in {}. Retry {}/3 after {} seconds.",
                    func.__name__,
                    retries,
                    wait_seconds,
                )
                if retries > 3:
                    await _notify_owner(
                        f"⚠️ FloodWait limit oshdi: {func.__name__} | kutish={wait_seconds}s"
                    )
                    raise
                await asyncio.sleep(wait_seconds + 1)
            except (UserNotParticipantError, ChatAdminRequiredError) as exc:
                await _notify_owner(f"⚠️ Telegram ruxsat xatosi: {func.__name__} | {exc.__class__.__name__}")
                raise

    return wrapper


@flood_safe
async def safe_send(
    client,
    target,
    text: str | None = None,
    file: str | None = None,
    caption: str | None = None,
    voice_note: bool = False,
    reply_to: int | None = None,
):
    """Safely send a message or file with hourly rate limiting.

    Args:
        client: Active Telethon client.
        target: Destination entity or identifier.
        text: Optional message text.
        file: Optional file path.
        caption: Optional file caption.
        voice_note: Whether the file should be sent as a voice note.
        reply_to: Optional reply-to message id.

    Returns:
        Telethon send result.

    Raises:
        RuntimeError: If the hourly per-chat send limit is exceeded.
    """

    chat_key = _chat_key(target)
    await _check_hourly_limit(chat_key)
    if file:
        return await client.send_file(
            target,
            file,
            caption=caption,
            voice_note=voice_note,
            reply_to=reply_to,
        )
    return await client.send_message(target, text or "", reply_to=reply_to)


@flood_safe
async def safe_forward(client, target, messages) -> object:
    """Safely forward messages to a target chat.

    Args:
        client: Active Telethon client.
        target: Destination entity.
        messages: Message or messages to forward.

    Returns:
        Telethon forward result.
    """

    chat_key = _chat_key(target)
    await _check_hourly_limit(chat_key)
    return await client.forward_messages(target, messages)


async def _check_hourly_limit(chat_key: str) -> None:
    """Enforce a maximum of 20 sends per hour per chat.

    Args:
        chat_key: Per-chat rate key.

    Raises:
        RuntimeError: If the chat exceeded its hourly budget.
    """

    bucket = _CHAT_HOURLY_BUCKETS[chat_key]
    now = time.monotonic()
    while bucket and now - bucket[0] > 3600:
        bucket.popleft()

    if len(bucket) >= 20:
        await _notify_owner(f"🚫 Chat '{chat_key}' uchun 20 ta/soat limitga yetildi.")
        raise RuntimeError("Chat uchun soatlik yuborish limiti tugadi.")

    if len(bucket) >= 15:
        last_warning = _CHAT_WARNING_TIMESTAMPS.get(chat_key, 0.0)
        if now - last_warning > 1800:
            _CHAT_WARNING_TIMESTAMPS[chat_key] = now
            await _notify_owner(f"⚠️ Chat '{chat_key}' bo'yicha yuborish limiti yaqinlashmoqda ({len(bucket)}/20).")

    bucket.append(now)


async def _notify_owner(text: str) -> None:
    """Send a best-effort owner alert if a notifier is configured.

    Args:
        text: Alert text.
    """

    if _OWNER_NOTIFIER is None:
        logger.warning("Owner notifier not configured: {}", text)
        return
    try:
        await _OWNER_NOTIFIER(text)
    except Exception:
        logger.exception("Failed to notify owner: {}", text)


def _chat_key(target) -> str:
    """Build a stable rate-limit key for a chat target.

    Args:
        target: Telethon entity or identifier.

    Returns:
        String key representing the target chat.
    """

    target_id = getattr(target, "id", None)
    if target_id is not None:
        return str(target_id)
    return str(target)
