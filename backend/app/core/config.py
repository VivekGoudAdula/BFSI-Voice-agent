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

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    elevenlabs_auto_fallback_voice: bool = True

    # Deepgram (streaming STT)
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"

    # Groq (LLM)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Conversation
    bank_name: str = "ABC Bank"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "voice_agent"

    # Application
    base_url: str = "http://localhost:8000"
    audio_storage_path: str = "./storage/audio"
    log_level: str = "INFO"

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
