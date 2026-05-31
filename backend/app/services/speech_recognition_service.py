"""Deepgram streaming speech-to-text integration."""

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, Optional
from urllib.parse import urlencode

import websockets
from websockets.asyncio.client import ClientConnection

from app.core.config import Settings
from app.core.exceptions import SpeechRecognitionError
from app.core.logging_config import log_with_context

logger = logging.getLogger(__name__)

FinalTranscriptHandler = Callable[[str, float], Awaitable[None]]
SpeechStartedHandler = Callable[[], Awaitable[None]]


class SpeechRecognitionService:
    """
    Streaming transcription via Deepgram Live API.

    Handles partial transcripts, final transcripts, and voice activity events.
    Only final transcripts should be forwarded to the LLM pipeline.
    """

    DEEPGRAM_WS_BASE = "wss://api.deepgram.com/v1/listen"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.deepgram_api_key
        self._model = settings.deepgram_model
        self._ws: Optional[ClientConnection] = None
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._on_final: Optional[FinalTranscriptHandler] = None
        self._on_speech_started: Optional[SpeechStartedHandler] = None
        self._last_final_at: float = 0.0
        self._utterance_start: float = 0.0

    def _build_ws_url(self) -> str:
        params = {
            "encoding": "mulaw",
            "sample_rate": "8000",
            "channels": "1",
            "model": self._model,
            "interim_results": "true",
            "utterance_end_ms": "1000",
            "vad_events": "true",
            "endpointing": "300",
            "punctuate": "true",
            "smart_format": "true",
        }
        return f"{self.DEEPGRAM_WS_BASE}?{urlencode(params)}"

    async def connect(
        self,
        on_final_transcript: FinalTranscriptHandler,
        on_speech_started: Optional[SpeechStartedHandler] = None,
    ) -> None:
        """Open a Deepgram live transcription session."""
        if not self._api_key:
            raise SpeechRecognitionError("DEEPGRAM_API_KEY must be configured")

        self._on_final = on_final_transcript
        self._on_speech_started = on_speech_started

        headers = {"Authorization": f"Token {self._api_key}"}

        try:
            self._ws = await websockets.connect(
                self._build_ws_url(),
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=2**20,
            )
        except Exception as exc:
            raise SpeechRecognitionError(f"Failed to connect to Deepgram: {exc}") from exc

        self._listener_task = asyncio.create_task(self._listen())
        log_with_context(logger, logging.INFO, "Deepgram STT connected", event="stt_connected")

    async def _listen(self) -> None:
        """Process messages from the Deepgram websocket."""
        if not self._ws:
            return

        try:
            async for raw in self._ws:
                await self._handle_message(raw)
        except websockets.ConnectionClosed:
            logger.debug("Deepgram connection closed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Deepgram listener error: {exc}",
                event="stt_error",
            )

    async def _handle_message(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = message.get("type")

        if msg_type == "SpeechStarted":
            self._utterance_start = time.perf_counter()
            if self._on_speech_started:
                await self._on_speech_started()
            return

        if msg_type != "Results":
            return

        channel = message.get("channel", {})
        alternatives = channel.get("alternatives", [])
        if not alternatives:
            return

        transcript = alternatives[0].get("transcript", "").strip()
        if not transcript:
            return

        is_final = message.get("is_final", False)
        if not is_final:
            return

        # Deduplicate rapid duplicate finals
        now = time.perf_counter()
        if now - self._last_final_at < 0.3:
            return
        self._last_final_at = now

        stt_latency_ms = (now - self._utterance_start) * 1000 if self._utterance_start else 0.0

        log_with_context(
            logger,
            logging.INFO,
            f"Final transcript: {transcript[:120]}",
            stt_ms=round(stt_latency_ms, 1),
            event="stt_final_transcript",
        )

        if self._on_final:
            await self._on_final(transcript, stt_latency_ms)

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Forward mulaw audio to Deepgram."""
        if self._ws is not None:
            try:
                await self._ws.send(audio_bytes)
            except Exception:
                pass

    async def close(self) -> None:
        """Gracefully close the Deepgram session."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            await self._ws.close()
            self._ws = None

        log_with_context(logger, logging.INFO, "Deepgram STT closed", event="stt_closed")
