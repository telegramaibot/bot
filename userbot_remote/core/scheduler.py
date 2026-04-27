"""APScheduler factory helpers."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def create_scheduler() -> AsyncIOScheduler:
    """Create the shared async APScheduler instance."""

    return AsyncIOScheduler(timezone="UTC")
