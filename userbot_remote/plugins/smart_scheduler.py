"""Task scheduling plugin for future Telegram actions."""

from __future__ import annotations

# === MODIFIED ===

from datetime import datetime, timezone
import json

from loguru import logger

from userbot_remote.db.models import ScheduledTaskRecord
from userbot_remote.db.repository import Repository
from userbot_remote.plugins.voice_sender import VoiceSender
from userbot_remote.userbot.chat_ops import forward_messages, send_message
from userbot_remote.utils.helpers import utc_now


class SmartScheduler:
    """Persist and execute scheduled Telegram tasks."""

    def __init__(self, repository: Repository, client, settings, voice_sender: VoiceSender) -> None:
        """Store dependencies used for scheduling.

        Args:
            repository: Shared repository.
            client: Active Telethon client.
            settings: Application settings.
            voice_sender: Voice sender plugin.
        """

        self.repository = repository
        self.client = client
        self.settings = settings
        self.voice_sender = voice_sender

    async def schedule_message(
        self,
        client,
        target: str,
        text: str,
        run_at: datetime,
        voice: bool = False,
    ) -> int:
        """Persist a future send-message task.

        Args:
            client: Unused compatibility parameter for the current client.
            target: Destination chat.
            text: Message text.
            run_at: Execution time.
            voice: Whether to send as a voice note.

        Returns:
            Created task id.
        """

        task = await self.repository.create_scheduled_task(
            task_type="send_voice" if voice else "send_message",
            payload={"target": target, "text": text},
            run_at=run_at.astimezone(timezone.utc).isoformat(),
            status="pending",
        )
        logger.info("Scheduled {} task {} for {}.", task.task_type, task.id, task.run_at)
        return task.id

    async def schedule_forward(self, source: str, target: str, limit: int, run_at: datetime) -> int:
        """Persist a future forward task.

        Args:
            source: Source chat.
            target: Destination chat.
            limit: Number of messages to forward.
            run_at: Execution time.

        Returns:
            Created task id.
        """

        task = await self.repository.create_scheduled_task(
            task_type="forward",
            payload={"source": source, "target": target, "limit": limit},
            run_at=run_at.astimezone(timezone.utc).isoformat(),
            status="pending",
        )
        logger.info("Scheduled forward task {} for {}.", task.id, task.run_at)
        return task.id

    async def list_tasks(self) -> list[dict]:
        """Return all active scheduled tasks formatted for display.

        Returns:
            List of serializable task dictionaries.
        """

        tasks = await self.repository.list_scheduled_tasks(include_finished=False)
        return [
            {
                "id": task.id,
                "task_type": task.task_type,
                "run_at": task.run_at,
                "status": task.status,
                "result_text": task.result_text,
            }
            for task in tasks
        ]

    async def cancel_task(self, task_id: int) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: Task identifier.

        Returns:
            True if the task was cancelled.
        """

        return await self.repository.cancel_scheduled_task(task_id)

    async def execute_pending(self, client=None) -> None:
        """Execute all tasks that are due.

        Args:
            client: Optional Telethon client override.
        """

        active_client = client or self.client
        due_tasks = await self.repository.list_due_scheduled_tasks(utc_now().isoformat())
        for task in due_tasks:
            await self.repository.update_scheduled_task_status(task.id, "running", "Ishga tushdi")
            try:
                payload = json.loads(task.payload_json)
                if task.task_type == "send_message":
                    await send_message(
                        active_client,
                        target=payload["target"],
                        text=payload["text"],
                        delay=False,
                        ghost_mode=False,
                        min_delay=self.settings.min_delay,
                        max_delay=self.settings.max_delay,
                    )
                elif task.task_type == "send_voice":
                    await self.voice_sender.send_voice(active_client, payload["target"], payload["text"])
                elif task.task_type == "forward":
                    await forward_messages(
                        active_client,
                        source=payload["source"],
                        target=payload["target"],
                        limit=int(payload["limit"]),
                    )
                else:
                    raise ValueError(f"Noma'lum task turi: {task.task_type}")
                await self.repository.update_scheduled_task_status(task.id, "done", "Muvaffaqiyatli bajarildi")
            except Exception as exc:
                logger.exception("Scheduled task {} failed.", task.id)
                await self.repository.update_scheduled_task_status(task.id, "failed", str(exc))


SmartSchedulerPlugin = SmartScheduler
