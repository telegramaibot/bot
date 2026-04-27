"""Async SQLite database initialization and migration helpers."""

from __future__ import annotations

# === MODIFIED ===

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL DEFAULT '',
    client_info TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ban_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    banned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    attempted_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    client_info TEXT
);

CREATE TABLE IF NOT EXISTS login_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL,
    client_info TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    chat_id INTEGER NOT NULL,
    chat_title TEXT NOT NULL,
    sender_id INTEGER,
    sender_name TEXT NOT NULL,
    text TEXT NOT NULL,
    media_type TEXT,
    file_path TEXT,
    timestamp TEXT NOT NULL,
    is_from_owner INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS monitor_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL DEFAULT 0,
    chat_title TEXT NOT NULL DEFAULT '',
    keyword TEXT NOT NULL,
    message_text TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    file_path TEXT,
    notified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    result_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    telegram_id INTEGER,
    status TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity_at ON sessions(last_activity_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_telegram_id ON login_attempts(telegram_id);
CREATE INDEX IF NOT EXISTS idx_login_history_user_id ON login_history(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_monitor_logs_keyword ON monitor_logs(keyword);
CREATE UNIQUE INDEX IF NOT EXISTS idx_monitor_unique_event ON monitor_logs(chat_id, message_id, keyword);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_status_run_at ON scheduled_tasks(status, run_at);
CREATE INDEX IF NOT EXISTS idx_command_logs_created_at ON command_logs(created_at);
"""

MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "sessions": {
        "last_activity_at": "TEXT NOT NULL DEFAULT ''",
        "client_info": "TEXT",
    },
    "login_attempts": {
        "client_info": "TEXT",
    },
    "messages": {
        "message_id": "INTEGER",
    },
    "monitor_logs": {
        "message_id": "INTEGER NOT NULL DEFAULT 0",
        "chat_title": "TEXT NOT NULL DEFAULT ''",
        "summary": "TEXT NOT NULL DEFAULT ''",
        "file_path": "TEXT",
    },
    "scheduled_tasks": {
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "result_text": "TEXT NOT NULL DEFAULT ''",
    },
}


class Database:
    """Async SQLite access wrapper."""

    def __init__(self, path: str | Path) -> None:
        """Store the target database path and ensure the directory exists.

        Args:
            path: Database file path.
        """

        self.path = Path(path).resolve()
        # Ensure parent directory exists before SQLite tries to open the file.
        # This prevents OperationalError on Railway and similar cloud runtimes.
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self):
        """Yield a configured SQLite connection.

        Yields:
            Configured SQLite connection object.
        """

        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON;")
        try:
            yield connection
        finally:
            await connection.close()

    async def init(self) -> None:
        """Create tables, indexes, and missing columns."""

        async with self.connection() as connection:
            await connection.executescript(SCHEMA_SQL)
            await self._apply_column_migrations(connection)
            await connection.commit()

    async def _apply_column_migrations(self, connection: aiosqlite.Connection) -> None:
        """Ensure newly introduced columns exist on upgraded databases.

        Args:
            connection: Active SQLite connection.
        """

        for table_name, columns in MIGRATION_COLUMNS.items():
            existing_columns = await self._get_columns(connection, table_name)
            for column_name, definition in columns.items():
                if column_name in existing_columns:
                    continue
                await connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                )

    @staticmethod
    async def _get_columns(connection: aiosqlite.Connection, table_name: str) -> set[str]:
        """Read the current column names for a table.

        Args:
            connection: Active SQLite connection.
            table_name: Table to inspect.

        Returns:
            Set of column names.
        """

        cursor = await connection.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        return {row["name"] for row in rows}
