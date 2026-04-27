"""Telethon client factory, authorization flow, and background handlers."""

from __future__ import annotations

# === MODIFIED ===

import asyncio

from loguru import logger
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from userbot_remote.bot.handlers.message_handler import KeywordMonitor
from userbot_remote.config.settings import Settings


async def create_userbot_client(settings: Settings) -> TelegramClient:
    """Create and authorize the Telethon userbot client.

    Args:
        settings: Application settings.

    Returns:
        Authorized Telethon client.
    """

    if settings.session_string:
        try:
            client = TelegramClient(StringSession(settings.session_string), settings.api_id, settings.api_hash)
            logger.info("Using StringSession for Telethon startup.")
        except ValueError:
            logger.warning("SESSION_STRING is set but invalid — falling back to file-based session.")
            session_stem = str(settings.session_path.with_suffix(""))
            client = TelegramClient(session_stem, settings.api_id, settings.api_hash)
    else:
        session_stem = str(settings.session_path.with_suffix(""))
        client = TelegramClient(session_stem, settings.api_id, settings.api_hash)
    await client.connect()
    if await client.is_user_authorized():
        logger.info("Telethon session loaded from {}.", settings.session_path)
        return client

    logger.warning("Telethon session not authorized. Starting interactive login flow.")
    await client.send_code_request(settings.phone_number)
    code = await asyncio.to_thread(input, "Telegram code: ")
    try:
        await client.sign_in(phone=settings.phone_number, code=code.strip())
    except SessionPasswordNeededError:
        password = await asyncio.to_thread(input, "Telegram 2FA password: ")
        await client.sign_in(password=password.strip())
    logger.info("Telethon authorization completed and session saved.")
    return client


def register_monitoring_handlers(client: TelegramClient, monitor: KeywordMonitor) -> None:
    """Register keyword monitoring on the Telethon client.

    Args:
        client: Active Telethon client.
        monitor: Keyword monitor instance.
    """

    @client.on(events.NewMessage(incoming=True))
    async def keyword_monitor(event) -> None:
        """Pass incoming messages to the keyword monitor."""

        try:
            await monitor.check_message(event.message, client)
        except Exception:
            logger.exception("Keyword monitor failed for chat {}.", event.chat_id)
