"""Sarvam AI text-to-speech integration (Bulbul v3)."""

import json
import logging
import time
import uuid
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.exceptions import SarvamServiceError
from app.core.logging_config import log_with_context

logger = logging.getLogger(__name__)

SARVAM_TTS_STREAM_URL = "https://api.sarvam.ai/text-to-speech/stream"

# ISO 639-1 → Sarvam BCP-47 language codes
SARVAM_LANGUAGE_CODES: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
}

# Bulbul v3 speaker names (lowercase)
SARVAM_SPEAKERS: frozenset[str] = frozenset(
    {
        "anushka",
        "abhilash",
        "manisha",
        "vidya",
        "arya",
        "karun",
        "hitesh",
        "aditya",
        "ritu",
        "priya",
        "neha",
        "rahul",
        "pooja",
        "rohan",
        "simran",
        "kavya",
        "amit",
        "dev",
        "ishita",
        "shreya",
        "ratan",
        "varun",
        "manan",
        "sumit",
        "roopa",
        "kabir",
        "aayan",
        "shubh",
        "ashutosh",
        "advait",
        "anand",
        "tanya",
        "tarun",
        "sunny",
        "mani",
        "gokul",
        "vijay",
        "shruti",
        "suhani",
        "mohit",
        "kavitha",
        "rehan",
        "soham",
        "rupali",
    }
)


def _parse_api_error(response_text: str) -> str:
    try:
        body = json.loads(response_text)
        if isinstance(body, dict):
            for key in ("message", "error", "detail"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
    except json.JSONDecodeError:
        pass
    return response_text[:500]


class SarvamService:
    """Generates speech audio via the Sarvam AI streaming TTS API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.sarvam_api_key
        self._model = settings.sarvam_model
        self._pace = settings.sarvam_pace
        self._default_speaker = settings.sarvam_speaker_default
        self._speakers_by_lang = {
            "en": settings.sarvam_speaker_en,
            "hi": settings.sarvam_speaker_hi,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "api-subscription-key": self._api_key,
            "Content-Type": "application/json",
        }

    def _target_language_code(self, language_code: str) -> str:
        normalized = (language_code or "en").strip().lower()[:2]
        return SARVAM_LANGUAGE_CODES.get(normalized, SARVAM_LANGUAGE_CODES["en"])

    def _resolve_speaker(self, language_code: str, voice_id: str | None) -> str:
        normalized = (language_code or "en").strip().lower()[:2]
        fallback = self._speakers_by_lang.get(normalized) or self._default_speaker

        if not voice_id or not voice_id.strip():
            return fallback

        candidate = voice_id.strip().lower()
        if candidate in SARVAM_SPEAKERS:
            return candidate

        # Agents/DB often store ElevenLabs voice IDs — ignore and use Sarvam defaults
        logger.warning(
            "Ignoring non-Sarvam voice %r; using speaker %r for language %s",
            voice_id.strip(),
            fallback,
            normalized,
        )
        return fallback

    def _build_payload(
        self,
        text: str,
        *,
        language_code: str,
        voice_id: str | None,
        output_audio_codec: str,
        speech_sample_rate: int,
    ) -> dict:
        return {
            "text": text,
            "target_language_code": self._target_language_code(language_code),
            "speaker": self._resolve_speaker(language_code, voice_id),
            "model": self._model,
            "pace": self._pace,
            "speech_sample_rate": speech_sample_rate,
            "output_audio_codec": output_audio_codec,
            "enable_preprocessing": True,
        }

    async def _stream_audio(self, payload: dict) -> bytes:
        if not self._api_key:
            raise SarvamServiceError("SARVAM_API_KEY must be configured")

        chunks: list[bytes] = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    SARVAM_TTS_STREAM_URL,
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        detail = _parse_api_error(body.decode(errors="replace"))
                        raise SarvamServiceError(detail)

                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            chunks.append(chunk)
        except SarvamServiceError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = _parse_api_error(exc.response.text) if exc.response else str(exc)
            raise SarvamServiceError(detail) from exc
        except httpx.RequestError as exc:
            raise SarvamServiceError(str(exc)) from exc

        audio_bytes = b"".join(chunks)
        if not audio_bytes:
            raise SarvamServiceError("Sarvam returned empty audio")
        return audio_bytes

    async def generate_audio(
        self,
        text: str,
        voice_id: str | None = None,
        language_code: str = "en",
    ) -> tuple[str, Path]:
        """Generate MP3 speech and persist to local storage."""
        payload = self._build_payload(
            text,
            language_code=language_code,
            voice_id=voice_id,
            output_audio_codec="mp3",
            speech_sample_rate=22050,
        )

        log_with_context(
            logger,
            logging.INFO,
            f"Generating audio via Sarvam model={self._model}",
            event="audio_generation_started",
        )

        start = time.perf_counter()
        audio_bytes = await self._stream_audio(payload)
        latency_ms = (time.perf_counter() - start) * 1000

        audio_dir = self._settings.audio_dir
        audio_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.mp3"
        file_path = audio_dir / filename
        file_path.write_bytes(audio_bytes)

        log_with_context(
            logger,
            logging.INFO,
            f"Audio saved to {filename}",
            sarvam_ms=round(latency_ms, 1),
            event="audio_generation_completed",
        )
        return filename, file_path

    async def generate_response_audio(
        self,
        text: str,
        voice_id: str | None = None,
        language_code: str = "en",
    ) -> bytes:
        """
        Generate telephony-ready mulaw 8 kHz audio for Twilio Media Streams.

        Returns:
            Raw mulaw audio bytes.
        """
        payload = self._build_payload(
            text,
            language_code=language_code,
            voice_id=voice_id,
            output_audio_codec="mulaw",
            speech_sample_rate=8000,
        )

        log_with_context(
            logger,
            logging.INFO,
            "Generating conversational audio via Sarvam",
            event="conversational_tts_started",
        )

        start = time.perf_counter()
        try:
            audio_bytes = await self._stream_audio(payload)
        except SarvamServiceError as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Sarvam conversational TTS error: {exc}",
                event="conversational_tts_failed",
            )
            raise

        latency_ms = (time.perf_counter() - start) * 1000
        log_with_context(
            logger,
            logging.INFO,
            f"Conversational audio generated ({len(audio_bytes)} bytes)",
            sarvam_ms=round(latency_ms, 1),
            event="conversational_tts_completed",
        )
        return audio_bytes
