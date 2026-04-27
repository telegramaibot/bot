"""Environment-backed application settings."""

from __future__ import annotations

# === MODIFIED ===

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Convert environment string values into booleans."""

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_list(value: str | None) -> list[int]:
    """Convert a comma-separated integer string into a list."""

    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _parse_str_list(value: str | None) -> list[str]:
    """Convert a comma-separated string into a normalized list."""

    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _optional_int(value: str | None) -> int | None:
    """Convert an optional environment string into an integer."""

    if value is None or not value.strip():
        return None
    return int(value.strip())


def _resolve_runtime_path(value: str, default_name: str) -> Path:
    """Resolve relative runtime paths against the project directory."""

    raw = value.strip() if value else default_name
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


@dataclass
class Settings:
    """Validated runtime settings for the application."""

    api_id: int
    api_hash: str
    phone_number: str
    session_name: str
    session_path: Path
    session_string: str | None
    bot_token: str
    owner_id: int
    command_prefix: str
    admin_login: str
    admin_password: str
    jwt_secret: str
    session_expire_hours: int
    gemini_api_key: str | None
    gemini_model: str
    auto_respond_chats: list[int]
    monitor_keywords: list[str]
    log_channel_id: int | None
    ghost_mode: bool
    min_delay: int
    max_delay: int
    read_delay_min: int
    read_delay_max: int
    database_path: Path
    media_dir: Path
    archive_dir: Path
    temp_dir: Path
    log_dir: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build and validate application settings from environment variables."""

        load_dotenv()
        session_name = os.getenv("SESSION_NAME", "userbot_session").strip() or "userbot_session"
        database_path = _resolve_runtime_path(os.getenv("DATABASE_PATH", "/data/userbot.db"), "/data/userbot.db")
        session_path = _resolve_runtime_path(f"{session_name}.session", f"{session_name}.session")

        settings = cls(
            api_id=int(os.getenv("API_ID", "0")),
            api_hash=os.getenv("API_HASH", "").strip(),
            phone_number=os.getenv("PHONE_NUMBER", "").strip(),
            session_name=session_name,
            session_path=session_path,
            session_string=os.getenv("SESSION_STRING", "").strip() or None,
            bot_token=os.getenv("BOT_TOKEN", "").strip(),
            owner_id=int(os.getenv("OWNER_ID", "0")),
            command_prefix=os.getenv("COMMAND_PREFIX", ".").strip() or ".",
            admin_login=os.getenv("ADMIN_LOGIN", "admin").strip(),
            admin_password=os.getenv("ADMIN_PASSWORD", "").strip(),
            jwt_secret=os.getenv("JWT_SECRET", "").strip(),
            session_expire_hours=int(os.getenv("SESSION_EXPIRE_HOURS", "24")),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip() or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash",
            auto_respond_chats=_parse_int_list(os.getenv("AUTO_RESPOND_CHATS")),
            monitor_keywords=_parse_str_list(os.getenv("MONITOR_KEYWORDS")),
            log_channel_id=_optional_int(os.getenv("LOG_CHANNEL_ID")),
            ghost_mode=_parse_bool(os.getenv("GHOST_MODE"), default=True),
            min_delay=int(os.getenv("MIN_DELAY", "2")),
            max_delay=int(os.getenv("MAX_DELAY", "6")),
            read_delay_min=int(os.getenv("READ_DELAY_MIN", "30")),
            read_delay_max=int(os.getenv("READ_DELAY_MAX", "120")),
            database_path=database_path,
            media_dir=(BASE_DIR / "runtime" / "media").resolve(),
            archive_dir=(BASE_DIR / "runtime" / "archives").resolve(),
            temp_dir=(BASE_DIR / "runtime" / "temp").resolve(),
            log_dir=(BASE_DIR / "runtime" / "logs").resolve(),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )
        settings.validate()
        settings.ensure_runtime_dirs()
        return settings

    def validate(self) -> None:
        """Validate required settings and logical constraints."""

        required_fields = {
            "API_ID": self.api_id,
            "API_HASH": self.api_hash,
            "PHONE_NUMBER": self.phone_number,
            "BOT_TOKEN": self.bot_token,
            "OWNER_ID": self.owner_id,
            "ADMIN_PASSWORD": self.admin_password,
            "JWT_SECRET": self.jwt_secret,
        }
        missing = [name for name, value in required_fields.items() if value in {"", 0, None}]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        if self.min_delay < 0 or self.max_delay < self.min_delay:
            raise ValueError("MIN_DELAY and MAX_DELAY values are invalid.")
        if self.read_delay_min < 0 or self.read_delay_max < self.read_delay_min:
            raise ValueError("READ_DELAY_MIN and READ_DELAY_MAX values are invalid.")
        if not self.command_prefix:
            raise ValueError("COMMAND_PREFIX cannot be empty.")

    def ensure_runtime_dirs(self) -> None:
        """Create runtime directories used by the application."""

        for path in (
            self.database_path.parent,
            self.media_dir,
            self.archive_dir,
            self.temp_dir,
            self.log_dir,
            self.session_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings instance."""

    return Settings.from_env()
