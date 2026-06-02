"""Per-turn latency tracking helpers for voice calls."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class LatencyTracker:
    """Track named timing marks within a single conversation turn."""

    call_sid: str
    call_id: str
    turn_id: str = field(default_factory=lambda: str(int(time.time() * 1000)))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    marks: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, float | int] = field(default_factory=dict)
    _stt_first_partial_marked: bool = False
    _finalized: bool = False

    def mark(self, name: str) -> None:
        """Record a timing mark if it has not been recorded yet."""
        if self._finalized:
            return
        self.marks.setdefault(name, time.perf_counter())

    def mark_stt_first_partial(self) -> None:
        """Record first STT partial transcript marker once."""
        if self._stt_first_partial_marked:
            return
        self._stt_first_partial_marked = True
        self.mark("STT_FIRST_PARTIAL")

    def _delta_ms(self, start: str, end: str) -> float | None:
        start_t = self.marks.get(start)
        end_t = self.marks.get(end)
        if start_t is None or end_t is None:
            return None
        return round((end_t - start_t) * 1000, 1)

    def set_diagnostics(self, **values: float | int) -> None:
        """Attach token/response diagnostics gathered by conversation service."""
        if self._finalized:
            return
        for key, value in values.items():
            self.diagnostics[key] = value

    def compute_metrics(self) -> dict[str, float | int | None]:
        """Compute normalized latency metrics expected by the call pipeline."""
        metrics: dict[str, float | int | None] = {
            "stt_total_ms": self._delta_ms("STT_START", "STT_END"),
            "stt_to_transcript_ms": self._delta_ms("STT_START", "STT_FINAL_TRANSCRIPT"),
            "groq_total_ms": self._delta_ms("GROQ_START", "GROQ_END"),
            "tts_total_ms": self._delta_ms("TTS_START", "TTS_COMPLETE"),
            "playback_total_ms": self._delta_ms("AUDIO_PLAYBACK_START", "AUDIO_PLAYBACK_END"),
        }
        metrics.update(self.diagnostics)
        return metrics

    def to_mongo_document(self) -> dict:
        """Convert tracker data to a MongoDB document."""
        self._finalized = True
        metrics = self.compute_metrics()
        return {
            "call_id": self.call_id,
            "call_sid": self.call_sid,
            "turn_id": self.turn_id,
            "started_at": self.started_at,
            "created_at": datetime.now(timezone.utc),
            "marks": self.marks,
            "durations_ms": metrics,
            "diagnostics": self.diagnostics,
        }

    def log_breakdown(self) -> None:
        """Emit a concise latency breakdown in logs."""
        metrics = self.compute_metrics()
        logger.info(
            "Latency breakdown | call_id=%s stt_ms=%s groq_ms=%s tts_ms=%s playback_ms=%s",
            self.call_id,
            metrics.get("stt_total_ms"),
            metrics.get("groq_total_ms"),
            metrics.get("tts_total_ms"),
            metrics.get("playback_total_ms"),
        )


def create_tracker(call_sid: str, call_id: str) -> LatencyTracker:
    """Factory for a new per-turn latency tracker."""
    tracker = LatencyTracker(call_sid=call_sid, call_id=call_id)
    tracker.mark("TURN_START")
    return tracker
