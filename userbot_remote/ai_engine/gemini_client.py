"""Async Gemini AI wrapper with Uzbek-first prompting and safe fallbacks."""

from __future__ import annotations

# === NEW CODE ===

import asyncio
from collections.abc import Iterable
import mimetypes
from pathlib import Path

import aiofiles
from loguru import logger

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - dependency is optional at import time
    genai = None


class GeminiClient:
    """Provide async Gemini helpers used across the project."""

    def __init__(self, api_key: str | None, model_name: str = "gemini-1.5-flash") -> None:
        """Initialize the Gemini wrapper.

        Args:
            api_key: Google Gemini API key.
            model_name: Target Gemini model name.
        """

        self.api_key = (api_key or "").strip()
        self.model_name = model_name.strip() or "gemini-1.5-flash"
        self.enabled = bool(self.api_key and genai is not None)
        if self.enabled:
            genai.configure(api_key=self.api_key)
        else:
            logger.warning("Gemini client initialized in fallback mode.")

    async def analyze_text(self, text: str, system_prompt: str | None = None) -> str:
        """Analyze text and return insights in Uzbek.

        Args:
            text: Source text to analyze.
            system_prompt: Optional extra instruction for the model.

        Returns:
            Uzbek analysis text.
        """

        prompt = "\n\n".join(
            part
            for part in [
                system_prompt or "Siz kuchli tahlilchi assistantsiz. Faqat o'zbek tilida javob bering.",
                "Quyidagi matnni tahlil qiling, asosiy fikrlar, xavflar va keyingi qadamlarni yozing:",
                text.strip(),
            ]
            if part
        )
        return await self._generate_text(prompt, fallback=self._fallback_summary(text))

    async def analyze_file(self, file_path: str, mime_type: str | None, question: str) -> str:
        """Analyze a file and return an Uzbek summary.

        Args:
            file_path: Absolute or relative file path.
            mime_type: MIME type hint for the file.
            question: User question or analysis instruction.

        Returns:
            Gemini response or a fallback summary.
        """

        path = Path(file_path).resolve()
        detected_mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        if detected_mime.startswith("text/") or detected_mime in {"application/json", "text/csv"}:
            async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as file:
                content = await file.read()
            prompt = "\n\n".join(
                [
                    "Fayl tarkibini o'zbek tilida tahlil qiling. Asosiy ma'lumotlar, raqamlar va tavsiyalarni yozing.",
                    f"Savol: {question}",
                    content[:12000],
                ]
            )
            return await self._generate_text(prompt, fallback=self._fallback_summary(content))

        if not self.enabled:
            return await self.analyze_text(
                f"Fayl: {path.name}\nMIME: {detected_mime}\nSavol: {question}",
                system_prompt="Faylning o'zi yuborilmagan. Minimal foydali Uzbek xulosa yozing.",
            )

        try:
            return await asyncio.to_thread(
                self._analyze_file_sync,
                path,
                detected_mime,
                question,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.exception("Gemini file analysis failed for '{}'.", path)
            return await self.analyze_text(
                f"Fayl: {path.name}\nMIME: {detected_mime}\nSavol: {question}\nXato: {exc}"
            )

    async def summarize_messages(self, messages: list[dict]) -> str:
        """Summarize Telegram messages into a brief Uzbek report.

        Args:
            messages: Message dictionaries.

        Returns:
            Uzbek briefing text.
        """

        if not messages:
            return "Xabarlar topilmadi."
        formatted_lines = []
        for item in messages:
            sender_name = item.get("sender_name") or "Noma'lum"
            message_text = item.get("text") or "[media]"
            formatted_lines.append(f"[{item.get('timestamp')}] {sender_name}: {message_text}")
        formatted = "\n".join(formatted_lines)
        prompt = "\n\n".join(
            [
                "Quyidagi yozishmani rahbar uchun qisqa briefing ko'rinishida o'zbek tilida xulosalang.",
                "Asosiy mavzular, qarorlar, xavflar va keyingi qadamlarni alohida ko'rsating.",
                formatted[:18000],
            ]
        )
        return await self._generate_text(prompt, fallback=self._fallback_summary(formatted))

    async def smart_reply(self, context: str, tone: str = "friendly") -> str:
        """Generate a natural reply from conversation context.

        Args:
            context: Conversation context.
            tone: Desired reply tone.

        Returns:
            Generated reply in Uzbek.
        """

        prompt = "\n\n".join(
            [
                "Siz Telegram yozishmalari uchun tabiiy javob yozuvchi assistantsiz.",
                f"Ohang: {tone}",
                "Quyidagi kontekst asosida bitta tayyor javob yozing. O'zbek tilida, qisqa va tabiiy bo'lsin.",
                context.strip(),
            ]
        )
        return await self._generate_text(prompt, fallback="Rahmat, ma'lumotni oldim. Tez orada javob beraman.")

    async def translate(self, text: str, target_lang: str = "uz") -> str:
        """Translate text to a target language.

        Args:
            text: Source text.
            target_lang: Target language code.

        Returns:
            Translated text.
        """

        prompt = "\n\n".join(
            [
                f"Quyidagi matnni {target_lang} tiliga aniq va tabiiy tarjima qiling.",
                "Faqat tayyor tarjimani qaytaring.",
                text.strip(),
            ]
        )
        return await self._generate_text(prompt, fallback=text)

    async def generate_daily_report(self, events: list[str]) -> str:
        """Generate a structured daily report in Uzbek.

        Args:
            events: Raw daily events/stat lines.

        Returns:
            Formatted report text.
        """

        prompt = "\n\n".join(
            [
                "Quyidagi kundalik statistikalar va voqealardan rahbar uchun chiroyli, aniq, o'zbekcha hisobot tuzing.",
                "Format: umumiy holat, asosiy ko'rsatkichlar, xavflar, tavsiyalar.",
                "\n".join(events),
            ]
        )
        return await self._generate_text(prompt, fallback="\n".join(events))

    async def _generate_text(self, prompt: str, fallback: str) -> str:
        """Generate text via Gemini with graceful fallback.

        Args:
            prompt: Prompt to send.
            fallback: Fallback text if Gemini fails.

        Returns:
            Generated or fallback text.
        """

        if not self.enabled:
            return fallback
        try:
            return await asyncio.to_thread(self._generate_text_sync, prompt)
        except Exception:  # pragma: no cover - network dependent
            logger.exception("Gemini text generation failed.")
            return fallback

    def _generate_text_sync(self, prompt: str) -> str:
        """Run blocking Gemini text generation.

        Args:
            prompt: Prompt body.

        Returns:
            Generated text.

        Raises:
            RuntimeError: If no Gemini text is returned.
        """

        model = genai.GenerativeModel(model_name=self.model_name)
        response = model.generate_content(prompt)
        text = self._extract_response_text(response)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text

    def _analyze_file_sync(self, path: Path, mime_type: str, question: str) -> str:
        """Run blocking Gemini file analysis.

        Args:
            path: File path.
            mime_type: File MIME type.
            question: Analysis prompt.

        Returns:
            Generated analysis text.
        """

        uploaded = genai.upload_file(path=str(path), mime_type=mime_type)
        try:
            model = genai.GenerativeModel(model_name=self.model_name)
            response = model.generate_content(
                [
                    (
                        "Quyidagi faylni o'zbek tilida tahlil qiling. "
                        "Asosiy ma'lumotlar, sonlar, trendlar va amaliy tavsiyalarni yozing.\n"
                        f"Savol: {question}"
                    ),
                    uploaded,
                ]
            )
            text = self._extract_response_text(response)
            if not text:
                raise RuntimeError("Gemini file analysis returned an empty response.")
            return text
        finally:
            delete_file = getattr(genai, "delete_file", None)
            if callable(delete_file):
                try:
                    delete_file(uploaded.name)
                except Exception:
                    logger.warning("Failed to delete Gemini uploaded file '{}'.", getattr(uploaded, "name", "unknown"))

    @staticmethod
    def _extract_response_text(response) -> str:
        """Extract response text from a Gemini SDK response.

        Args:
            response: SDK response object.

        Returns:
            Plain text content.
        """

        text = getattr(response, "text", None)
        if text:
            return text.strip()
        candidates = getattr(response, "candidates", None) or []
        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) if content else []:
                part_text = getattr(part, "text", None)
                if part_text:
                    parts.append(part_text.strip())
        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _fallback_summary(text: str) -> str:
        """Build a simple fallback summary when Gemini is unavailable.

        Args:
            text: Source text.

        Returns:
            Minimal useful Uzbek summary.
        """

        cleaned = " ".join(text.split())
        if not cleaned:
            return "Tahlil uchun matn topilmadi."
        excerpt = cleaned[:600]
        return (
            "Gemini mavjud emas yoki javob bermadi. Quyidagi qisqa xulosa tayyorlandi:\n"
            f"• Mazmun: {excerpt}\n"
            "• Tavsiya: muhim raqamlar va vazifalarni qo'lda tekshirib chiqing."
        )
