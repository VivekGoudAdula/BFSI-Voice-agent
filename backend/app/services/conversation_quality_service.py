"""Human-likeness conversation quality metrics persistence."""

from datetime import datetime, timezone

from app.database.mongodb import MongoDB


class ConversationQualityService:
    """Stores per-call conversation quality and human-likeness metrics."""

    def finalize_metrics(self, session: object) -> None:
        avg_response_time_ms = 0
        if getattr(session, "response_latency_count", 0) > 0:
            avg_response_time_ms = int(
                session.response_latency_ms_sum / session.response_latency_count
            )
        avg_turn_duration_ms = 0
        if getattr(session, "turn_count", 0) > 0:
            avg_turn_duration_ms = int(session.total_turn_duration_ms / session.turn_count)

        sentiment = getattr(session, "last_customer_sentiment", "neutral")
        score = self._compute_score(
            interruptions_handled=int(getattr(session, "interruption_count", 0)),
            avg_response_time_ms=avg_response_time_ms,
            sentiment=sentiment,
        )
        MongoDB.conversation_quality_metrics().insert_one(
            {
                "call_sid": session.call_sid,
                "interruptions_handled": int(getattr(session, "interruption_count", 0)),
                "avg_response_time_ms": avg_response_time_ms,
                "avg_turn_duration_ms": avg_turn_duration_ms,
                "customer_sentiment": sentiment,
                "conversation_score": score,
                "human_likeness_score": score,
                "created_at": datetime.now(timezone.utc),
            }
        )

    @staticmethod
    def _compute_score(
        interruptions_handled: int,
        avg_response_time_ms: int,
        sentiment: str,
    ) -> int:
        score = 88
        if 300 <= avg_response_time_ms <= 900:
            score += 6
        elif avg_response_time_ms < 200 or avg_response_time_ms > 1400:
            score -= 8
        if interruptions_handled > 0:
            score += min(interruptions_handled * 2, 6)
        if sentiment in ("negative", "frustrated"):
            score -= 4
        return max(0, min(100, score))
