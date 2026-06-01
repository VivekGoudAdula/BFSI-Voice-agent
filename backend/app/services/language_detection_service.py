"""Detect customer language, code-mixing, and explicit switch requests."""

import logging
import re
import unicodedata
from typing import Optional

from app.config.languages import (
    HINDI_KEYWORDS,
    LANGUAGE_SWITCH_PATTERNS,
    MARATHI_KEYWORDS,
    SCRIPT_RANGES,
    SUPPORTED_LANGUAGES,
    normalize_language_code,
)
from app.models.language import LanguageDetectionResult
from app.repositories.language_repository import LanguageRepository

logger = logging.getLogger(__name__)


class LanguageDetectionService:
    """
    Detect customer language from speech transcripts.

    Supports Indian languages, code-mixed speech (e.g. Hinglish, Telugu-English),
    and explicit language-switch requests.
    """

    def __init__(self, repository: LanguageRepository | None = None) -> None:
        self._repo = repository or LanguageRepository()

    def detect_switch_request(
        self, text: str, supported: list[str]
    ) -> Optional[str]:
        """Return target language code if customer explicitly asks to switch."""
        for pattern, lang in LANGUAGE_SWITCH_PATTERNS:
            if lang not in supported:
                continue
            if re.search(pattern, text):
                return lang
        return None

    def detect_language(
        self,
        text: str,
        *,
        supported: list[str],
        previous_language: str = "en",
    ) -> LanguageDetectionResult:
        """
        Detect dominant language from transcript text.

        Uses Unicode script analysis for Indian languages and Latin ratio for English.
        """
        switch_lang = self.detect_switch_request(text, supported)
        if switch_lang:
            return LanguageDetectionResult(
                language=switch_lang,
                confidence=0.99,
                is_code_mixed=False,
                switch_requested=True,
                previous_language=previous_language,
            )

        script_counts = self._count_scripts(text)
        latin = script_counts.get("latin", 0)
        total_chars = sum(script_counts.values()) or 1

        lang_scores: dict[str, float] = {}
        for lang, ranges in SCRIPT_RANGES.items():
            if lang not in supported or lang in ("hi", "mr"):
                continue
            count = sum(
                script_counts.get(f"{lo}-{hi}", 0) for lo, hi in ranges
            )
            if count > 0:
                lang_scores[lang] = count / total_chars

        devanagari = sum(
            script_counts.get(f"{lo}-{hi}", 0)
            for lo, hi in SCRIPT_RANGES.get("hi", [])
        )
        if devanagari > 0:
            marathi_hits = sum(1 for w in MARATHI_KEYWORDS if w in text)
            hindi_hits = sum(1 for w in HINDI_KEYWORDS if w in text)
            if "mr" in supported and marathi_hits > hindi_hits:
                lang_scores["mr"] = devanagari / total_chars
            elif "hi" in supported:
                lang_scores["hi"] = devanagari / total_chars

        if latin / total_chars > 0.5 and "en" in supported:
            lang_scores["en"] = latin / total_chars

        if not lang_scores:
            return LanguageDetectionResult(
                language=previous_language or "en",
                confidence=0.5,
                is_code_mixed=False,
                detected_scripts=script_counts,
                previous_language=previous_language,
            )

        dominant = max(lang_scores, key=lang_scores.get)
        confidence = min(0.98, lang_scores[dominant] + 0.2)
        is_mixed = len([s for s in lang_scores if lang_scores[s] > 0.15]) > 1

        if is_mixed and dominant == "en" and previous_language != "en":
            # Prefer established conversation language for light code-mixing
            dominant = previous_language
            confidence = 0.75

        if dominant not in supported:
            dominant = normalize_language_code(previous_language, supported) or "en"

        return LanguageDetectionResult(
            language=dominant,
            confidence=round(confidence, 2),
            is_code_mixed=is_mixed,
            detected_scripts=script_counts,
            previous_language=previous_language,
        )

    def store_preference(
        self, customer_id: str, language: str, confidence: float
    ) -> None:
        """Persist detected language preference for future calls."""
        if not customer_id:
            return
        self._repo.upsert_customer_preference(customer_id, language, confidence)

    def get_stored_preference(self, customer_id: str) -> Optional[str]:
        pref = self._repo.get_customer_preference(customer_id)
        return pref.language if pref else None

    @staticmethod
    def _count_scripts(text: str) -> dict[str, int]:
        counts: dict[str, int] = {"latin": 0}
        for ch in text:
            if ch.isspace() or not ch.isprintable():
                continue
            cp = ord(ch)
            if cp < 128 and ch.isalpha():
                counts["latin"] = counts.get("latin", 0) + 1
                continue
            for ranges in SCRIPT_RANGES.values():
                for lo, hi in ranges:
                    if lo <= cp <= hi:
                        key = f"{lo}-{hi}"
                        counts[key] = counts.get(key, 0) + 1
                        break
        return counts

    @staticmethod
    def describe_code_mix(language: str, is_mixed: bool) -> str:
        """Human-readable code-mix label for logging."""
        if not is_mixed:
            return SUPPORTED_LANGUAGES.get(language, language)
        if language == "hi":
            return "Hinglish"
        if language == "te":
            return "Telugu-English"
        if language == "ta":
            return "Tamil-English"
        return f"{SUPPORTED_LANGUAGES.get(language, language)}-English"
