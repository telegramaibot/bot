"""Admin-only command handlers for user and session management."""

from __future__ import annotations

# === MODIFIED ===

from aiogram import F, Router
from aiogram.types import Message

from userbot_remote.auth.auth_manager import AuthManager
from userbot_remote.bot.command_parser import ADMIN_ACTIONS, CommandParser
from userbot_remote.bot.responses import access_denied_message
from userbot_remote.config.settings import Settings
from userbot_remote.utils.formatters import format_ban_list, format_sessions


def build_admin_router(
    auth_manager: AuthManager,
    parser: CommandParser,
    settings: Settings,
) -> Router:
    """Create the admin router for privileged commands."""

    router = Router(name="admin")

    @router.message(F.text)
    async def admin_commands_handler(message: Message) -> None:
        """Handle admin-only prefixed commands."""

        text = (message.text or "").strip()
        if not text.startswith(settings.command_prefix):
            return
        try:
            command = parser.parse(text)
        except ValueError:
            return
        if command.action not in ADMIN_ACTIONS:
            return

        telegram_id = message.from_user.id
        is_owner = telegram_id == settings.owner_id
        if not is_owner and not await auth_manager.user_is_admin(telegram_id):
            await message.answer(access_denied_message())
            return

        status_message = await message.answer("⏳ Bajarilmoqda...")
        try:
            if command.action == "sessions":
                sessions = await auth_manager.get_all_sessions()
                await status_message.edit_text(format_sessions(sessions))
                return

            if command.action == "revoke":
                revoked = await auth_manager.revoke_session_by_login(command.target or "")
                await status_message.edit_text("✅ Sessiya bekor qilindi." if revoked else "❌ Login topilmadi.")
                return

            if command.action == "adduser":
                await auth_manager.register_user(
                    login=command.target or "",
                    password=command.text or "",
                    telegram_id=None,
                    role="user",
                )
                await status_message.edit_text(f"✅ User qo'shildi: {command.target}")
                return

            if command.action == "deluser":
                deleted = await auth_manager.delete_user(command.target or "")
                await status_message.edit_text("✅ User o'chirildi." if deleted else "❌ Login topilmadi.")
                return

            if command.action == "banlist":
                await status_message.edit_text(format_ban_list(await auth_manager.get_ban_list()))
                return

            if command.action == "unban":
                unbanned = await auth_manager.unban_user(int(command.target or "0"))
                await status_message.edit_text("✅ Ban bekor qilindi." if unbanned else "❌ Telegram ID topilmadi.")
                return
        except Exception as exc:
            await status_message.edit_text(f"❌ Xato: {exc}")

    return router
