"""Formatted text responses used by the control bot."""

from __future__ import annotations

# === MODIFIED ===


def login_prompt() -> str:
    """Return the standard login prompt for new users."""

    return "Salom! Login va parolni kiriting:\nlogin: mylogin\npass: mypassword"


def auth_success_message(prefix: str) -> str:
    """Return the authentication success message."""

    return f"✅ Xush kelibsiz! Buyruqlar: /help yoki {prefix}help"


def auth_failed_message() -> str:
    """Return the authentication failure message."""

    return "❌ Login yoki parol noto'g'ri. 3 marta xato kiritsangiz bloklanasiz."


def logout_message() -> str:
    """Return the logout success message."""

    return "✅ Sessiya bekor qilindi."


def access_denied_message() -> str:
    """Return a generic access-denied message."""

    return "❌ Ushbu buyruq uchun admin huquqi kerak."


def command_help(prefix: str) -> str:
    """Return the help text listing supported commands."""

    return "\n".join(
        [
            "📚 Mavjud buyruqlar:",
            f"{prefix}o'qi <chat> <n> - chatdagi oxirgi xabarlarni o'qish",
            f"{prefix}yubor <chat> <text> - xabar yuborish",
            f"{prefix}forward <from> <to> <n> - xabarlarni forward qilish",
            f"{prefix}voice <chat> <text> - ovozli xabar yuborish",
            f"{prefix}tahlil [savol] - biriktirilgan faylni AI bilan tahlil qilish",
            f"{prefix}brief <chat> - chatdan AI briefing olish",
            f"{prefix}tarjima <text> - matnni tarjima qilish",
            f"{prefix}arxiv <chat> [type] [limit] - media arxivlash",
            f"{prefix}kanal <name> - yangi kanal yaratish",
            f"{prefix}guruh <name> - yangi guruh yaratish",
            f"{prefix}log <text> - manual log yozish",
            f"{prefix}jadval <time> <chat> <text> - xabarni rejalashtirish",
            f"{prefix}jadvallar - rejalashtirilgan vazifalar",
            f"{prefix}bekor <id> - vazifani bekor qilish",
            f"{prefix}top <chat> <keyword> - qidiruv",
            f"{prefix}qidir <keyword> [chat] - barcha chatlarda qidiruv",
            f"{prefix}xulosa <chat> [N] kun - AI chat xulosasi",
            f"{prefix}hisobot - bugungi hisobotni hozir olish",
            f"{prefix}kalit <words> - monitor kalit so'zlarini yangilash",
            f"{prefix}kalit ko'r - joriy kalit so'zlarni ko'rish",
            f"{prefix}chatlar - barcha chatlar ro'yxati",
            f"{prefix}sessions - faol sessiyalar",
            f"{prefix}revoke <login> - sessiyani bekor qilish",
            f"{prefix}banlist - ban ro'yxatini ko'rish",
            f"{prefix}unban <telegram_id> - bandan chiqarish",
            f"{prefix}adduser <login> <pass> - foydalanuvchi qo'shish",
            f"{prefix}deluser <login> - foydalanuvchini o'chirish",
            f"{prefix}help - yordam",
            "",
            "Media yuborish uchun faylga caption yozing:",
            f"{prefix}yubor <chat> [caption]",
            "",
            "Fayl tahlili uchun caption misol:",
            f"{prefix}tahlil jadvaldagi xavf va sonlarni ajrat",
        ]
    )
