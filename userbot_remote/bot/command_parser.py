"""Parse bot text commands into structured command objects."""

from __future__ import annotations

# === MODIFIED ===

from dataclasses import dataclass
from datetime import datetime
import re

from userbot_remote.utils.helpers import parse_command_args, parse_schedule_time


ADMIN_ACTIONS = {"sessions", "revoke", "adduser", "deluser", "banlist", "unban"}

_ALIAS_MAP = {
    "read": {"o'qi", "oqi", "read", "читать", "читай"},
    "send_message": {"yubor", "send", "отправь", "отправить"},
    "forward": {"forward", "перешли", "переслать"},
    "voice": {"voice", "ovoz", "голос"},
    "archive": {"arxiv", "archive", "архив"},
    "create_channel": {"kanal", "channel", "канал"},
    "create_group": {"guruh", "group", "группа"},
    "log": {"log", "журнал", "reportlog"},
    "schedule": {"jadval", "schedule", "расписание"},
    "schedule_list": {"jadvallar", "tasks", "задачи"},
    "schedule_cancel": {"bekor", "cancel", "отмена"},
    "search": {"top", "search", "поиск"},
    "global_search": {"qidir", "find", "искать"},
    "chat_summary": {"xulosa", "summary", "сводка"},
    "brief": {"brief", "briefing", "бриф"},
    "translate": {"tarjima", "translate", "перевод"},
    "analyze_file": {"tahlil", "analyze", "анализ"},
    "daily_report_now": {"hisobot", "report", "отчет"},
    "update_keywords": {"kalit", "keywords", "ключи"},
    "list_chats": {"chatlar", "chats", "чаты"},
    "sessions": {"sessions", "сессии"},
    "revoke": {"revoke", "отозвать"},
    "adduser": {"adduser", "добавитьюзера"},
    "deluser": {"deluser", "удалитьюзера"},
    "banlist": {"banlist", "баны"},
    "unban": {"unban", "разбан"},
    "help": {"help", "yordam", "помощь"},
}

_READ_AND_VOICE_PATTERNS = [
    re.compile(
        r"^(?:o['’]?qi|oqi|read|читать)\s+(?P<target>.+?)\s+(?P<count>\d+)\s+"
        r"(?:va\s+unga\s+ovoz\s+yubor|and\s+send\s+voice\s+to\s+them|и\s+отправь\s+ему\s+голос)\s+"
        r"(?P<voice_text>.+?)(?:\s+deb)?$",
        re.IGNORECASE,
    )
]


@dataclass
class Command:
    """Structured representation of a control-bot command."""

    action: str
    target: str | None = None
    text: str | None = None
    count: int | None = None
    media_type: str | None = None
    schedule_time: datetime | None = None
    raw: str = ""


class CommandParser:
    """Parse prefixed control-bot commands into Command objects."""

    def __init__(self, prefix: str = ".") -> None:
        """Store the configured command prefix.

        Args:
            prefix: Bot command prefix.
        """

        self.prefix = prefix

    def parse(self, raw_text: str) -> Command:
        """Parse a raw user command string into a Command object.

        Args:
            raw_text: Incoming text message.

        Returns:
            Parsed command instance.

        Raises:
            ValueError: If the command is invalid or unsupported.
        """

        text = (raw_text or "").strip()
        if not text.startswith(self.prefix):
            raise ValueError("Command noto'g'ri prefix bilan yuborildi.")

        body = text[len(self.prefix) :].strip()
        if not body:
            raise ValueError("Bo'sh buyruq.")

        combined = self._parse_read_and_voice(body, raw=text)
        if combined is not None:
            return combined

        args = parse_command_args(body)
        if not args:
            raise ValueError("Buyruq topilmadi.")

        action = self._resolve_action(args[0].lower())
        if action == "read":
            return self._parse_read(args, raw=text)
        if action == "send_message":
            return self._parse_send(args, raw=text)
        if action == "forward":
            return self._parse_forward(args, raw=text)
        if action == "voice":
            return self._parse_voice(args, raw=text)
        if action == "archive":
            return self._parse_archive(args, raw=text)
        if action == "create_channel":
            return self._parse_title_action(args, raw=text, action="create_channel")
        if action == "create_group":
            return self._parse_title_action(args, raw=text, action="create_group")
        if action == "log":
            return self._parse_text_only(args, raw=text, action="log", minimum=2)
        if action == "schedule":
            return self._parse_schedule(args, raw=text)
        if action == "schedule_list":
            return Command(action="schedule_list", raw=text)
        if action == "schedule_cancel":
            return self._parse_single_target(args, raw=text, action="schedule_cancel")
        if action == "search":
            return self._parse_search(args, raw=text)
        if action == "global_search":
            return self._parse_global_search(args, raw=text)
        if action == "chat_summary":
            return self._parse_chat_summary(args, raw=text)
        if action == "brief":
            return self._parse_title_action(args, raw=text, action="brief")
        if action == "translate":
            return self._parse_text_only(args, raw=text, action="translate", minimum=2)
        if action == "analyze_file":
            return Command(action="analyze_file", text=" ".join(args[1:]).strip() or None, raw=text)
        if action == "daily_report_now":
            return Command(action="daily_report_now", raw=text)
        if action == "update_keywords":
            return self._parse_keywords(args, raw=text)
        if action == "list_chats":
            return Command(action="list_chats", raw=text)
        if action == "sessions":
            return Command(action="sessions", raw=text)
        if action == "revoke":
            return self._parse_single_target(args, raw=text, action="revoke")
        if action == "adduser":
            return self._parse_adduser(args, raw=text)
        if action == "deluser":
            return self._parse_single_target(args, raw=text, action="deluser")
        if action == "banlist":
            return Command(action="banlist", raw=text)
        if action == "unban":
            return self._parse_single_target(args, raw=text, action="unban")
        if action == "help":
            return Command(action="help", raw=text)
        raise ValueError("Noma'lum buyruq.")

    def _resolve_action(self, token: str) -> str:
        """Map an alias token to an internal action name."""

        for action, aliases in _ALIAS_MAP.items():
            if token in aliases:
                return action
        raise ValueError(f"Noma'lum buyruq: {token}")

    def _parse_read_and_voice(self, body: str, raw: str) -> Command | None:
        """Parse the combined read-and-voice workflow command."""

        for pattern in _READ_AND_VOICE_PATTERNS:
            match = pattern.match(body)
            if match:
                return Command(
                    action="read_and_voice",
                    target=match.group("target").strip(),
                    count=int(match.group("count")),
                    text=match.group("voice_text").strip(),
                    raw=raw,
                )
        return None

    @staticmethod
    def _parse_read(args: list[str], raw: str) -> Command:
        """Parse a read-messages command."""

        if len(args) < 3:
            raise ValueError("Format: .o'qi <chat> <count>")
        count = int(args[-1])
        target = " ".join(args[1:-1]).strip()
        if not target:
            raise ValueError("Chat ko'rsatilmagan.")
        return Command(action="read", target=target, count=count, raw=raw)

    @staticmethod
    def _parse_send(args: list[str], raw: str) -> Command:
        """Parse a send-message command."""

        if len(args) < 3:
            raise ValueError("Format: .yubor <chat> <text>")
        return Command(action="send_message", target=args[1], text=" ".join(args[2:]).strip(), raw=raw)

    @staticmethod
    def _parse_forward(args: list[str], raw: str) -> Command:
        """Parse a forward command."""

        if len(args) < 4:
            raise ValueError("Format: .forward <from> <to> <count>")
        return Command(action="forward", target=args[1], text=args[2], count=int(args[3]), raw=raw)

    @staticmethod
    def _parse_voice(args: list[str], raw: str) -> Command:
        """Parse a voice-note command."""

        if len(args) < 3:
            raise ValueError("Format: .voice <chat> <text>")
        return Command(action="voice", target=args[1], text=" ".join(args[2:]).strip(), raw=raw)

    @staticmethod
    def _parse_archive(args: list[str], raw: str) -> Command:
        """Parse a media archive command."""

        if len(args) < 2:
            raise ValueError("Format: .arxiv <chat> [type] [limit]")
        media_type = args[2] if len(args) >= 3 else "all"
        count = int(args[3]) if len(args) >= 4 else 50
        return Command(action="archive", target=args[1], media_type=media_type, count=count, raw=raw)

    @staticmethod
    def _parse_title_action(args: list[str], raw: str, action: str) -> Command:
        """Parse commands that only take a title payload."""

        if len(args) < 2:
            raise ValueError("Nom ko'rsatilmagan.")
        return Command(action=action, target=" ".join(args[1:]).strip(), raw=raw)

    @staticmethod
    def _parse_text_only(args: list[str], raw: str, action: str, minimum: int = 2) -> Command:
        """Parse commands that accept only a text payload."""

        if len(args) < minimum:
            raise ValueError("Matn ko'rsatilmagan.")
        return Command(action=action, text=" ".join(args[1:]).strip(), raw=raw)

    def _parse_schedule(self, args: list[str], raw: str) -> Command:
        """Parse a scheduled-message command."""

        if len(args) < 4:
            raise ValueError("Format: .jadval <time> <chat> <text>")

        schedule_token_count = 1
        schedule_value = args[1]
        try:
            run_at = parse_schedule_time(schedule_value)
        except ValueError:
            if len(args) < 5:
                raise ValueError("Vaqt formatini tekshiring.")
            schedule_value = f"{args[1]} {args[2]}"
            run_at = parse_schedule_time(schedule_value)
            schedule_token_count = 2

        target_index = 1 + schedule_token_count
        if len(args) <= target_index + 1:
            raise ValueError("Format: .jadval <time> <chat> <text>")
        return Command(
            action="schedule",
            target=args[target_index],
            text=" ".join(args[target_index + 1 :]).strip(),
            schedule_time=run_at,
            raw=raw,
        )

    @staticmethod
    def _parse_search(args: list[str], raw: str) -> Command:
        """Parse a chat search command."""

        if len(args) < 3:
            raise ValueError("Format: .top <chat> <keyword>")
        return Command(action="search", target=args[1], text=" ".join(args[2:]).strip(), raw=raw)

    @staticmethod
    def _parse_global_search(args: list[str], raw: str) -> Command:
        """Parse a cross-chat search command."""

        if len(args) < 2:
            raise ValueError("Format: .qidir <keyword> [chat]")
        if len(args) == 2:
            return Command(action="global_search", text=args[1], raw=raw)
        return Command(action="global_search", text=args[1], target=" ".join(args[2:]).strip(), raw=raw)

    @staticmethod
    def _parse_chat_summary(args: list[str], raw: str) -> Command:
        """Parse an AI chat summary command."""

        if len(args) < 2:
            raise ValueError("Format: .xulosa <chat> [N] kun")
        days = 7
        if len(args) >= 4 and args[-1].lower() == "kun" and args[-2].isdigit():
            days = int(args[-2])
            target = " ".join(args[1:-2]).strip()
        else:
            target = " ".join(args[1:]).strip()
        if not target:
            raise ValueError("Chat ko'rsatilmagan.")
        return Command(action="chat_summary", target=target, count=days, raw=raw)

    @staticmethod
    def _parse_keywords(args: list[str], raw: str) -> Command:
        """Parse keyword update/show commands."""

        if len(args) < 2:
            raise ValueError("Format: .kalit <so'zlar> yoki .kalit ko'r")
        second = args[1].lower()
        if second in {"ko'r", "kor", "show", "list"}:
            return Command(action="show_keywords", raw=raw)
        return Command(action="update_keywords", text=" ".join(args[1:]).strip(), raw=raw)

    @staticmethod
    def _parse_single_target(args: list[str], raw: str, action: str) -> Command:
        """Parse commands that expect exactly one target argument."""

        if len(args) != 2:
            raise ValueError("Argument yetarli emas.")
        return Command(action=action, target=args[1], raw=raw)

    @staticmethod
    def _parse_adduser(args: list[str], raw: str) -> Command:
        """Parse an add-user command."""

        if len(args) != 3:
            raise ValueError("Format: .adduser <login> <password>")
        return Command(action="adduser", target=args[1], text=args[2], raw=raw)
