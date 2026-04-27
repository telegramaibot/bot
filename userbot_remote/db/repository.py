"""Repository layer for all async database access."""

from __future__ import annotations

# === MODIFIED ===

from datetime import timedelta
import json

from userbot_remote.db.database import Database
from userbot_remote.db.models import (
    BanRecord,
    CommandLogRecord,
    DailyLogRecord,
    LoginAttemptRecord,
    LoginHistoryRecord,
    MessageRecord,
    MonitorLogRecord,
    ScheduledTaskRecord,
    SessionRecord,
    UserRecord,
)
from userbot_remote.utils.helpers import utc_now


class Repository:
    """Async repository providing CRUD operations for application data."""

    def __init__(self, database: Database) -> None:
        """Bind the repository to a database instance.

        Args:
            database: Shared database wrapper.
        """

        self.database = database

    async def create_user(
        self,
        login: str,
        password_hash: str,
        telegram_id: int | None = None,
        role: str = "user",
    ) -> UserRecord:
        """Insert a new user record."""

        created_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO users (telegram_id, login, password_hash, role, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (telegram_id, login, password_hash, role, created_at),
            )
            await connection.commit()
        return UserRecord(
            id=cursor.lastrowid,
            telegram_id=telegram_id,
            login=login,
            password_hash=password_hash,
            role=role,
            created_at=created_at,
            is_active=True,
        )

    async def reactivate_user(
        self,
        login: str,
        password_hash: str,
        telegram_id: int | None = None,
        role: str = "user",
    ) -> UserRecord | None:
        """Reactivate an existing user with fresh credentials."""

        async with self.database.connection() as connection:
            await connection.execute(
                """
                UPDATE users
                SET telegram_id = ?, password_hash = ?, role = ?, is_active = 1
                WHERE login = ?
                """,
                (telegram_id, password_hash, role, login),
            )
            await connection.commit()
        return await self.get_user_by_login(login)

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        """Fetch a user by login."""

        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM users WHERE login = ? LIMIT 1", (login,))
            row = await cursor.fetchone()
        return self._row_to_user(row)

    async def get_user_by_telegram_id(self, telegram_id: int) -> UserRecord | None:
        """Fetch a user by Telegram account id."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM users WHERE telegram_id = ? LIMIT 1",
                (telegram_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_user(row)

    async def bind_user_telegram(self, login: str, telegram_id: int) -> UserRecord | None:
        """Attach a Telegram id to an existing user record."""

        async with self.database.connection() as connection:
            await connection.execute(
                "UPDATE users SET telegram_id = ? WHERE login = ?",
                (telegram_id, login),
            )
            await connection.commit()
        return await self.get_user_by_login(login)

    async def delete_user(self, login: str) -> bool:
        """Soft-delete a user and deactivate sessions."""

        user = await self.get_user_by_login(login)
        if user is None:
            return False
        async with self.database.connection() as connection:
            await connection.execute(
                "UPDATE users SET is_active = 0, telegram_id = NULL WHERE login = ?",
                (login,),
            )
            await connection.execute("UPDATE sessions SET is_active = 0 WHERE user_id = ?", (user.id,))
            await connection.commit()
        return True

    async def create_session(
        self,
        user_id: int,
        token_hash: str,
        expires_at: str,
        client_info: str | None = None,
    ) -> SessionRecord:
        """Insert a new session row for a user."""

        created_at = utc_now().isoformat()
        last_activity_at = created_at
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO sessions (
                    user_id, token_hash, created_at, expires_at, last_activity_at, client_info, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (user_id, token_hash, created_at, expires_at, last_activity_at, client_info),
            )
            await connection.commit()
        return SessionRecord(
            id=cursor.lastrowid,
            user_id=user_id,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
            last_activity_at=last_activity_at,
            is_active=True,
            client_info=client_info,
        )

    async def touch_session(
        self,
        session_id: int,
        expires_at: str | None = None,
        client_info: str | None = None,
    ) -> SessionRecord | None:
        """Update last activity time and optionally extend session expiry."""

        last_activity_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            if expires_at is None:
                await connection.execute(
                    """
                    UPDATE sessions
                    SET last_activity_at = ?, client_info = COALESCE(?, client_info)
                    WHERE id = ?
                    """,
                    (last_activity_at, client_info, session_id),
                )
            else:
                await connection.execute(
                    """
                    UPDATE sessions
                    SET last_activity_at = ?, expires_at = ?, client_info = COALESCE(?, client_info)
                    WHERE id = ?
                    """,
                    (last_activity_at, expires_at, client_info, session_id),
                )
            await connection.commit()
            cursor = await connection.execute("SELECT * FROM sessions WHERE id = ? LIMIT 1", (session_id,))
            row = await cursor.fetchone()
        return self._row_to_session(row)

    async def deactivate_sessions_by_user_id(self, user_id: int) -> None:
        """Deactivate all sessions for a given user."""

        async with self.database.connection() as connection:
            await connection.execute("UPDATE sessions SET is_active = 0 WHERE user_id = ?", (user_id,))
            await connection.commit()

    async def deactivate_session_by_telegram_id(self, telegram_id: int) -> None:
        """Deactivate sessions for the user linked to a Telegram id."""

        user = await self.get_user_by_telegram_id(telegram_id)
        if user is None:
            return
        await self.deactivate_sessions_by_user_id(user.id)

    async def get_active_session_by_telegram_id(self, telegram_id: int) -> SessionRecord | None:
        """Fetch an active, non-expired session by Telegram id."""

        now_iso = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT s.*, u.login, u.telegram_id
                FROM sessions s
                INNER JOIN users u ON u.id = s.user_id
                WHERE u.telegram_id = ?
                  AND u.is_active = 1
                  AND s.is_active = 1
                  AND s.expires_at > ?
                ORDER BY s.id DESC
                LIMIT 1
                """,
                (telegram_id, now_iso),
            )
            row = await cursor.fetchone()
        return self._row_to_session(row)

    async def list_active_sessions(self) -> list[SessionRecord]:
        """Return all active, non-expired sessions."""

        now_iso = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT s.*, u.login, u.telegram_id
                FROM sessions s
                INNER JOIN users u ON u.id = s.user_id
                WHERE u.is_active = 1
                  AND s.is_active = 1
                  AND s.expires_at > ?
                ORDER BY s.last_activity_at DESC
                """,
                (now_iso,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]

    async def save_login_attempt(
        self,
        telegram_id: int,
        success: bool,
        client_info: str | None = None,
    ) -> LoginAttemptRecord:
        """Persist a login attempt."""

        attempted_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO login_attempts (telegram_id, attempted_at, success, client_info)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_id, attempted_at, int(success), client_info),
            )
            await connection.commit()
        return LoginAttemptRecord(
            id=cursor.lastrowid,
            telegram_id=telegram_id,
            attempted_at=attempted_at,
            success=success,
            client_info=client_info,
        )

    async def count_recent_failed_attempts(self, telegram_id: int, hours: int = 24) -> int:
        """Count consecutive recent failed login attempts for a Telegram id."""

        threshold = (utc_now() - timedelta(hours=hours)).isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT success
                FROM login_attempts
                WHERE telegram_id = ?
                  AND attempted_at >= ?
                ORDER BY attempted_at DESC
                LIMIT 3
                """,
                (telegram_id, threshold),
            )
            rows = await cursor.fetchall()
        failures = 0
        for row in rows:
            if bool(row["success"]):
                break
            failures += 1
        return failures

    async def record_login_history(
        self,
        user_id: int,
        telegram_id: int,
        client_info: str,
    ) -> LoginHistoryRecord:
        """Persist successful login history."""

        created_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO login_history (user_id, telegram_id, client_info, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, telegram_id, client_info, created_at),
            )
            await connection.commit()
        await self.trim_login_history(user_id, keep=10)
        return LoginHistoryRecord(
            id=cursor.lastrowid,
            user_id=user_id,
            telegram_id=telegram_id,
            client_info=client_info,
            created_at=created_at,
        )

    async def trim_login_history(self, user_id: int, keep: int = 10) -> None:
        """Keep only the latest N login history records for a user."""

        async with self.database.connection() as connection:
            await connection.execute(
                """
                DELETE FROM login_history
                WHERE id IN (
                    SELECT id
                    FROM login_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (user_id, keep),
            )
            await connection.commit()

    async def list_recent_login_history(self, user_id: int, limit: int = 10) -> list[LoginHistoryRecord]:
        """Fetch recent successful logins for a user."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM login_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._row_to_login_history(row) for row in rows]

    async def count_distinct_login_accounts_for_user(self, user_id: int, hours: int = 24) -> int:
        """Count distinct Telegram accounts used by a login in the recent period."""

        threshold = (utc_now() - timedelta(hours=hours)).isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT COUNT(DISTINCT telegram_id) AS count
                FROM login_history
                WHERE user_id = ?
                  AND created_at >= ?
                """,
                (user_id, threshold),
            )
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def add_ban(self, telegram_id: int, reason: str) -> BanRecord:
        """Insert or update a ban entry."""

        banned_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO ban_list (telegram_id, reason, banned_at)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id)
                DO UPDATE SET reason = excluded.reason, banned_at = excluded.banned_at
                """,
                (telegram_id, reason, banned_at),
            )
            await connection.commit()
            cursor = await connection.execute(
                "SELECT * FROM ban_list WHERE telegram_id = ? LIMIT 1",
                (telegram_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_ban(row)

    async def list_bans(self) -> list[BanRecord]:
        """Return all banned Telegram accounts."""

        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM ban_list ORDER BY banned_at DESC")
            rows = await cursor.fetchall()
        return [self._row_to_ban(row) for row in rows]

    async def remove_ban(self, telegram_id: int) -> bool:
        """Remove a Telegram account from the ban list."""

        async with self.database.connection() as connection:
            cursor = await connection.execute("DELETE FROM ban_list WHERE telegram_id = ?", (telegram_id,))
            await connection.commit()
        return bool(cursor.rowcount)

    async def is_banned(self, telegram_id: int) -> bool:
        """Check whether a Telegram id is banned."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT 1 FROM ban_list WHERE telegram_id = ? LIMIT 1",
                (telegram_id,),
            )
            row = await cursor.fetchone()
        return row is not None

    async def save_message(
        self,
        chat_id: int,
        chat_title: str,
        sender_id: int | None,
        sender_name: str,
        text: str,
        media_type: str | None,
        file_path: str | None,
        timestamp: str,
        is_from_owner: bool,
        message_id: int | None = None,
    ) -> MessageRecord:
        """Persist a message snapshot."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO messages (
                    message_id, chat_id, chat_title, sender_id, sender_name, text,
                    media_type, file_path, timestamp, is_from_owner
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    chat_id,
                    chat_title,
                    sender_id,
                    sender_name,
                    text,
                    media_type,
                    file_path,
                    timestamp,
                    int(is_from_owner),
                ),
            )
            await connection.commit()
        return MessageRecord(
            id=cursor.lastrowid,
            message_id=message_id,
            chat_id=chat_id,
            chat_title=chat_title,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            media_type=media_type,
            file_path=file_path,
            timestamp=timestamp,
            is_from_owner=is_from_owner,
        )

    async def list_recent_messages(self, chat_id: int, limit: int = 10) -> list[MessageRecord]:
        """Fetch recent stored messages for a chat."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._row_to_message(row) for row in rows]

    async def save_monitor_log(
        self,
        chat_id: int,
        message_id: int,
        chat_title: str,
        keyword: str,
        message_text: str,
        summary: str,
        file_path: str | None = None,
    ) -> MonitorLogRecord:
        """Persist a keyword monitor alert row."""

        notified_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT OR REPLACE INTO monitor_logs (
                    chat_id, message_id, chat_title, keyword, message_text, summary, file_path, notified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, message_id, chat_title, keyword, message_text, summary, file_path, notified_at),
            )
            await connection.commit()
        return MonitorLogRecord(
            id=cursor.lastrowid,
            chat_id=chat_id,
            message_id=message_id,
            chat_title=chat_title,
            keyword=keyword,
            message_text=message_text,
            summary=summary,
            file_path=file_path,
            notified_at=notified_at,
        )

    async def monitor_log_exists(self, chat_id: int, message_id: int, keyword: str) -> bool:
        """Check whether a monitor event has already been recorded."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT 1
                FROM monitor_logs
                WHERE chat_id = ? AND message_id = ? AND keyword = ?
                LIMIT 1
                """,
                (chat_id, message_id, keyword),
            )
            row = await cursor.fetchone()
        return row is not None

    async def create_scheduled_task(
        self,
        task_type: str,
        payload: dict,
        run_at: str,
        status: str = "pending",
    ) -> ScheduledTaskRecord:
        """Persist a scheduled task."""

        payload_json = json.dumps(payload, ensure_ascii=False)
        created_at = utc_now().isoformat()
        updated_at = created_at
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO scheduled_tasks (
                    task_type, payload_json, run_at, status, created_at, updated_at, result_text
                )
                VALUES (?, ?, ?, ?, ?, ?, '')
                """,
                (task_type, payload_json, run_at, status, created_at, updated_at),
            )
            await connection.commit()
        return ScheduledTaskRecord(
            id=cursor.lastrowid,
            task_type=task_type,
            payload_json=payload_json,
            run_at=run_at,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            result_text="",
        )

    async def get_scheduled_task(self, task_id: int) -> ScheduledTaskRecord | None:
        """Fetch a scheduled task by id."""

        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
        return self._row_to_scheduled_task(row)

    async def list_pending_scheduled_tasks(self) -> list[ScheduledTaskRecord]:
        """Return all pending tasks."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM scheduled_tasks
                WHERE status = 'pending'
                ORDER BY run_at ASC
                """
            )
            rows = await cursor.fetchall()
        return [self._row_to_scheduled_task(row) for row in rows]

    async def list_due_scheduled_tasks(self, now_iso: str) -> list[ScheduledTaskRecord]:
        """Return tasks that are due for execution."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM scheduled_tasks
                WHERE status = 'pending'
                  AND run_at <= ?
                ORDER BY run_at ASC
                """,
                (now_iso,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_scheduled_task(row) for row in rows]

    async def list_scheduled_tasks(self, include_finished: bool = False) -> list[ScheduledTaskRecord]:
        """Return scheduled tasks for display."""

        query = "SELECT * FROM scheduled_tasks"
        if not include_finished:
            query += " WHERE status IN ('pending', 'running')"
        query += " ORDER BY run_at ASC"
        async with self.database.connection() as connection:
            cursor = await connection.execute(query)
            rows = await cursor.fetchall()
        return [self._row_to_scheduled_task(row) for row in rows]

    async def update_scheduled_task_status(self, task_id: int, status: str, result_text: str = "") -> None:
        """Update a scheduled task status and result."""

        updated_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            await connection.execute(
                """
                UPDATE scheduled_tasks
                SET status = ?, updated_at = ?, result_text = ?
                WHERE id = ?
                """,
                (status, updated_at, result_text, task_id),
            )
            await connection.commit()

    async def cancel_scheduled_task(self, task_id: int) -> bool:
        """Cancel a pending scheduled task."""

        task = await self.get_scheduled_task(task_id)
        if task is None or task.status not in {"pending", "running"}:
            return False
        await self.update_scheduled_task_status(task_id, "cancelled", "Bekor qilindi")
        return True

    async def upsert_daily_log(self, date: str, summary: str) -> DailyLogRecord:
        """Insert or replace the daily summary for a given date."""

        created_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            await connection.execute(
                """
                INSERT INTO daily_logs (date, summary, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(date)
                DO UPDATE SET summary = excluded.summary, created_at = excluded.created_at
                """,
                (date, summary, created_at),
            )
            await connection.commit()
            cursor = await connection.execute("SELECT * FROM daily_logs WHERE date = ?", (date,))
            row = await cursor.fetchone()
        return self._row_to_daily_log(row)

    async def append_daily_log_entry(self, text: str, date: str | None = None) -> DailyLogRecord:
        """Append a line to the daily summary."""

        target_date = date or utc_now().date().isoformat()
        existing = await self.get_daily_log(target_date)
        summary = text if existing is None else f"{existing.summary}\n{text}".strip()
        return await self.upsert_daily_log(target_date, summary)

    async def get_daily_log(self, date: str) -> DailyLogRecord | None:
        """Fetch a daily summary by date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM daily_logs WHERE date = ?", (date,))
            row = await cursor.fetchone()
        return self._row_to_daily_log(row)

    async def save_command_log(
        self,
        action: str,
        telegram_id: int | None,
        status: str,
        details: str = "",
    ) -> CommandLogRecord:
        """Persist an executed command entry."""

        created_at = utc_now().isoformat()
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO command_logs (action, telegram_id, status, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action, telegram_id, status, details, created_at),
            )
            await connection.commit()
        return CommandLogRecord(
            id=cursor.lastrowid,
            action=action,
            telegram_id=telegram_id,
            status=status,
            details=details,
            created_at=created_at,
        )

    async def count_messages_for_date(self, date: str) -> int:
        """Count stored messages for a specific date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE substr(timestamp, 1, 10) = ?",
                (date,),
            )
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def count_monitor_logs_for_date(self, date: str) -> int:
        """Count monitor hits for a specific date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS count FROM monitor_logs WHERE substr(notified_at, 1, 10) = ?",
                (date,),
            )
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def count_commands_for_date(self, date: str) -> int:
        """Count executed commands for a specific date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) AS count FROM command_logs WHERE substr(created_at, 1, 10) = ?",
                (date,),
            )
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def count_commands_by_actions_for_date(self, date: str, actions: list[str]) -> int:
        """Count executed commands filtered by action names."""

        if not actions:
            return 0
        placeholders = ",".join("?" for _ in actions)
        query = (
            f"SELECT COUNT(*) AS count FROM command_logs "
            f"WHERE substr(created_at, 1, 10) = ? AND action IN ({placeholders})"
        )
        params = [date, *actions]
        async with self.database.connection() as connection:
            cursor = await connection.execute(query, params)
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def count_completed_tasks_for_date(self, date: str) -> int:
        """Count completed scheduled tasks for a specific date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM scheduled_tasks
                WHERE status = 'done'
                  AND substr(updated_at, 1, 10) = ?
                """,
                (date,),
            )
            row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def list_most_active_chats_for_date(self, date: str, limit: int = 3) -> list[dict]:
        """Return top chats by message count for a given date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT chat_id, chat_title, COUNT(*) AS message_count
                FROM messages
                WHERE substr(timestamp, 1, 10) = ?
                GROUP BY chat_id, chat_title
                ORDER BY message_count DESC
                LIMIT ?
                """,
                (date, limit),
            )
            rows = await cursor.fetchall()
        return [
            {
                "chat_id": row["chat_id"],
                "chat_title": row["chat_title"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]

    async def list_keywords_for_date(self, date: str) -> list[str]:
        """Return distinct keywords triggered during a specific date."""

        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT DISTINCT keyword
                FROM monitor_logs
                WHERE substr(notified_at, 1, 10) = ?
                ORDER BY keyword ASC
                """,
                (date,),
            )
            rows = await cursor.fetchall()
        return [str(row["keyword"]) for row in rows]

    @staticmethod
    def _row_to_user(row) -> UserRecord | None:
        """Convert a SQLite row into a UserRecord."""

        if row is None:
            return None
        return UserRecord(
            id=row["id"],
            telegram_id=row["telegram_id"],
            login=row["login"],
            password_hash=row["password_hash"],
            role=row["role"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    @staticmethod
    def _row_to_session(row) -> SessionRecord | None:
        """Convert a SQLite row into a SessionRecord."""

        if row is None:
            return None
        return SessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_activity_at=row["last_activity_at"] if "last_activity_at" in row.keys() else row["created_at"],
            is_active=bool(row["is_active"]),
            client_info=row["client_info"] if "client_info" in row.keys() else None,
            login=row["login"] if "login" in row.keys() else None,
            telegram_id=row["telegram_id"] if "telegram_id" in row.keys() else None,
        )

    @staticmethod
    def _row_to_ban(row) -> BanRecord | None:
        """Convert a SQLite row into a BanRecord."""

        if row is None:
            return None
        return BanRecord(
            id=row["id"],
            telegram_id=row["telegram_id"],
            reason=row["reason"],
            banned_at=row["banned_at"],
        )

    @staticmethod
    def _row_to_login_history(row) -> LoginHistoryRecord | None:
        """Convert a SQLite row into a LoginHistoryRecord."""

        if row is None:
            return None
        return LoginHistoryRecord(
            id=row["id"],
            user_id=row["user_id"],
            telegram_id=row["telegram_id"],
            client_info=row["client_info"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_message(row) -> MessageRecord | None:
        """Convert a SQLite row into a MessageRecord."""

        if row is None:
            return None
        return MessageRecord(
            id=row["id"],
            message_id=row["message_id"] if "message_id" in row.keys() else None,
            chat_id=row["chat_id"],
            chat_title=row["chat_title"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            text=row["text"],
            media_type=row["media_type"],
            file_path=row["file_path"],
            timestamp=row["timestamp"],
            is_from_owner=bool(row["is_from_owner"]),
        )

    @staticmethod
    def _row_to_scheduled_task(row) -> ScheduledTaskRecord | None:
        """Convert a SQLite row into a ScheduledTaskRecord."""

        if row is None:
            return None
        return ScheduledTaskRecord(
            id=row["id"],
            task_type=row["task_type"],
            payload_json=row["payload_json"],
            run_at=row["run_at"],
            status=row["status"],
            created_at=row["created_at"] if "created_at" in row.keys() else "",
            updated_at=row["updated_at"] if "updated_at" in row.keys() else "",
            result_text=row["result_text"] if "result_text" in row.keys() else "",
        )

    @staticmethod
    def _row_to_daily_log(row) -> DailyLogRecord | None:
        """Convert a SQLite row into a DailyLogRecord."""

        if row is None:
            return None
        return DailyLogRecord(
            id=row["id"],
            date=row["date"],
            summary=row["summary"],
            created_at=row["created_at"],
        )
