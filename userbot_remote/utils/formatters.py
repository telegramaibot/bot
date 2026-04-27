"""Formatting helpers for bot and userbot responses."""

from __future__ import annotations

# === MODIFIED ===

from datetime import datetime

from userbot_remote.db.models import BanRecord, ScheduledTaskRecord, SessionRecord


def format_messages(messages: list[dict]) -> str:
    """Format message rows into a readable Telegram response."""

    if not messages:
        return "Xabar topilmadi."
    lines = []
    for item in messages:
        timestamp = item.get("timestamp", "")
        sender = item.get("sender_name") or item.get("sender_id") or "Noma'lum"
        text = item.get("text") or "[media]"
        lines.append(f"[{timestamp}] {sender}: {text}")
    return "\n".join(lines)


def format_dialogs(dialogs: list[dict]) -> str:
    """Format dialogs into a compact list."""

    if not dialogs:
        return "Chatlar topilmadi."
    lines = []
    for dialog in dialogs:
        username = f"@{dialog['username']}" if dialog.get("username") else "-"
        unread = dialog.get("unread_count", 0)
        lines.append(
            f"• {dialog['title']} | id={dialog['id']} | {dialog['type']} | {username} | unread={unread}"
        )
    return "\n".join(lines)


def format_search_results(messages: list[dict], keyword: str) -> str:
    """Format search results for the control bot."""

    if not messages:
        return f"'{keyword}' bo'yicha hech narsa topilmadi."
    header = f"'{keyword}' bo'yicha topilgan xabarlar:"
    return "\n".join([header, format_messages(messages)])


def format_sessions(sessions: list[SessionRecord]) -> str:
    """Format active sessions for admin users."""

    if not sessions:
        return "Faol sessiyalar yo'q."
    lines = []
    for session in sessions:
        expires_at = session.expires_at.replace("T", " ")
        last_activity = (session.last_activity_at or session.created_at).replace("T", " ")
        login = session.login or "unknown"
        telegram_id = session.telegram_id or "-"
        client_info = session.client_info or "-"
        lines.append(
            f"• {login} | tg={telegram_id} | oxirgi faollik={last_activity} | expires={expires_at} | client={client_info}"
        )
    return "\n".join(lines)


def format_ban_list(items: list[BanRecord]) -> str:
    """Format banned Telegram accounts for admin users."""

    if not items:
        return "Ban ro'yxati bo'sh."
    return "\n".join(
        f"• tg={item.telegram_id} | {item.reason} | {item.banned_at.replace('T', ' ')}"
        for item in items
    )


def format_tasks(tasks: list[ScheduledTaskRecord]) -> str:
    """Format scheduled tasks for display."""

    if not tasks:
        return "Rejalashtirilgan vazifalar yo'q."
    lines = []
    for task in tasks:
        lines.append(
            f"• ID={task.id} | {task.task_type} | status={task.status} | run_at={task.run_at.replace('T', ' ')}"
        )
    return "\n".join(lines)


def format_datetime(value: datetime | None) -> str:
    """Format an optional datetime value for user-facing messages."""

    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M UTC")
