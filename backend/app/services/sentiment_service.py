"""Sentiment analysis layer for escalation detection (Phase 7)."""

import re

from app.models.handoff import SentimentLevel

_VERY_NEGATIVE_PATTERNS = [
    r"\b(furious|outraged|disgusted|hate you|worst ever|sue you|idiot|stupid)\b",
    r"\b(this is ridiculous|absolutely unacceptable|never again)\b",
    r"\b(shut up|go to hell|damn you)\b",
]

_NEGATIVE_PATTERNS = [
    r"\b(angry|frustrated|upset|annoyed|disappointed|terrible|awful|horrible)\b",
    r"\b(not happy|unhappy|fed up|sick of|waste of time)\b",
    r"\b(complaint|complain|unacceptable|nonsense)\b",
    r"\b(wrong|incorrect|dispute|don't agree|do not agree)\b",
]

_POSITIVE_PATTERNS = [
    r"\b(thank you|thanks|appreciate|great|helpful|good|fine|okay|ok)\b",
    r"\b(understood|sounds good|no problem|perfect)\b",
]


class SentimentService:
    """Keyword-based sentiment classifier for voice transcripts."""

    def analyze(self, text: str) -> SentimentLevel:
        """Classify a single utterance."""
        normalized = text.lower().strip()
        if not normalized or len(normalized) < 2:
            return SentimentLevel.NEUTRAL

        if self._matches_any(normalized, _VERY_NEGATIVE_PATTERNS):
            return SentimentLevel.VERY_NEGATIVE
        if self._matches_any(normalized, _NEGATIVE_PATTERNS):
            return SentimentLevel.NEGATIVE
        if self._matches_any(normalized, _POSITIVE_PATTERNS):
            return SentimentLevel.POSITIVE

        return SentimentLevel.NEUTRAL

    def should_escalate_for_sentiment(
        self,
        current: SentimentLevel,
        history: list[SentimentLevel],
    ) -> bool:
        """
        Escalate when sentiment is VERY_NEGATIVE or repeated NEGATIVE responses.
        """
        if current == SentimentLevel.VERY_NEGATIVE:
            return True

        negative_count = sum(
            1 for s in history if s in (SentimentLevel.NEGATIVE, SentimentLevel.VERY_NEGATIVE)
        )
        if current == SentimentLevel.NEGATIVE and negative_count >= 2:
            return True

        return False

    def aggregate_sentiment(self, history: list[SentimentLevel]) -> SentimentLevel:
        """Return the worst sentiment observed in the conversation."""
        if not history:
            return SentimentLevel.NEUTRAL
        priority = {
            SentimentLevel.VERY_NEGATIVE: 4,
            SentimentLevel.NEGATIVE: 3,
            SentimentLevel.NEUTRAL: 2,
            SentimentLevel.POSITIVE: 1,
        }
        return max(history, key=lambda s: priority.get(s, 0))

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)
