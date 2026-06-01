"""Human-like response pacing controller."""

import random


class SpeechPacingManager:
    """Optional short delay before TTS (disabled by default for low latency)."""

    def __init__(self, min_delay_ms: int = 0, max_delay_ms: int = 0) -> None:
        self._min = min_delay_ms
        self._max = max_delay_ms

    def next_delay_ms(self) -> int:
        if self._max <= 0:
            return 0
        return random.randint(self._min, self._max)
