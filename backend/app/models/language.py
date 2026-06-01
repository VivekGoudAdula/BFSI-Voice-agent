"""Multilingual support domain models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class VoiceLanguageConfig(BaseModel):
    """ElevenLabs voice mapping per language."""

    language: str = Field(..., min_length=2, max_length=5)
    voice_id: str = Field(..., min_length=1)


class AgentLanguageSettings(BaseModel):
    """Per-agent multilingual configuration."""

    supported_languages: list[str] = Field(
        default_factory=lambda: ["en", "hi", "te", "ta", "kn", "mr", "bn"]
    )
    default_language: str = "en"
    voice_configs: list[VoiceLanguageConfig] = Field(default_factory=list)


class AgentPromptTranslation(BaseModel):
    """Localized prompt content for an agent."""

    agent_id: str
    language: str
    system_prompt: str
    greeting_template: str = ""
    escalation_message: str = ""
    unavailable_info_message: str = ""
    language_instruction: str = ""


class CustomerLanguagePreference(BaseModel):
    """Stored customer language preference."""

    id: Optional[str] = None
    customer_id: str
    language: str
    confidence: float = 0.0
    updated_at: Optional[datetime] = None


class LanguageDetectionResult(BaseModel):
    """Output from language detection."""

    language: str
    confidence: float
    is_code_mixed: bool = False
    detected_scripts: dict[str, int] = Field(default_factory=dict)
    switch_requested: bool = False
    previous_language: str = ""


class AgentLanguagesResponse(BaseModel):
    """GET /agents/{id}/languages response."""

    agent_id: str
    supported_languages: list[str]
    default_language: str
    voice_configs: list[VoiceLanguageConfig]
    prompt_translations: list[AgentPromptTranslation] = Field(default_factory=list)


class AgentLanguagesUpdateRequest(BaseModel):
    """POST /agents/{id}/languages request body."""

    supported_languages: list[str] = Field(min_length=1)
    default_language: str = "en"
    voice_configs: list[VoiceLanguageConfig] = Field(default_factory=list)
    prompt_translations: list[AgentPromptTranslation] = Field(default_factory=list)


class LanguageSwitchEvent(BaseModel):
    """Recorded when customer switches language mid-call."""

    call_id: str
    call_sid: str
    agent_id: str
    customer_id: str
    from_language: str
    to_language: str
    trigger: str = "auto"  # auto | explicit_request
    timestamp: Optional[datetime] = None


class LanguageAnalyticsSummary(BaseModel):
    """Aggregated multilingual analytics."""

    calls_by_language: dict[str, int] = Field(default_factory=dict)
    language_distribution: dict[str, float] = Field(default_factory=dict)
    language_switch_events: int = 0
    language_success_rate: dict[str, float] = Field(default_factory=dict)
    total_calls: int = 0
