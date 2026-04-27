"""Async Gemini AI wrapper with Uzbek-first prompting and safe fallbacks."""

from __future__ import annotations

# === MODIFIED — migrated to google-genai SDK ===

import asyncio
import mimetypes
from pathlib import Path

import aiofiles
from loguru import logger

try:
    from google import genai as _genai
    _GENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _genai = None
    _GENAI_AVAILABLE = False


class GeminiClient:
    """Provide async Gemini helpers used across the project."""

    def __init__(self, api_key: str | None, model_name: str = "gemini-1.5-flash") -> None:
        self.api_key = (api_key or "").strip()
        self.model_name = model_name.strip() or "gemini-1.5-flash"
        self.enabled = bool(self.api_key and _GENAI_AVAILABLE)
        if self.enabled:
            self._client = _genai.Client(api_key=self.api_key)
            logger.info("Gemini client initialized with model '{}'.", self.model_name)
        else:
            self._client = None
            logger.warning("Gemini client initialized in fallback mode (no API key or SDK).")

    async def analyze_text(self, text: str, system_prompt: str | None = None) -> str:
        prompt = "\n\n".join(
            part for part in [
                system_prompt or "Siz kuchli tahlilchi assistantsiz. Faqat o'zbek tilida javob bering.",
                "Quyidagi matnni tahlil qiling, asosiy fikrlar, xavflar va keyingi qadamlarni yozing:",
                text.strip(),
            ] if part
        )
        return await self._generate_text(prompt, fallback=self._fallback_summary(text))

    async def analyze_file(self, file_path: str, mime_type: str | None, question: str) -> str:
        path = Path(file_path).resolve()
        detected_mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        if detected_mime.startswith("text/") or detected_mime in {"application/json", "text/csv"}:
            async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as fh:
                content = await fh.read()
            prompt = "\n\n".join([
                "Fayl tarkibini o'zbek tilida tahlil qiling. Asosiy ma'lumotlar, raqamlar va tavsiyalarni yozing.",
                f"Savol: {question}",
                content[:12000],
            ])
            return await self._generate_text(prompt, fallback=self._fallback_summary(content))

        if not self.enabled:
            return await self.analyze_text(
                f"Fayl: {path.name}\nMIME: {detected_mime}\nSavol: {question}",
                system_prompt="Faylning o'zi yuborilmagan. Minimal foydali Uzbek xulosa yozing.",
            )

        try:
            return await asyncio.to_thread(self._analyze_file_sync, path, detected_mime, question)
        except Exception as exc:
            logger.exception("Gemini file analysis failed for '{}'.", path)
            return await self.analyze_text(
                f"Fayl: {path.name}\nMIME: {detected_mime}\nSavol: {question}\nXato: {exc}"
            )

    async def summarize_messages(self, messages: list[dict]) -> str:
        if not messages:
            return "Xabarlar topilmadi."
        lines = [
            f"[{m.get('timestamp')}] {m.get('sender_name') or 'Noma\\'lum'}: {m.get('text') or '[media]'}"
            for m in messages
        ]
        prompt = "\n\n".join([
            "Quyidagi yozishmani rahbar uchun qisqa briefing ko'rinishida o'zbek tilida xulosalang.",
            "Asosiy mavzular, qarorlar, xavflar va keyingi qadamlarni alohida ko'rsating.",
            "\n".join(lines)[:18000],
        ])
        return await self._generate_text(prompt, fallback=self._fallback_summary("\n".join(lines)))

    async def smart_reply(self, context: str, tone: str = "friendly") -> str:
        prompt = "\n\n".join([
            "Siz Telegram yozishmalari uchun tabiiy javob yozuvchi assistantsiz.",
            f"Ohang: {tone}",
            "Quyidagi kontekst asosida bitta tayyor javob yozing. O'zbek tilida, qisqa va tabiiy bo'lsin.",
            context.strip(),
        ])
        return await self._generate_text(prompt, fallback="Rahmat, ma'lumotni oldim. Tez orada javob beraman.")

    async def translate(self, text: str, target_lang: str = "uz") -> str:
        prompt = "\n\n".join([
            f"Quyidagi matnni {target_lang} tiliga aniq va tabiiy tarjima qiling.",
            "Faqat tayyor tarjimani qaytaring.",
            text.strip(),
        ])
        return await self._generate_text(prompt, fallback=text)

    async def generate_daily_report(self, events: list[str]) -> str:
        prompt = "\n\n".join([
            "Quyidagi kundalik statistikalar va voqealardan rahbar uchun chiroyli, aniq, o'zbekcha hisobot tuzing.",
            "Format: umumiy holat, asosiy ko'rsatkichlar, xavflar, tavsiyalar.",
            "\n".join(events),
        ])
        return await self._generate_text(prompt, fallback="\n".join(events))

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _generate_text(self, prompt: str, fallback: str) -> str:
        if not self.enabled:
            return fallback
        try:
            return await asyncio.to_thread(self._generate_text_sync, prompt)
        except Exception:
            logger.exception("Gemini text generation failed.")
            return fallback

    def _generate_text_sync(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        text = self._extract_response_text(response)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text

    def _analyze_file_sync(self, path: Path, mime_type: str, question: str) -> str:
        uploaded = self._client.files.upload(
            file=str(path),
            config={"mime_type": mime_type},
        )
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[
                    uploaded,
                    (
                        "Quyidagi faylni o'zbek tilida tahlil qiling. "
                        "Asosiy ma'lumotlar, sonlar, trendlar va amaliy tavsiyalarni yozing.\n"
                        f"Savol: {question}"
                    ),
                ],
            )
            text = self._extract_response_text(response)
            if not text:
                raise RuntimeError("Gemini file analysis returned an empty response.")
            return text
        finally:
            try:
                self._client.files.delete(name=uploaded.name)
            except Exception:
                logger.warning("Failed to delete Gemini file '{}'.", getattr(uploaded, "name", "?"))

    @staticmethod
    def _extract_response_text(response) -> str:
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
        return "\n".join(p for p in parts if p).strip()

    @staticmethod
    def _fallback_summary(text: str) -> str:
        cleaned = " ".join(text.split())
        if not cleaned:
            return "Tahlil uchun matn topilmadi."
        excerpt = cleaned[:600]
        return (
            "Gemini mavjud emas yoki javob bermadi. Quyidagi qisqa xulosa tayyorlandi:\n"
            f"• Mazmun: {excerpt}\n"
            "• Tavsiya: muhim raqamlar va vazifalarni qo'lda tekshirib chiqing."
        )
