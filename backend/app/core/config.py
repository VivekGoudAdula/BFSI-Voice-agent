"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the voice agent platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_sms_number: str = ""

    # Text-to-speech (sarvam | elevenlabs)
    tts_provider: str = "sarvam"

    # Sarvam AI (Bulbul v3) — default until ElevenLabs Pro voices are available
    sarvam_api_key: str = ""
    sarvam_model: str = "bulbul:v3"
    sarvam_speaker_default: str = "ashutosh"
    sarvam_speaker_en: str = "ashutosh"
    sarvam_speaker_hi: str = "ashutosh"
    sarvam_pace: float = 1.1

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    elevenlabs_auto_fallback_voice: bool = True

    # Deepgram (streaming STT)
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    # Use "multi" for Hindi+English calls (nova-2); "hi" or "en" for single language
    deepgram_language: str = "multi"

    # Groq (LLM)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fallback_model: str = "llama-3.1-8b-instant"
    groq_voice_max_tokens: int = 50

    # Conversation
    bank_name: str = "ABC Bank"
    payment_link_base_url: str = "https://abc-bank.com/pay"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "voice_agent"

    # Campaign Engine (Phase 6)
    campaign_batch_size: int = 10
    campaign_call_interval_seconds: float = 5.0
    campaign_max_concurrent_calls: int = 50

    # Human Handoff (Phase 7)
    human_agent_phone: str = ""
    handoff_enabled: bool = True

    # Compliance & Audit (Phase 8)
    compliance_enabled: bool = True
    # Shorter phone opener (disclosure + consent in one brief line)
    compliance_brief_mode: bool = True
    # Say "Hello" first, detect language from customer's reply, then continue in that language
    compliance_language_first_flow: bool = True
    compliance_disclosure_template: str = (
        "Hello. I am an AI-powered virtual assistant calling on behalf of {bank_name}."
    )
    compliance_consent_prompt: str = (
        "Do I have your permission to continue this conversation?"
    )
    compliance_recording_notice: str = (
        "This call may be monitored and recorded for quality and compliance purposes."
    )
    compliance_consent_timeout_seconds: float = 30.0
    compliance_retention_transcripts_days: int = 2555
    compliance_retention_audit_logs_days: int = 2555
    compliance_retention_recordings_days: int = 2555
    compliance_retention_consent_days: int = 2555
    compliance_retention_disclosure_days: int = 2555
    compliance_retention_tool_audit_days: int = 2555
    compliance_retention_crm_audit_days: int = 2555
    compliance_retention_escalation_days: int = 2555
    compliance_retention_events_days: int = 2555

    # Application
    base_url: str = "http://localhost:8000"
    audio_storage_path: str = "./storage/audio"
    log_level: str = "INFO"
    seed_on_startup: bool = True

    @property
    def audio_dir(self) -> Path:
        """Resolved absolute path for generated audio files."""
        path = Path(self.audio_storage_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent.parent / path
        return path

    @property
    def websocket_base_url(self) -> str:
        """WebSocket base URL derived from BASE_URL (http→ws, https→wss)."""
        base = self.base_url.rstrip("/")
        if base.startswith("https://"):
            return "wss://" + base[len("https://") :]
        if base.startswith("http://"):
            return "ws://" + base[len("http://") :]
        return f"wss://{base}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for dependency injection."""
    return Settings()
