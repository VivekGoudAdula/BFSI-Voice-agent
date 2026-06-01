"""Orchestrate language detection, prompts, voices, and runtime agent configuration."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.config.languages import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    normalize_language_code,
)
from app.models.agent import AgentConfig
from app.models.language import (
    AgentLanguageSettings,
    AgentPromptTranslation,
    LanguageDetectionResult,
    VoiceLanguageConfig,
)
from app.agents.loader import AgentLoader
from app.repositories.language_repository import LanguageRepository
from app.services.language_detection_service import LanguageDetectionService

logger = logging.getLogger(__name__)

LANGUAGE_SWITCH_ACK: dict[str, str] = {
    "en": "Sure, I will continue in English.",
    "hi": "जी, अब मैं हिंदी में बात करूँगा।",
}

INITIAL_HELLO = "Hello."

# Ready-to-speak scripts (no LLM) — fast TTS after language detection
CANNED_GREETING_HI = (
    "नमस्ते, मैं {bank} से बोल रहा हूँ। "
    "क्या मैं {name} जी से बात कर रहा हूँ?"
)
CANNED_GREETING_EN = (
    "Good afternoon. This is {bank} calling about your EMI reminder. "
    "Am I speaking with {name}?"
)

# Romanized / misheard Hindi cues (STT often returns Latin for Hindi speech)
ROMANIZED_HINDI_HINTS = (
    "kaun",
    "koun",
    "kon ho",
    "kon hai",
    "aap kaun",
    "ap kaun",
    "aap kon",
    "namaste",
    "kaise ho",
    "kya hai",
    "boliye",
    "bolo",
    "hindi",
    "mein baat",
    "me baat",
    "baath",
    "baat kar",
    "sakthe",
    "sakte",
    "हिंदी",
)

OPENING_DISCLOSURE: dict[str, str] = {
    "en": "This call may be recorded for quality purposes.",
    "hi": "यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा सकती है।",
}


class LanguageManager:
    """
    Central multilingual coordinator for live calls.

    Responsibilities: detect language, load prompts/voices, configure agent runtime.
    """

    def __init__(
        self,
        repository: LanguageRepository | None = None,
        detection_service: LanguageDetectionService | None = None,
        agent_loader: AgentLoader | None = None,
    ) -> None:
        self._repo = repository or LanguageRepository()
        self._detection = detection_service or LanguageDetectionService(self._repo)
        self._loader = agent_loader

    def get_agent_language_settings(self, agent_doc: dict[str, Any]) -> AgentLanguageSettings:
        supported = agent_doc.get("supported_languages") or [agent_doc.get("language", "en")]
        default = agent_doc.get("default_language") or agent_doc.get("language", "en")
        voice_configs_raw = agent_doc.get("voice_configs") or []
        voice_configs: list[VoiceLanguageConfig] = []
        if voice_configs_raw:
            for vc in voice_configs_raw:
                if isinstance(vc, dict):
                    voice_configs.append(VoiceLanguageConfig(**vc))
        else:
            base_voice = agent_doc.get("voice_id", "")
            if base_voice:
                voice_configs.append(
                    VoiceLanguageConfig(language=default, voice_id=base_voice)
                )
        return AgentLanguageSettings(
            supported_languages=supported,
            default_language=default,
            voice_configs=voice_configs,
        )

    def store_customer_language(
        self, customer_id: str, language: str, confidence: float = 0.9
    ) -> None:
        self._detection.store_preference(customer_id, language, confidence)

    @staticmethod
    def is_india_phone(phone: str) -> bool:
        digits = re.sub(r"\D", "", phone or "")
        return digits.startswith("91") and len(digits) >= 10

    @staticmethod
    def _is_india_phone(phone: str) -> bool:
        return LanguageManager.is_india_phone(phone)

    @staticmethod
    def _looks_clearly_english(text: str) -> bool:
        lower = text.lower()
        words = re.findall(r"[a-z']+", lower)
        if len(words) >= 6:
            return True
        if re.search(r"\b(yes|yeah|yep|correct|right|speaking)\b", lower):
            return True
        if re.search(r"\b(i\s+am|this\s+is|that's\s+me)\b", lower):
            return True
        markers = (
            "please",
            "thank",
            "english",
            "continue",
            "payment",
            "loan",
            "emi",
            "account",
            "yes i",
            "speak english",
        )
        return any(marker in lower for marker in markers)

    @staticmethod
    def _looks_like_stt_garbage(text: str) -> bool:
        """Phone Hindi often transcribed as nonsense English (e.g. '$20. I was done with')."""
        lower = text.lower()
        if re.search(r"\$\d+", text):
            return True
        garbage = ("done with", "was done", "i was done", "twenty dollar")
        return any(phrase in lower for phrase in garbage)

    @staticmethod
    def _has_devanagari(text: str) -> bool:
        return any(0x0900 <= ord(ch) <= 0x097F for ch in text)

    @classmethod
    def format_transcript_log(
        cls,
        text: str,
        *,
        active_language: str = "en",
        resolved_language: str | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Build log line + extras; use Devanagari labels when conversation is Hindi."""
        lang = resolved_language or active_language
        extras: dict[str, str] = {"active_language": lang}
        if lang != "hi":
            return (f"User said: {text[:120]}", extras)

        display = text
        if cls._has_devanagari(text):
            pass
        elif cls._detection_static_hindi_request(text):
            display = "क्या आप हिंदी में बात कर सकते हैं?"
            extras["transcript_raw"] = text[:120]
        elif cls._looks_like_stt_garbage(text):
            display = "क्या आप हिंदी में बात कर सकते हैं? (STT गलत)"
            extras["transcript_raw"] = text[:120]

        return (f"ग्राहक ने कहा: {display[:120]}", extras)

    @staticmethod
    def _detection_static_hindi_request(text: str) -> bool:
        lower = text.lower()
        if "hindi" in lower:
            return True
        return LanguageManager._likely_hindi_from_romanized(text)

    @staticmethod
    def _likely_hindi_from_romanized(text: str) -> bool:
        lower = text.lower()
        if any(hint in lower for hint in ROMANIZED_HINDI_HINTS):
            return True
        words = re.findall(r"[a-z']+", lower)
        # Common STT mishearing of "आप कौन हैं" → "phone who up" / "hello who"
        if "who" in words and len(words) <= 6:
            return True
        return False

    def resolve_language_from_first_utterance(
        self,
        text: str,
        agent_doc: dict[str, Any],
        current_language: str,
        customer_phone: str = "",
    ) -> tuple[str, AgentConfig]:
        """
        Pick conversation language from the customer's first reply after "Hello".

        Uses script detection, explicit switch phrases, and Deepgram transcript content.
        """
        settings = self.get_agent_language_settings(agent_doc)
        supported = settings.supported_languages

        detection = self._detection.detect_language(
            text,
            supported=supported,
            previous_language=current_language,
        )

        has_devanagari = any(0x0900 <= ord(ch) <= 0x097F for ch in text)
        lower = text.lower()
        india_customer = self._is_india_phone(customer_phone)

        if detection.switch_requested and detection.language in supported:
            lang = detection.language
        elif has_devanagari and "hi" in supported:
            lang = "hi"
        elif self._likely_hindi_from_romanized(text) and "hi" in supported:
            lang = "hi"
        elif detection.language == "hi" and detection.confidence >= 0.5 and "hi" in supported:
            lang = "hi"
        elif (
            india_customer
            and "hi" in supported
            and (
                self._looks_like_stt_garbage(text)
                or (
                    not self._looks_clearly_english(text)
                    and (
                        self._likely_hindi_from_romanized(text)
                        or re.search(
                            r"\b(call|phone).{0,12}\b(home|who|connor)\b", lower
                        )
                    )
                )
            )
        ):
            lang = "hi"
            logger.info(
                "India caller — Hindi selected (STT=%r)",
                text[:80],
            )
        elif (
            india_customer
            and "hi" in supported
            and not self._looks_clearly_english(text)
        ):
            lang = "hi"
            logger.info(
                "India caller — default Hindi for ambiguous first reply (STT=%r)",
                text[:80],
            )
        elif detection.language in supported and detection.confidence >= 0.6:
            lang = detection.language
        else:
            lang = normalize_language_code(current_language, supported) or "en"

        config = self.configure_runtime(agent_doc, lang)
        return lang, config

    def build_intro_after_hello(
        self,
        language: str,
        agent_config: AgentConfig,
        bank_name: str,
        *,
        customer_name: str = "",
        agent_context: dict[str, Any] | None = None,
        user_first_utterance: str = "",
    ) -> str:
        """Localized canned intro after Hello — fast TTS, no LLM round-trip."""
        disclosure = OPENING_DISCLOSURE.get(language, OPENING_DISCLOSURE["en"])
        name = customer_name or ("जी" if language == "hi" else "Sir")

        if language == "hi":
            greeting = CANNED_GREETING_HI.format(bank=bank_name, name=name)
            return f"{greeting} {disclosure}".strip()

        greeting = CANNED_GREETING_EN.format(bank=bank_name, name=name)
        return f"{greeting} {disclosure}".strip()

    def resolve_initial_language(
        self,
        agent_doc: dict[str, Any],
        customer_id: str,
    ) -> str:
        settings = self.get_agent_language_settings(agent_doc)
        stored = self._detection.get_stored_preference(customer_id)
        if stored and stored in settings.supported_languages:
            return stored
        default = normalize_language_code(
            settings.default_language, settings.supported_languages
        )
        return default or DEFAULT_LANGUAGE

    def configure_runtime(
        self,
        agent_doc: dict[str, Any],
        language: str,
    ) -> AgentConfig:
        """Build AgentConfig with localized prompt and voice for the active language."""
        if not self._loader:
            raise RuntimeError("LanguageManager requires AgentLoader injection")

        settings = self.get_agent_language_settings(agent_doc)
        lang = normalize_language_code(language, settings.supported_languages)
        if not lang:
            lang = settings.default_language

        localized_doc = dict(agent_doc)
        translation = self._repo.get_prompt_translation(agent_doc["agent_id"], lang)
        if translation:
            localized_doc["system_prompt"] = translation.system_prompt
            if translation.greeting_template:
                localized_doc["greeting_template"] = translation.greeting_template
            if translation.escalation_message:
                localized_doc["escalation_message"] = translation.escalation_message
            if translation.unavailable_info_message:
                localized_doc["unavailable_info_message"] = (
                    translation.unavailable_info_message
                )
        localized_doc["language"] = lang

        voice_id = self.resolve_voice_id(settings, lang, agent_doc.get("voice_id", ""))
        localized_doc["voice_id"] = voice_id

        runtime = self._loader.build_from_document(localized_doc)
        config = runtime.to_agent_config()
        config.language_code = lang
        config.language = SUPPORTED_LANGUAGES.get(lang, lang)
        config.supported_languages = list(settings.supported_languages)
        config.default_language = settings.default_language
        return config

    def resolve_voice_id(
        self,
        settings: AgentLanguageSettings,
        language: str,
        fallback: str,
    ) -> str:
        for vc in settings.voice_configs:
            if vc.language == language and vc.voice_id:
                return vc.voice_id
        for vc in settings.voice_configs:
            if vc.language == settings.default_language and vc.voice_id:
                return vc.voice_id
        return fallback

    def process_transcript(
        self,
        *,
        text: str,
        agent_doc: dict[str, Any],
        customer_id: str,
        call_id: str,
        call_sid: str,
        current_language: str,
    ) -> tuple[LanguageDetectionResult, Optional[AgentConfig], Optional[str]]:
        """
        Analyze transcript; return detection, optional new AgentConfig, optional ack message.

        If language switches, returns updated config and a short acknowledgment to speak.
        """
        settings = self.get_agent_language_settings(agent_doc)
        supported = settings.supported_languages

        detection = self._detection.detect_language(
            text,
            supported=supported,
            previous_language=current_language,
        )

        target = detection.language
        if detection.switch_requested:
            trigger = "explicit_request"
        elif (
            detection.confidence >= 0.7
            and target != current_language
            and len(text.strip()) >= 8
        ):
            trigger = "auto"
        else:
            if detection.confidence >= 0.6:
                self._detection.store_preference(
                    customer_id, current_language, detection.confidence
                )
            return detection, None, None

        if target == current_language:
            return detection, None, None

        if target not in supported:
            return detection, None, None

        self._apply_switch(
            agent_id=agent_doc["agent_id"],
            customer_id=customer_id,
            call_id=call_id,
            call_sid=call_sid,
            from_language=current_language,
            to_language=target,
            trigger=trigger if detection.switch_requested else "auto",
        )

        new_config = self.configure_runtime(agent_doc, target)
        ack = LANGUAGE_SWITCH_ACK.get(target) if detection.switch_requested else None
        return detection, new_config, ack

    def _apply_switch(
        self,
        *,
        agent_id: str,
        customer_id: str,
        call_id: str,
        call_sid: str,
        from_language: str,
        to_language: str,
        trigger: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._detection.store_preference(customer_id, to_language, 0.99)
        self._repo.record_language_switch(
            {
                "call_id": call_id,
                "call_sid": call_sid,
                "agent_id": agent_id,
                "customer_id": customer_id,
                "from_language": from_language,
                "to_language": to_language,
                "trigger": trigger,
                "timestamp": now,
            }
        )
        self._repo.increment_language_call_stats(
            agent_id, to_language, switched=True
        )
        logger.info(
            "Language switch %s → %s | call=%s trigger=%s",
            from_language,
            to_language,
            call_id,
            trigger,
        )

    def initialize_call_session(
        self,
        session: Any,
        agent_doc: dict[str, Any],
        *,
        customer_name: str,
        agent_context: dict[str, Any] | None = None,
    ) -> str:
        """Set initial language, localized agent config, and greeting on session start."""
        from app.agents.engine import AgentEngine

        lang = self.resolve_initial_language(agent_doc, session.customer_id)
        session.active_language = lang
        session.agent_config = self.configure_runtime(agent_doc, lang)

        engine = AgentEngine()
        greeting = engine.build_greeting(
            session.agent_config, customer_name, agent_context
        )
        session.pending_greeting = greeting
        if session.messages:
            for msg in reversed(session.messages):
                if msg.get("role") == "assistant":
                    msg["content"] = greeting
                    break
        return lang

    def save_agent_languages(
        self,
        agent_id: str,
        settings: AgentLanguageSettings,
        translations: list[AgentPromptTranslation],
    ) -> None:
        if translations:
            self._repo.upsert_prompt_translations(agent_id, translations)

    def get_agent_languages_response(
        self, agent_doc: dict[str, Any]
    ) -> dict[str, Any]:
        settings = self.get_agent_language_settings(agent_doc)
        translations = self._repo.list_prompt_translations(agent_doc["agent_id"])
        return {
            "agent_id": agent_doc["agent_id"],
            "supported_languages": settings.supported_languages,
            "default_language": settings.default_language,
            "voice_configs": [vc.model_dump() for vc in settings.voice_configs],
            "prompt_translations": [t.model_dump() for t in translations],
        }
