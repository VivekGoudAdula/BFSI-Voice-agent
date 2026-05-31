"""ElevenLabs text-to-speech integration."""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ElevenLabsServiceError
from app.core.logging_config import log_with_context

logger = logging.getLogger(__name__)

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_TTS_URL = f"{ELEVENLABS_BASE_URL}/text-to-speech/{{voice_id}}"

# Default premade voice (Rachel) — available on ElevenLabs free tier via API
DEFAULT_FREE_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def _parse_api_error(response_text: str) -> str:
    """Extract a readable message from ElevenLabs error JSON."""
    try:
        body = json.loads(response_text)
        detail = body.get("detail")
        if isinstance(detail, dict):
            return detail.get("message", response_text)
        if isinstance(detail, str):
            return detail
    except json.JSONDecodeError:
        pass
    return response_text[:500]


class ElevenLabsService:
    """Generates speech audio via the ElevenLabs API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.elevenlabs_api_key
        self._voice_id = settings.elevenlabs_voice_id
        self._model_id = settings.elevenlabs_model_id

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "xi-api-key": self._api_key,
        }

    @staticmethod
    def is_voice_api_usable_on_free(voice: dict[str, Any]) -> bool:
        """Return True if a voice can be used via API on the free tier."""
        category = voice.get("category", "")
        if category == "premade":
            return True
        if category in {"cloned", "generated"} and voice.get("is_owner"):
            return True
        tiers = voice.get("available_for_tiers") or []
        return "free" in tiers

    async def list_voices(self) -> list[dict[str, Any]]:
        """List voices on the account, flagged for free-tier API use."""
        if not self._api_key:
            raise ElevenLabsServiceError("ELEVENLABS_API_KEY must be configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ELEVENLABS_BASE_URL}/voices",
                headers=self._headers(),
                params={"show_legacy": "true"},
            )
            response.raise_for_status()
            voices = response.json().get("voices", [])

        return [
            {
                "voice_id": voice["voice_id"],
                "name": voice.get("name", ""),
                "category": voice.get("category", ""),
                "available_for_tiers": voice.get("available_for_tiers", []),
                "api_usable_on_free": self.is_voice_api_usable_on_free(voice),
            }
            for voice in voices
        ]

    async def _get_voice(self, client: httpx.AsyncClient, voice_id: str) -> dict[str, Any] | None:
        response = await client.get(
            f"{ELEVENLABS_BASE_URL}/voices/{voice_id}",
            headers=self._headers(),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def _resolve_voice_id(self, client: httpx.AsyncClient) -> str:
        """Pick a voice that works on the free-tier API."""
        preferred = self._voice_id or DEFAULT_FREE_VOICE_ID
        voice = await self._get_voice(client, preferred)

        if voice and self.is_voice_api_usable_on_free(voice):
            return preferred

        if voice:
            logger.warning(
                "Configured voice %s (%s) is not available on free API tier",
                preferred,
                voice.get("name", "unknown"),
            )

        if not self._settings.elevenlabs_auto_fallback_voice:
            raise ElevenLabsServiceError(
                f"Voice '{preferred}' cannot be used on the free API tier. "
                "Use a premade voice (e.g. Rachel: 21m00Tcm4TlvDq8ikWAM) or set "
                "ELEVENLABS_AUTO_FALLBACK_VOICE=true. See GET /elevenlabs/voices."
            )

        all_voices = (await client.get(
            f"{ELEVENLABS_BASE_URL}/voices",
            headers=self._headers(),
            params={"show_legacy": "true"},
        )).json().get("voices", [])

        for candidate in all_voices:
            if self.is_voice_api_usable_on_free(candidate):
                fallback_id = candidate["voice_id"]
                logger.warning(
                    "Falling back to free API voice: %s (%s)",
                    candidate.get("name", fallback_id),
                    fallback_id,
                )
                return fallback_id

        return DEFAULT_FREE_VOICE_ID

    async def generate_audio(self, text: str) -> tuple[str, Path]:
        """
        Generate speech from text and persist to local storage.

        Returns:
            Tuple of (filename, absolute file path).
        """
        if not self._api_key:
            raise ElevenLabsServiceError("ELEVENLABS_API_KEY must be configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            voice_id = await self._resolve_voice_id(client)

            url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
            headers = {
                **self._headers(),
                "Accept": "audio/mpeg",
            }
            payload = {
                "text": text,
                "model_id": self._model_id,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            }

            log_with_context(
                logger,
                logging.INFO,
                f"Generating audio via ElevenLabs model={self._model_id} voice={voice_id}",
                event="audio_generation_started",
            )

            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                audio_bytes = response.content
            except httpx.HTTPStatusError as exc:
                detail = _parse_api_error(exc.response.text) if exc.response else str(exc)
                log_with_context(
                    logger,
                    logging.ERROR,
                    f"ElevenLabs API HTTP error: {detail}",
                    event="audio_generation_failed",
                )
                raise ElevenLabsServiceError(detail) from exc
            except httpx.RequestError as exc:
                log_with_context(
                    logger,
                    logging.ERROR,
                    f"ElevenLabs request failed: {exc}",
                    event="audio_generation_failed",
                )
                raise ElevenLabsServiceError(str(exc)) from exc

        audio_dir = self._settings.audio_dir
        audio_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid.uuid4().hex}.mp3"
        file_path = audio_dir / filename
        file_path.write_bytes(audio_bytes)

        log_with_context(
            logger,
            logging.INFO,
            f"Audio saved to {filename}",
            event="audio_generation_completed",
        )

        return filename, file_path

    async def generate_response_audio(self, text: str) -> bytes:
        """
        Generate telephony-ready mulaw 8 kHz audio for real-time playback.

        Used during live conversations via Twilio Media Streams.

        Returns:
            Raw mulaw audio bytes.
        """
        if not self._api_key:
            raise ElevenLabsServiceError("ELEVENLABS_API_KEY must be configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            voice_id = await self._resolve_voice_id(client)

            url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
            headers = {
                **self._headers(),
                "Accept": "audio/basic",
            }
            payload = {
                "text": text,
                "model_id": self._model_id,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            }
            params = {
                "output_format": "ulaw_8000",
                "optimize_streaming_latency": "3",
            }

            log_with_context(
                logger,
                logging.INFO,
                "Generating conversational audio via ElevenLabs",
                event="conversational_tts_started",
            )

            start = time.perf_counter()

            try:
                response = await client.post(
                    url, json=payload, headers=headers, params=params
                )
                response.raise_for_status()
                audio_bytes = response.content
            except httpx.HTTPStatusError as exc:
                detail = _parse_api_error(exc.response.text) if exc.response else str(exc)
                log_with_context(
                    logger,
                    logging.ERROR,
                    f"ElevenLabs conversational TTS error: {detail}",
                    event="conversational_tts_failed",
                )
                raise ElevenLabsServiceError(detail) from exc
            except httpx.RequestError as exc:
                log_with_context(
                    logger,
                    logging.ERROR,
                    f"ElevenLabs request failed: {exc}",
                    event="conversational_tts_failed",
                )
                raise ElevenLabsServiceError(str(exc)) from exc

        latency_ms = (time.perf_counter() - start) * 1000

        log_with_context(
            logger,
            logging.INFO,
            f"Conversational audio generated ({len(audio_bytes)} bytes)",
            elevenlabs_ms=round(latency_ms, 1),
            event="conversational_tts_completed",
        )

        return audio_bytes
