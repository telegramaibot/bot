"""Daily reporting plugin backed by APScheduler."""

from __future__ import annotations

# === MODIFIED ===

from loguru import logger

from userbot_remote.ai_engine.gemini_client import GeminiClient
from userbot_remote.config.settings import Settings
from userbot_remote.db.repository import Repository
from userbot_remote.safety.anti_ban import safe_send
from userbot_remote.utils.helpers import chunk_text
from userbot_remote.utils.helpers import utc_now


class DailyLogger:
    """Generate and deliver daily activity summaries."""

    def __init__(
        self,
        repository: Repository,
        client,
        settings: Settings,
        gemini_client: GeminiClient,
    ) -> None:
        """Store dependencies for daily reports.

        Args:
            repository: Shared repository.
            client: Active Telethon client.
            settings: Application settings.
            gemini_client: Gemini wrapper.
        """

        self.repository = repository
        self.client = client
        self.settings = settings
        self.gemini_client = gemini_client

    async def collect_stats(self) -> dict:
        """Collect today's stats from the database.

        Returns:
            Dictionary of daily metrics.
        """

        target_date = utc_now().date().isoformat()
        messages_received = await self.repository.count_messages_for_date(target_date)
        commands_executed = await self.repository.count_commands_for_date(target_date)
        manual_log = await self.repository.get_daily_log(target_date)
        briefings_sent = await self.repository.count_monitor_logs_for_date(target_date)
        briefings_sent += await self.repository.count_commands_by_actions_for_date(
            target_date,
            ["brief", "chat_summary", "analyze_file", "daily_report_now"],
        )
        tasks_completed = await self.repository.count_completed_tasks_for_date(target_date)
        most_active_chats = await self.repository.list_most_active_chats_for_date(target_date, limit=3)
        keywords_triggered = await self.repository.list_keywords_for_date(target_date)
        return {
            "date": target_date,
            "messages_received": messages_received,
            "commands_executed": commands_executed,
            "briefings_sent": briefings_sent,
            "tasks_completed": tasks_completed,
            "most_active_chats": most_active_chats,
            "keywords_triggered": keywords_triggered,
            "manual_log": manual_log.summary if manual_log else "",
        }

    async def generate_report(self, client=None) -> str:
        """Generate an Uzbek daily report using Gemini.

        Args:
            client: Optional compatibility parameter.

        Returns:
            Final formatted report text.
        """

        stats = await self.collect_stats()
        events = [
            f"Sana: {stats['date']}",
            f"Xabarlar: {stats['messages_received']}",
            f"Buyruqlar: {stats['commands_executed']}",
            f"Briefinglar: {stats['briefings_sent']}",
            f"Vazifalar: {stats['tasks_completed']}",
            f"Kalit so'zlar: {', '.join(stats['keywords_triggered']) or '-'}",
            f"Manual log: {stats['manual_log'] or '-'}",
        ]
        for item in stats["most_active_chats"]:
            events.append(f"Faol chat: {item['chat_title']} ({item['message_count']} ta)")
        ai_report = await self.gemini_client.generate_daily_report(events)
        header = "\n".join(
            [
                f"📊 Kunlik Hisobot — {stats['date']}",
                "━━━━━━━━━━━━━━━",
                f"📨 Xabarlar: {stats['messages_received']} ta",
                f"⚡ Buyruqlar: {stats['commands_executed']} ta",
                f"🔔 Briefinglar: {stats['briefings_sent']} ta",
                f"✅ Vazifalar: {stats['tasks_completed']} ta",
                "🔥 Faol chatlar: "
                + (", ".join(item["chat_title"] for item in stats["most_active_chats"]) or "-"),
                "",
                ai_report,
            ]
        )
        return header

    async def post_report(self, client=None) -> None:
        """Post today's report to the configured log channel.

        Args:
            client: Optional Telethon client override.
        """

        active_client = client or self.client
        report = await self.generate_report(active_client)
        if self.settings.log_channel_id is None:
            logger.warning("LOG_CHANNEL_ID is not configured; daily report was generated but not posted.")
            return
        for chunk in chunk_text(report):
            await safe_send(active_client, self.settings.log_channel_id, text=chunk)
        logger.info("Posted daily report to LOG_CHANNEL_ID.")

    async def write_manual(self, client, text: str) -> None:
        """Append a manual log line to today's journal.

        Args:
            client: Optional compatibility parameter.
            text: Manual log text.
        """

        await self.repository.append_daily_log_entry(text)


DailyLoggerPlugin = DailyLogger
