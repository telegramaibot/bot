"""Ghost mode helpers for lightweight human-like Telegram activity."""

from __future__ import annotations

# === MODIFIED ===

import asyncio
import random

from loguru import logger
from telethon.tl import functions

from userbot_remote.safety.anti_ban import human_delay


async def simulate_typing(client, chat_id, seconds: int | None = None) -> None:
    """Show a typing action in a chat for a short randomized period.

    Args:
        client: Active Telethon client.
        chat_id: Target chat id or entity.
        seconds: Optional explicit duration. If omitted, 2-5 seconds are used.
    """

    duration = seconds if seconds is not None else random.randint(2, 5)
    async with client.action(chat_id, "typing"):
        await asyncio.sleep(max(duration, 1))


async def delayed_read(
    client,
    chat_id,
    min_delay: int = 30,
    max_delay: int = 120,
) -> None:
    """Delay read acknowledgement to reduce automation patterns.

    Args:
        client: Active Telethon client.
        chat_id: Chat id or entity to acknowledge.
        min_delay: Minimum delay in seconds.
        max_delay: Maximum delay in seconds.
    """

    await human_delay(min_delay, max_delay)
    await client.send_read_acknowledge(chat_id)


async def set_online(client, online: bool) -> None:
    """Toggle account online visibility.

    Args:
        client: Active Telethon client.
        online: Desired online flag.
    """

    await client(functions.account.UpdateStatusRequest(offline=not online))


async def random_online(client) -> None:
    """Randomly appear online 3-5 times per day for 5-15 minutes.

    Args:
        client: Active Telethon client.
    """

    while True:
        appearances = random.randint(3, 5)
        for _ in range(appearances):
            wait_hours = random.uniform(3.5, 8.0)
            await asyncio.sleep(wait_hours * 3600)
            duration_minutes = random.randint(5, 15)
            try:
                await set_online(client, True)
                logger.info("Ghost mode: online ko'rinish yoqildi {} minutga.", duration_minutes)
                await asyncio.sleep(duration_minutes * 60)
            finally:
                await set_online(client, False)
