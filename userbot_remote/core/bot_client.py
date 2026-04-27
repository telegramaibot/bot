"""Aiogram bot and dispatcher factories."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from userbot_remote.config.settings import Settings


def create_bot(settings: Settings) -> Bot:
    """Create the aiogram Bot instance."""

    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=None))


def create_dispatcher() -> Dispatcher:
    """Create the aiogram Dispatcher instance."""

    return Dispatcher()
