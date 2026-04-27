"""Authentication handlers for the control bot."""

from __future__ import annotations

# === MODIFIED ===

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from userbot_remote.auth.auth_manager import AuthManager
from userbot_remote.bot.responses import (
    auth_failed_message,
    auth_success_message,
    command_help,
    login_prompt,
    logout_message,
)
from userbot_remote.config.settings import Settings
from userbot_remote.utils.helpers import is_login_payload, parse_login_payload


def build_auth_router(auth_manager: AuthManager, settings: Settings) -> Router:
    """Create and return the authentication router."""

    router = Router(name="auth")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        """Handle `/start` requests for both owner and regular users."""

        telegram_id = message.from_user.id
        if telegram_id == settings.owner_id or await auth_manager.is_authenticated(telegram_id):
            await message.answer(command_help(settings.command_prefix))
            return
        await message.answer(login_prompt())

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        """Handle `/help` requests."""

        telegram_id = message.from_user.id
        if telegram_id == settings.owner_id or await auth_manager.is_authenticated(telegram_id):
            await message.answer(command_help(settings.command_prefix))
            return
        await message.answer(login_prompt())

    @router.message(Command("logout"))
    async def logout_handler(message: Message) -> None:
        """Revoke the caller's active session."""

        telegram_id = message.from_user.id
        if telegram_id != settings.owner_id:
            await auth_manager.revoke_session(telegram_id)
        await message.answer(logout_message())

    @router.message(F.text)
    async def credential_handler(message: Message) -> None:
        """Handle credential payloads for unauthenticated users."""

        if not is_login_payload(message.text):
            return
        if message.from_user.id == settings.owner_id:
            await message.answer(command_help(settings.command_prefix))
            return
        login, password = parse_login_payload(message.text)
        client_info = (
            f"user={message.from_user.username or 'no_username'}|"
            f"lang={message.from_user.language_code or 'unknown'}"
        )
        token = await auth_manager.authenticate(
            message.from_user.id,
            login,
            password,
            client_info=client_info,
        )
        if token:
            await message.answer(auth_success_message(settings.command_prefix))
            return
        if not await auth_manager.check_ban(message.from_user.id):
            await message.answer(auth_failed_message())

    return router
