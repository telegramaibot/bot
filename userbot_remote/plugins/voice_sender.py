"""Voice-note generation and delivery helpers."""

from __future__ import annotations

# === MODIFIED ===

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from gtts import gTTS
from langdetect import LangDetectException, detect
from loguru import logger

from userbot_remote.safety.anti_ban import safe_send
from userbot_remote.userbot.contact_ops import resolve_entity
from userbot_remote.utils.helpers import sanitize_filename


class VoiceSender:
    """Generate Telegram voice notes with gTTS and ffmpeg."""

    def __init__(self, temp_dir: str | Path) -> None:
        """Store the temporary directory used for generated audio files.

        Args:
            temp_dir: Directory for generated mp3/ogg files.
        """

        self.temp_dir = Path(temp_dir).resolve()
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def text_to_ogg(self, text: str, lang: str = "ru") -> str:
        """Convert text into an OGG/Opus voice note.

        Args:
            text: Input text for TTS.
            lang: Language code for gTTS.

        Returns:
            Absolute path to the generated `.ogg` file.

        Raises:
            RuntimeError: If ffmpeg conversion fails.
        """

        stem = sanitize_filename(f"voice_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}")
        mp3_path = self.temp_dir / f"{stem}.mp3"
        ogg_path = self.temp_dir / f"{stem}.ogg"
        try:
            await asyncio.to_thread(self._generate_mp3_sync, text, lang, mp3_path)
            await asyncio.to_thread(self._convert_with_ffmpeg_sync, mp3_path, ogg_path)
            return str(ogg_path.resolve())
        except Exception:
            await asyncio.to_thread(self._safe_unlink_sync, mp3_path)
            await asyncio.to_thread(self._safe_unlink_sync, ogg_path)
            raise
        finally:
            await asyncio.to_thread(self._safe_unlink_sync, mp3_path)

    async def auto_detect_lang(self, text: str) -> str:
        """Detect whether text is mostly Uzbek, Russian, or English.

        Args:
            text: Source text.

        Returns:
            One of `uz`, `ru`, or `en`.
        """

        sample = (text or "").strip()
        if not sample:
            return "ru"
        try:
            detected = await asyncio.to_thread(detect, sample)
        except LangDetectException:
            detected = "ru"
        detected = detected.lower()
        if detected.startswith("uz"):
            return "uz"
        if detected.startswith("en"):
            return "en"
        return "ru"

    async def send_voice(self, client, target, text: str, lang: str | None = None) -> None:
        """Generate and send a Telegram voice note.

        Args:
            client: Active Telethon client.
            target: Telegram entity or identifier.
            text: TTS source text.
            lang: Optional language code override.
        """

        entity = await resolve_entity(client, target)
        selected_lang = lang or await self.auto_detect_lang(text)
        ogg_path = await self.text_to_ogg(text, selected_lang)
        try:
            await safe_send(client, entity, file=ogg_path, voice_note=True)
        finally:
            await asyncio.to_thread(self._safe_unlink_sync, Path(ogg_path))

    @staticmethod
    def _generate_mp3_sync(text: str, lang: str, destination: Path) -> None:
        """Generate an MP3 file from text synchronously.

        Args:
            text: Source text.
            lang: gTTS language code.
            destination: Output mp3 path.
        """

        tts = gTTS(text=text, lang=lang)
        tts.save(str(destination))

    @staticmethod
    def _convert_with_ffmpeg_sync(source: Path, destination: Path) -> None:
        """Convert MP3 into OGG/Opus using ffmpeg.

        Args:
            source: Input mp3 file path.
            destination: Output ogg file path.

        Raises:
            RuntimeError: If ffmpeg exits with a non-zero code.
        """

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(source),
                    "-c:a",
                    "libopus",
                    str(destination),
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("ffmpeg conversion failed: {}", exc.stderr.decode("utf-8", errors="ignore"))
            raise RuntimeError("ffmpeg yordamida ovoz konvertatsiyasi muvaffaqiyatsiz tugadi.") from exc

    @staticmethod
    def _safe_unlink_sync(path: Path) -> None:
        """Delete a temporary file if it exists.

        Args:
            path: File path to delete.
        """

        if path.exists():
            path.unlink()


VoiceSenderPlugin = VoiceSender
