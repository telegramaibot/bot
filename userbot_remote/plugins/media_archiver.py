"""Plugin wrapper for media archiving workflows."""

from __future__ import annotations

from userbot_remote.userbot.media_ops import collect_and_archive


class MediaArchiverPlugin:
    """Convenience wrapper for collecting and zipping chat media."""

    def __init__(self, client, media_dir, archive_dir) -> None:
        """Store dependencies for archiving tasks."""

        self.client = client
        self.media_dir = media_dir
        self.archive_dir = archive_dir

    async def archive(self, chat, media_type: str, limit: int = 50) -> str:
        """Archive matching media files from a chat and return the ZIP path."""

        return await collect_and_archive(
            self.client,
            chat=chat,
            media_type=media_type,
            limit=limit,
            download_dir=self.media_dir,
            archive_dir=self.archive_dir,
        )
