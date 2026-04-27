"""Aiogram middlewares for authentication enforcement."""

from __future__ import annotations

# === MODIFIED ===

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from userbot_remote.auth.auth_manager import AuthManager
from userbot_remote.bot.responses import login_prompt
from userbot_remote.config.settings import Settings
from userbot_remote.utils.helpers import is_login_payload


class AuthMiddleware(BaseMiddleware):
    """Block unauthenticated users while allowing the login flow."""

    def __init__(self, auth_manager: AuthManager, settings: Settings) -> None:
        """Store auth dependencies used by the middleware."""

        self.auth_manager = auth_manager
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Check authentication for each incoming message/callback."""

        telegram_id = self._extract_telegram_id(event)
        if telegram_id is None:
            return await handler(event, data)

        if telegram_id == self.settings.owner_id:
            data["is_owner"] = True
            return await handler(event, data)

        if await self.auth_manager.check_ban(telegram_id):
            return None

        client_info = self._build_client_info(event)
        if await self.auth_manager.validate_activity(telegram_id, client_info=client_info):
            data["is_owner"] = False
            data["auth_user"] = await self.auth_manager.get_user_by_telegram_id(telegram_id)
            return await handler(event, data)

        if self._is_login_allowed_message(event):
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(login_prompt())
            return None

        if isinstance(event, CallbackQuery):
            await event.answer("Avval login qiling.", show_alert=True)
            return None

        return None

    @staticmethod
    def _extract_telegram_id(event: TelegramObject) -> int | None:
        """Extract Telegram user id from a message or callback event."""

        from_user = getattr(event, "from_user", None)
        if from_user is not None:
            return from_user.id
        message = getattr(event, "message", None)
        if message is not None and getattr(message, "from_user", None) is not None:
            return message.from_user.id
        return None

    @staticmethod
    def _is_login_allowed_message(event: TelegramObject) -> bool:
        """Check whether an unauthenticated event should pass through."""

        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/start") or text.startswith("/help") or text.startswith("/logout"):
                return True
            return is_login_payload(text)
        return False

    @staticmethod
    def _build_client_info(event: TelegramObject) -> str:
        """Create a lightweight client-info string for session history.

        Args:
            event: Telegram event.

        Returns:
            Compact client descriptor string.
        """

        from_user = getattr(event, "from_user", None)
        if from_user is None:
            message = getattr(event, "message", None)
            from_user = getattr(message, "from_user", None)
        if from_user is None:
            return "unknown-client"
        username = from_user.username or "no_username"
        lang = getattr(from_user, "language_code", None) or "unknown_lang"
        premium = "premium" if getattr(from_user, "is_premium", False) else "standard"
        return f"user={username}|lang={lang}|tier={premium}"
