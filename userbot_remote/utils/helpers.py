"""Generic helper functions used across the project."""

from __future__ import annotations

# === MODIFIED ===

import hashlib
import re
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path


LOGIN_PAYLOAD_PATTERN = re.compile(
    r"^\s*login:(?P<login>\S+)\s+pass:(?P<password>.+?)\s*$",
    re.IGNORECASE,
)


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def sha256_text(value: str) -> str:
    """Create a SHA-256 hex digest for the supplied string."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_login_payload(text: str | None) -> bool:
    """Check whether a text message matches the login payload format."""

    if not text:
        return False
    return LOGIN_PAYLOAD_PATTERN.match(text) is not None


def parse_login_payload(text: str) -> tuple[str, str]:
    """Parse a login credential payload into login and password parts.

    Args:
        text: Raw credential message from the user.

    Returns:
        A tuple of login and password strings.

    Raises:
        ValueError: If the payload format is invalid.
    """

    match = LOGIN_PAYLOAD_PATTERN.match(text)
    if not match:
        raise ValueError("Invalid login payload.")
    return match.group("login").strip(), match.group("password").strip()


def sanitize_filename(value: str) -> str:
    """Generate a filesystem-safe filename fragment."""

    sanitized = re.sub(r"[^\w\-\.]+", "_", value.strip(), flags=re.UNICODE)
    return sanitized.strip("_") or "telegram"


def parse_command_args(text: str) -> list[str]:
    """Split a command string into shell-style arguments."""

    first_token, separator, remainder = text.strip().partition(" ")
    if not separator:
        return [first_token]
    lexer = shlex.shlex(remainder, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.quotes = '"'
    parsed = list(lexer)
    return [first_token] + parsed


def parse_schedule_time(value: str) -> datetime:
    """Parse schedule text into a timezone-aware UTC datetime.

    Supported formats:
        - HH:MM
        - YYYY-MM-DD HH:MM
        - YYYY-MM-DDTHH:MM
        - DD.MM.YYYY HH:MM

    Args:
        value: User-supplied schedule string.

    Returns:
        A UTC datetime for the target schedule.

    Raises:
        ValueError: If the schedule string cannot be parsed.
    """

    raw = value.strip()
    now = utc_now()
    if re.fullmatch(r"\d{2}:\d{2}", raw):
        run_at = datetime.strptime(raw, "%H:%M").replace(
            year=now.year,
            month=now.month,
            day=now.day,
            tzinfo=timezone.utc,
        )
        if run_at <= now:
            run_at = run_at + timedelta(days=1)
        return run_at

    patterns = (
        ("%Y-%m-%d %H:%M", lambda dt: dt.replace(tzinfo=timezone.utc)),
        ("%Y-%m-%dT%H:%M", lambda dt: dt.replace(tzinfo=timezone.utc)),
        ("%d.%m.%Y %H:%M", lambda dt: dt.replace(tzinfo=timezone.utc)),
    )
    for fmt, normalizer in patterns:
        try:
            return normalizer(datetime.strptime(raw, fmt))
        except ValueError:
            continue
    raise ValueError("Unsupported schedule format.")


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    """Split long text into Telegram-safe chunks."""

    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            split_index = text.rfind("\n", start, end)
            if split_index > start:
                end = split_index
        chunks.append(text[start:end].strip())
        start = end
    return [chunk for chunk in chunks if chunk]


def display_path(path: str | Path) -> str:
    """Return a user-friendly absolute path string."""

    return str(Path(path).resolve())
