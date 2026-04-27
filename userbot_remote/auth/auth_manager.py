"""Password, JWT, session, and security management."""

from __future__ import annotations

# === MODIFIED ===

from collections.abc import Awaitable, Callable
from datetime import datetime
from datetime import timedelta

import bcrypt
from jose import JWTError, jwt
from loguru import logger

from userbot_remote.config.settings import Settings
from userbot_remote.db.models import BanRecord, SessionRecord, UserRecord
from userbot_remote.db.repository import Repository
from userbot_remote.utils.helpers import sha256_text, utc_now


OwnerNotifier = Callable[[str], Awaitable[None]]


class AuthManager:
    """Manage application users, sessions, and access rules."""

    def __init__(self, repository: Repository, settings: Settings) -> None:
        """Bind dependencies required for authentication workflows.

        Args:
            repository: Shared repository instance.
            settings: Application settings.
        """

        self.repository = repository
        self.settings = settings
        self.owner_notifier: OwnerNotifier | None = None

    def set_owner_notifier(self, notifier: OwnerNotifier | None) -> None:
        """Register an owner alert callback.

        Args:
            notifier: Async callback for owner alerts.
        """

        self.owner_notifier = notifier

    def hash_password(self, password: str) -> str:
        """Hash a plain-text password with bcrypt."""

        # bcrypt requires bytes; truncate to 72 bytes (bcrypt hard limit).
        secret = password.encode("utf-8")[:72]
        return bcrypt.hashpw(secret, bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Verify a plain-text password against its stored hash."""

        secret = plain.encode("utf-8")[:72]
        try:
            return bcrypt.checkpw(secret, hashed.encode("utf-8"))
        except Exception:
            return False

    def create_jwt_token(self, user_id: int, telegram_id: int) -> str:
        """Create a signed JWT token for an authenticated user."""

        expires_at = utc_now() + timedelta(hours=self.settings.session_expire_hours)
        payload = {
            "sub": str(user_id),
            "telegram_id": telegram_id,
            "iat": int(utc_now().timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, self.settings.jwt_secret, algorithm="HS256")

    def verify_jwt_token(self, token: str) -> dict | None:
        """Decode and verify a JWT token."""

        try:
            return jwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"])
        except JWTError:
            return None

    async def register_user(
        self,
        login: str,
        password: str,
        telegram_id: int | None,
        role: str = "user",
    ) -> UserRecord:
        """Create a new application user with a hashed password."""

        existing = await self.repository.get_user_by_login(login)
        if existing and existing.is_active:
            raise ValueError(f"User '{login}' allaqachon mavjud.")
        password_hash = self.hash_password(password)
        if existing and not existing.is_active:
            restored = await self.repository.reactivate_user(
                login=login,
                password_hash=password_hash,
                telegram_id=telegram_id,
                role=role,
            )
            if restored is None:
                raise ValueError(f"User '{login}'ni qayta tiklab bo'lmadi.")
            logger.info("Reactivated user '{}' with role '{}'.", login, role)
            return restored
        user = await self.repository.create_user(
            login=login,
            password_hash=password_hash,
            telegram_id=telegram_id,
            role=role,
        )
        logger.info("Registered new user '{}' with role '{}'.", login, role)
        return user

    async def authenticate(
        self,
        telegram_id: int,
        login: str,
        password: str,
        client_info: str | None = None,
    ) -> str | None:
        """Authenticate credentials, issue JWT, and persist a session."""

        if await self.check_ban(telegram_id):
            logger.warning("Blocked authentication attempt from banned Telegram id {}.", telegram_id)
            return None

        user = await self.repository.get_user_by_login(login)
        if user is None or not user.is_active:
            await self.record_login_attempt(telegram_id, success=False, client_info=client_info)
            await self._ban_if_needed(telegram_id)
            return None

        if not self.verify_password(password, user.password_hash):
            await self.record_login_attempt(telegram_id, success=False, client_info=client_info)
            await self._ban_if_needed(telegram_id)
            return None

        if user.telegram_id is not None and user.telegram_id != telegram_id:
            logger.warning(
                "Login '{}' attempted from unexpected Telegram id {} (bound to {}).",
                login,
                telegram_id,
                user.telegram_id,
            )
            await self.record_login_attempt(telegram_id, success=False, client_info=client_info)
            await self._ban_if_needed(telegram_id)
            return None

        if user.telegram_id is None:
            existing_binding = await self.repository.get_user_by_telegram_id(telegram_id)
            if existing_binding is not None and existing_binding.login != login and existing_binding.is_active:
                logger.warning(
                    "Telegram id {} already belongs to login '{}', rejected login '{}'.",
                    telegram_id,
                    existing_binding.login,
                    login,
                )
                await self.record_login_attempt(telegram_id, success=False, client_info=client_info)
                await self._ban_if_needed(telegram_id)
                return None
            user = await self.repository.bind_user_telegram(login, telegram_id)
            if user is None:
                await self.record_login_attempt(telegram_id, success=False, client_info=client_info)
                await self._ban_if_needed(telegram_id)
                return None

        await self.repository.deactivate_sessions_by_user_id(user.id)
        token = self.create_jwt_token(user.id, telegram_id)
        expires_at = (utc_now() + timedelta(hours=self.settings.session_expire_hours)).isoformat()
        await self.repository.create_session(
            user_id=user.id,
            token_hash=sha256_text(token),
            expires_at=expires_at,
            client_info=client_info,
        )
        await self.record_login_attempt(telegram_id, success=True, client_info=client_info)
        await self.repository.record_login_history(user.id, telegram_id, client_info or "unknown")
        await self._alert_on_suspicious_activity(user, login)
        logger.info("Authenticated login '{}' for Telegram id {}.", login, telegram_id)
        return token

    async def is_authenticated(self, telegram_id: int) -> bool:
        """Check whether a Telegram account has an active session."""

        session = await self.repository.get_active_session_by_telegram_id(telegram_id)
        return session is not None

    async def validate_activity(self, telegram_id: int, client_info: str | None = None) -> bool:
        """Validate an active session and auto-refresh it when close to expiry.

        Args:
            telegram_id: Telegram account id.
            client_info: Best-effort client descriptor.

        Returns:
            True if the user remains authenticated.
        """

        session = await self.repository.get_active_session_by_telegram_id(telegram_id)
        if session is None:
            return False

        expires_at = self._parse_iso_datetime(session.expires_at)
        extend_expiry: str | None = None
        if expires_at - utc_now() < timedelta(hours=1):
            extend_expiry = (utc_now() + timedelta(hours=self.settings.session_expire_hours)).isoformat()
            logger.info("Auto-renewed session {} for Telegram id {}.", session.id, telegram_id)

        await self.repository.touch_session(session.id, expires_at=extend_expiry, client_info=client_info)
        return True

    async def record_login_attempt(self, telegram_id: int, success: bool, client_info: str | None = None) -> None:
        """Save a login attempt audit entry."""

        await self.repository.save_login_attempt(telegram_id, success, client_info=client_info)

    async def check_ban(self, telegram_id: int) -> bool:
        """Check whether a Telegram id is currently banned."""

        return await self.repository.is_banned(telegram_id)

    async def ban_user(self, telegram_id: int, reason: str) -> None:
        """Ban a Telegram id and revoke its sessions."""

        await self.repository.add_ban(telegram_id, reason)
        await self.repository.deactivate_session_by_telegram_id(telegram_id)
        logger.warning("Banned Telegram id {}: {}", telegram_id, reason)

    async def unban_user(self, telegram_id: int) -> bool:
        """Remove a Telegram account from the ban list."""

        result = await self.repository.remove_ban(telegram_id)
        if result:
            logger.info("Unbanned Telegram id {}.", telegram_id)
        return result

    async def get_ban_list(self) -> list[BanRecord]:
        """Return all banned Telegram accounts."""

        return await self.repository.list_bans()

    async def get_all_sessions(self) -> list[SessionRecord]:
        """Return all active sessions."""

        return await self.repository.list_active_sessions()

    async def revoke_session(self, telegram_id: int) -> None:
        """Revoke all sessions for a Telegram id."""

        await self.repository.deactivate_session_by_telegram_id(telegram_id)
        logger.info("Revoked session for Telegram id {}.", telegram_id)

    async def revoke_session_by_login(self, login: str) -> bool:
        """Revoke sessions for a user identified by login."""

        user = await self.repository.get_user_by_login(login)
        if user is None:
            return False
        await self.repository.deactivate_sessions_by_user_id(user.id)
        logger.info("Revoked session for login '{}'.", login)
        return True

    async def get_user_by_telegram_id(self, telegram_id: int) -> UserRecord | None:
        """Fetch a user record linked to a Telegram id."""

        return await self.repository.get_user_by_telegram_id(telegram_id)

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        """Fetch a user record by login."""

        return await self.repository.get_user_by_login(login)

    async def delete_user(self, login: str) -> bool:
        """Deactivate a user and revoke their sessions."""

        return await self.repository.delete_user(login)

    async def user_is_admin(self, telegram_id: int) -> bool:
        """Check whether a Telegram account belongs to an admin user."""

        user = await self.repository.get_user_by_telegram_id(telegram_id)
        return user is not None and user.is_active and user.role in {"admin", "owner"}

    async def ensure_admin_user(self) -> UserRecord:
        """Create the bootstrap admin account from environment settings if needed."""

        existing = await self.repository.get_user_by_login(self.settings.admin_login)
        if existing is not None:
            return existing
        return await self.register_user(
            login=self.settings.admin_login,
            password=self.settings.admin_password,
            telegram_id=None,
            role="admin",
        )

    async def _ban_if_needed(self, telegram_id: int) -> None:
        """Ban a Telegram id after repeated failed login attempts."""

        failed_attempts = await self.repository.count_recent_failed_attempts(telegram_id)
        if failed_attempts >= 3:
            await self.ban_user(telegram_id, "3 ta noto'g'ri login urinishlari")

    async def _alert_on_suspicious_activity(self, user: UserRecord, login: str) -> None:
        """Notify the owner if the same login was used from many accounts.

        Args:
            user: Authenticated user.
            login: Login string.
        """

        distinct_accounts = await self.repository.count_distinct_login_accounts_for_user(user.id)
        if distinct_accounts < 3 or self.owner_notifier is None:
            return
        try:
            await self.owner_notifier(
                f"⚠️ Shubhali login faolligi: '{login}' 24 soatda {distinct_accounts} xil Telegram akkauntdan ishlatilgan."
            )
        except Exception:
            logger.exception("Failed to notify owner about suspicious login activity for '{}'.", login)

    @staticmethod
    def _parse_iso_datetime(value: str):
        """Parse an ISO datetime string into a timezone-aware datetime.

        Args:
            value: ISO datetime string.

        Returns:
            Parsed datetime object.
        """

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return utc_now()
