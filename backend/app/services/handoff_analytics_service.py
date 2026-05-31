"""Analytics for escalations and human handoffs (Phase 7)."""

from app.database.mongodb import MongoDB
from app.models.handoff import EscalationCategory, HandoffAnalyticsSummary
from app.repositories.handoff_repository import HandoffRepository


class HandoffAnalyticsService:
    """Tracks escalation rates and human transfer metrics."""

    def __init__(self, repository: HandoffRepository) -> None:
        self._repo = repository

    def get_summary(self) -> HandoffAnalyticsSummary:
        total_escalations = self._repo.count_escalations()
        total_calls = self._count_calls()
        human_transfers = self._repo.count_handoff_logs(
            status="TRANSFERRED",
        )
        if human_transfers == 0:
            human_transfers = self._repo.count_handoff_logs()

        escalation_rate = (
            round(total_escalations / total_calls, 4) if total_calls > 0 else 0.0
        )
        transfer_rate = (
            round(human_transfers / total_calls, 4) if total_calls > 0 else 0.0
        )

        return HandoffAnalyticsSummary(
            total_escalations=total_escalations,
            escalation_rate=escalation_rate,
            complaint_escalations=self._repo.count_escalations_by_type(
                EscalationCategory.COMPLAINT.value
            ),
            legal_escalations=self._repo.count_escalations_by_type(
                EscalationCategory.LEGAL_QUERY.value
            ),
            negative_sentiment_escalations=self._repo.count_escalations_by_type(
                EscalationCategory.NEGATIVE_SENTIMENT.value
            ),
            human_transfer_count=human_transfers,
            human_transfer_rate=transfer_rate,
            total_calls=total_calls,
            queue_waiting=self._repo.count_queue_waiting(),
            queue_high_priority=self._repo.count_queue_high_priority(),
        )

    @staticmethod
    def _count_calls() -> int:
        try:
            return MongoDB.calls().count_documents({})
        except Exception:
            return 0
