"""Dataclasses representing database entities."""

from __future__ import annotations

# === MODIFIED ===

from dataclasses import dataclass


@dataclass
class UserRecord:
    """Application user record."""

    id: int
    telegram_id: int | None
    login: str
    password_hash: str
    role: str
    created_at: str
    is_active: bool


@dataclass
class SessionRecord:
    """Authenticated session record."""

    id: int
    user_id: int
    token_hash: str
    created_at: str
    expires_at: str
    last_activity_at: str
    is_active: bool
    client_info: str | None = None
    login: str | None = None
    telegram_id: int | None = None


@dataclass
class BanRecord:
    """Banned Telegram account record."""

    id: int
    telegram_id: int
    reason: str
    banned_at: str


@dataclass
class LoginAttemptRecord:
    """Login attempt audit record."""

    id: int
    telegram_id: int
    attempted_at: str
    success: bool
    client_info: str | None = None


@dataclass
class LoginHistoryRecord:
    """Successful login history record."""

    id: int
    user_id: int
    telegram_id: int
    client_info: str
    created_at: str


@dataclass
class MessageRecord:
    """Stored Telegram message snapshot."""

    id: int
    message_id: int | None
    chat_id: int
    chat_title: str
    sender_id: int | None
    sender_name: str
    text: str
    media_type: str | None
    file_path: str | None
    timestamp: str
    is_from_owner: bool


@dataclass
class MonitorLogRecord:
    """Keyword monitor event record."""

    id: int
    chat_id: int
    message_id: int
    chat_title: str
    keyword: str
    message_text: str
    summary: str
    file_path: str | None
    notified_at: str


@dataclass
class ScheduledTaskRecord:
    """Deferred task record."""

    id: int
    task_type: str
    payload_json: str
    run_at: str
    status: str
    created_at: str
    updated_at: str
    result_text: str


@dataclass
class DailyLogRecord:
    """Daily summary record."""

    id: int
    date: str
    summary: str
    created_at: str


@dataclass
class CommandLogRecord:
    """Executed command audit record."""

    id: int
    action: str
    telegram_id: int | None
    status: str
    details: str
    created_at: str
