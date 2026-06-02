"""Deepgram streaming speech-to-text integration."""

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from app.services.latency_tracker import LatencyTracker
from urllib.parse import urlencode

import websockets
from websockets.asyncio.client import ClientConnection

from app.core.config import Settings
from app.core.exceptions import SpeechRecognitionError
from app.core.logging_config import log_with_context

logger = logging.getLogger(__name__)

FinalTranscriptHandler = Callable[[str, float], Awaitable[None]]
SpeechStartedHandler = Callable[[], Awaitable[None]]

# Map app language codes → Deepgram language parameter
DEEPGRAM_LANGUAGE_MAP: dict[str, str] = {
    "en": "en",
    "hi": "hi",
    "multi": "multi",
}


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
        self._language = self._normalize_language(settings.deepgram_language)
        self._ws: Optional[ClientConnection] = None
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._on_final: Optional[FinalTranscriptHandler] = None
        self._on_speech_started: Optional[SpeechStartedHandler] = None
        self._last_final_at: float = 0.0
        self._utterance_start: float = 0.0
        self._connect_lock = asyncio.Lock()
        self._latency_tracker: Optional["LatencyTracker"] = None

    @staticmethod
    def _normalize_language(code: str) -> str:
        normalized = (code or "multi").strip().lower()
        return DEEPGRAM_LANGUAGE_MAP.get(normalized, normalized)

    def _build_ws_url(self, language: str | None = None) -> str:
        lang = self._normalize_language(language or self._language)
        # Shorter endpointing helps multilingual / code-switching (Deepgram docs)
        endpointing_ms = "100" if lang == "multi" else "300"
        params = {
            "encoding": "mulaw",
            "sample_rate": "8000",
            "channels": "1",
            "model": self._model,
            "language": lang,
            "interim_results": "true",
            "utterance_end_ms": "1000",
            "vad_events": "true",
            "endpointing": endpointing_ms,
            "punctuate": "true",
            "smart_format": "true",
        }
        return f"{self.DEEPGRAM_WS_BASE}?{urlencode(params)}"

    def set_latency_tracker(self, tracker: Optional["LatencyTracker"]) -> None:
        """Attach per-turn latency tracker for STT stage marks."""
        self._latency_tracker = tracker

    async def connect(
        self,
        on_final_transcript: FinalTranscriptHandler,
        on_speech_started: Optional[SpeechStartedHandler] = None,
        language: str | None = None,
    ) -> None:
        """Open a Deepgram live transcription session."""
        if language:
            self._language = self._normalize_language(language)

        async with self._connect_lock:
            await self._shutdown_connection()
            await self._open_connection(on_final_transcript, on_speech_started)

    async def _open_connection(
        self,
        on_final_transcript: FinalTranscriptHandler,
        on_speech_started: Optional[SpeechStartedHandler],
    ) -> None:
        if not self._api_key:
            raise SpeechRecognitionError("DEEPGRAM_API_KEY must be configured")

        self._on_final = on_final_transcript
        self._on_speech_started = on_speech_started

        headers = {"Authorization": f"Token {self._api_key}"}
        url = self._build_ws_url(self._language)

        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=2**20,
            )
        except Exception as exc:
            raise SpeechRecognitionError(f"Failed to connect to Deepgram: {exc}") from exc

        self._listener_task = asyncio.create_task(self._listen())
        log_with_context(
            logger,
            logging.INFO,
            f"Deepgram STT connected (language={self._language})",
            event="stt_connected",
        )

    def schedule_language_change(self, language_code: str) -> None:
        """Reconnect STT on a background task (never call set_language from the listener)."""
        asyncio.create_task(self.set_language(language_code))

    async def set_language(self, language_code: str) -> None:
        """Reconnect Deepgram with a new language."""
        if not self._on_final:
            return

        new_lang = self._normalize_language(language_code)
        # Keep multilingual mode for English — switching to en hurts Hindi callers
        if new_lang == "en" and self._language == "multi":
            return
        if new_lang == self._language:
            return

        log_with_context(
            logger,
            logging.INFO,
            f"Deepgram STT reconnecting for language={new_lang}",
            event="stt_language_changed",
        )

        on_final = self._on_final
        on_speech_started = self._on_speech_started

        async with self._connect_lock:
            await self._shutdown_connection()
            self._language = new_lang
            await self._open_connection(on_final, on_speech_started)

    async def _shutdown_connection(self) -> None:
        """Tear down websocket and listener without awaiting the current task."""
        ws = self._ws
        self._ws = None
        task = self._listener_task
        self._listener_task = None

        if ws is not None:
            try:
                await ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass

        if task is not None and not task.done():
            task.cancel()
            current = asyncio.current_task()
            if task is not current:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

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
            if self._latency_tracker:
                # Mark after the callback so per-turn trackers can be attached
                # during the SpeechStarted handler.
                self._latency_tracker.mark("STT_START")
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
            if self._latency_tracker:
                self._latency_tracker.mark_stt_first_partial()
            return

        # Deduplicate rapid duplicate finals
        now = time.perf_counter()
        if now - self._last_final_at < 0.3:
            return
        self._last_final_at = now

        stt_latency_ms = (now - self._utterance_start) * 1000 if self._utterance_start else 0.0

        if self._latency_tracker:
            self._latency_tracker.mark("STT_FINAL_TRANSCRIPT")
            self._latency_tracker.mark("STT_END")

        if self._language == "hi":
            log_line = f"अंतिम प्रतिलेख: {transcript[:120]}"
        else:
            log_line = f"Final transcript: {transcript[:120]}"
        log_with_context(
            logger,
            logging.INFO,
            log_line,
            stt_ms=round(stt_latency_ms, 1),
            event="stt_final_transcript",
            active_language=self._language,
        )

        if self._on_final:
            asyncio.create_task(self._dispatch_final(transcript, stt_latency_ms))

    async def _dispatch_final(self, transcript: str, stt_latency_ms: float) -> None:
        """Run transcript handler outside the Deepgram listener task."""
        if not self._on_final:
            return
        try:
            await self._on_final(transcript, stt_latency_ms)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Final transcript handler failed: {exc}",
                event="stt_handler_error",
            )

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Forward mulaw audio to Deepgram."""
        if self._ws is not None:
            try:
                await self._ws.send(audio_bytes)
            except Exception:
                pass

    async def close(self) -> None:
        """Gracefully close the Deepgram session."""
        async with self._connect_lock:
            await self._shutdown_connection()
        log_with_context(logger, logging.INFO, "Deepgram STT closed", event="stt_closed")
