"""Voice activity tracking for speech start/stop and silence windows."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class VoiceActivityConfig:
    min_speech_ms: int = 120
    silence_timeout_ms: int = 900


class VoiceActivityService:
    """Tracks customer speech activity and computes silence durations."""

    def __init__(self, config: VoiceActivityConfig | None = None) -> None:
        self._config = config or VoiceActivityConfig()

    def on_speech_started(self, session: object) -> None:
        now = datetime.now(timezone.utc)
        session.last_user_speech_started_at = now

    def on_speech_stopped(self, session: object) -> int:
        now = datetime.now(timezone.utc)
        session.last_user_speech_stopped_at = now
        if not getattr(session, "last_user_speech_started_at", None):
            return 0
        delta_ms = int(
            (now - session.last_user_speech_started_at).total_seconds() * 1000
        )
        return max(delta_ms, 0)

    def get_silence_ms(self, session: object) -> int:
        stopped_at = getattr(session, "last_user_speech_stopped_at", None)
        if not stopped_at:
            return 0
        return int((datetime.now(timezone.utc) - stopped_at).total_seconds() * 1000)

    @property
    def silence_timeout_ms(self) -> int:
        return self._config.silence_timeout_ms
