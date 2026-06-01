"""Orchestrate language detection, prompts, voices, and runtime agent configuration."""

import logging
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
    "en": "Of course. I will continue in English.",
    "hi": "ज़रूर। अब मैं हिंदी में बात करूँगा।",
    "te": "తప్పకుండా. నేను ఇప్పుడు తెలుగులో మాట్లాడతాను.",
    "ta": "நிச்சயமாக. இப்போது நான் தமிழில் பேசுகிறேன்.",
    "kn": "ಖಂಡಿತ. ನಾನು ಈಗ ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ.",
    "mr": "नक्की. आता मी मराठीत बोलेन.",
    "bn": "অবশ্যই। এখন আমি বাংলায় কথা বলব।",
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
