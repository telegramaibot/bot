"""Application entrypoint that runs the Telethon userbot and aiogram control bot."""

from __future__ import annotations

# === MODIFIED ===

import asyncio
from contextlib import suppress

from loguru import logger

from userbot_remote.ai_engine.gemini_client import GeminiClient
from userbot_remote.auth.auth_manager import AuthManager
from userbot_remote.bot.command_parser import CommandParser
from userbot_remote.bot.handlers.admin_handler import build_admin_router
from userbot_remote.bot.handlers.auth_handler import build_auth_router
from userbot_remote.bot.handlers.cmd_handler import build_command_router
from userbot_remote.bot.handlers.media_handler import build_media_router
from userbot_remote.bot.handlers.message_handler import KeywordMonitor
from userbot_remote.bot.middlewares import AuthMiddleware
from userbot_remote.config.settings import get_settings
from userbot_remote.core.bot_client import create_bot, create_dispatcher
from userbot_remote.core.bridge import CommandBridge
from userbot_remote.core.scheduler import create_scheduler
from userbot_remote.core.userbot_client import create_userbot_client, register_monitoring_handlers
from userbot_remote.db.database import Database
from userbot_remote.db.repository import Repository
from userbot_remote.plugins.daily_logger import DailyLogger
from userbot_remote.plugins.smart_scheduler import SmartScheduler
from userbot_remote.plugins.voice_sender import VoiceSender
from userbot_remote.safety.anti_ban import configure_safety
from userbot_remote.safety.ghost_mode import random_online
from userbot_remote.userbot.executor import UserbotExecutor
from userbot_remote.utils.logger import setup_logger


async def main() -> None:
    """Initialize dependencies and run both Telegram clients concurrently."""

    settings = get_settings()
    setup_logger(settings)
    logger.info("Starting Telegram remote userbot service.")

    database = Database(settings.database_path)
    await database.init()
    repository = Repository(database)

    auth_manager = AuthManager(repository, settings)
    await auth_manager.ensure_admin_user()

    userbot_client = await create_userbot_client(settings)
    bot = create_bot(settings)
    dispatcher = create_dispatcher()
    scheduler = create_scheduler()

    gemini_client = GeminiClient(settings.gemini_api_key, settings.gemini_model)
    voice_sender = VoiceSender(settings.temp_dir)
    smart_scheduler = SmartScheduler(repository, userbot_client, settings, voice_sender)
    daily_logger = DailyLogger(repository, userbot_client, settings, gemini_client)
    keyword_monitor = KeywordMonitor(repository, gemini_client, bot, settings, settings.temp_dir)
    executor = UserbotExecutor(
        userbot_client,
        repository,
        settings,
        smart_scheduler,
        gemini_client,
        daily_logger,
        keyword_monitor,
        voice_sender,
    )
    parser = CommandParser(settings.command_prefix)
    bridge = CommandBridge(parser, executor)

    async def owner_notifier(text: str) -> None:
        """Deliver internal alerts to the owner and to the log channel."""

        await bot.send_message(settings.owner_id, text)
        if settings.log_channel_id and settings.log_channel_id != settings.owner_id:
            try:
                await bot.send_message(settings.log_channel_id, text)
            except Exception:
                pass

    auth_manager.set_owner_notifier(owner_notifier)
    configure_safety(owner_notifier)

    dispatcher.message.outer_middleware(AuthMiddleware(auth_manager, settings))
    dispatcher.callback_query.outer_middleware(AuthMiddleware(auth_manager, settings))

    dispatcher.include_router(build_auth_router(auth_manager, settings))
    dispatcher.include_router(build_admin_router(auth_manager, parser, settings))
    dispatcher.include_router(build_media_router(bridge, parser, settings))
    dispatcher.include_router(build_command_router(bridge, settings))

    scheduler.add_job(
        smart_scheduler.execute_pending,
        trigger="interval",
        seconds=60,
        args=[userbot_client],
        id="scheduled_task_runner",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        daily_logger.post_report,
        trigger="cron",
        hour=23,
        minute=0,
        args=[userbot_client],
        id="daily_log_job",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    await smart_scheduler.execute_pending(userbot_client)
    scheduler.start()

    register_monitoring_handlers(userbot_client, keyword_monitor)
    ghost_task = None
    if settings.ghost_mode:
        ghost_task = asyncio.create_task(random_online(userbot_client))

    logger.info(
        "Startup complete. Owner id={}, DB={}, session={}",
        settings.owner_id,
        settings.database_path,
        settings.session_path,
    )

    try:
        await asyncio.gather(
            userbot_client.run_until_disconnected(),
            dispatcher.start_polling(bot),
        )
    finally:
        if ghost_task is not None:
            ghost_task.cancel()
            with suppress(asyncio.CancelledError):
                await ghost_task
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await dispatcher.storage.close()
        await bot.session.close()
        with suppress(Exception):
            await userbot_client.disconnect()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
