"""Facade service for handoff API operations."""

from app.core.exceptions import EscalationNotFoundError, HandoffQueueItemNotFoundError
from app.models.handoff import (
    EscalationResponse,
    HandoffAnalyticsSummary,
    HumanHandoffLogResponse,
    TransferQueueItemResponse,
)
from app.repositories.handoff_repository import HandoffRepository
from app.services.handoff_analytics_service import HandoffAnalyticsService


class HandoffService:
    """Application service for escalation and transfer queue APIs."""

    def __init__(
        self,
        repository: HandoffRepository,
        analytics_service: HandoffAnalyticsService,
    ) -> None:
        self._repo = repository
        self._analytics = analytics_service

    def list_escalations(self, limit: int = 100) -> list[EscalationResponse]:
        docs = self._repo.list_escalations(limit=limit)
        return [self._repo.serialize_escalation(d) for d in docs]

    def get_escalation(self, escalation_id: str) -> EscalationResponse:
        doc = self._repo.get_escalation(escalation_id)
        if not doc:
            raise EscalationNotFoundError(escalation_id)
        return self._repo.serialize_escalation(doc)

    def list_queue_items(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[TransferQueueItemResponse]:
        docs = self._repo.list_queue_items(status=status, limit=limit)
        return [self._repo.serialize_queue_item(d) for d in docs]

    def get_queue_item(self, queue_id: str) -> TransferQueueItemResponse:
        doc = self._repo.get_queue_item(queue_id)
        if not doc:
            raise HandoffQueueItemNotFoundError(queue_id)
        return self._repo.serialize_queue_item(doc)

    def get_analytics(self) -> HandoffAnalyticsSummary:
        return self._analytics.get_summary()
