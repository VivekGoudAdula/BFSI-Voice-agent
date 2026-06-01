"""TTS provider selection (Sarvam or ElevenLabs)."""

from typing import Protocol, runtime_checkable

from app.core.config import Settings, get_settings
from app.services.elevenlabs_service import ElevenLabsService
from app.services.sarvam_service import SarvamService


@runtime_checkable
class TextToSpeechProvider(Protocol):
    async def generate_response_audio(
        self,
        text: str,
        voice_id: str | None = None,
        language_code: str = "en",
    ) -> bytes: ...


class TextToSpeechService:
    """Delegates to Sarvam or ElevenLabs based on configuration."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        provider = self._settings.tts_provider.strip().lower()
        if provider == "elevenlabs":
            self._backend: TextToSpeechProvider = ElevenLabsService(self._settings)
            self.provider_name = "elevenlabs"
        else:
            self._backend = SarvamService(self._settings)
            self.provider_name = "sarvam"

    async def generate_response_audio(
        self,
        text: str,
        voice_id: str | None = None,
        language_code: str = "en",
    ) -> bytes:
        return await self._backend.generate_response_audio(
            text,
            voice_id=voice_id,
            language_code=language_code,
        )
