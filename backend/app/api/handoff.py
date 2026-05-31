"""Human handoff and escalation API endpoints (Phase 7)."""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_handoff_service
from app.models.handoff import (
    EscalationResponse,
    HandoffAnalyticsSummary,
    TransferQueueItemResponse,
)
from app.services.handoff_service import HandoffService

router_escalations = APIRouter(prefix="/escalations", tags=["Escalations"])
router_queue = APIRouter(prefix="/handoff-queue", tags=["Handoff Queue"])


@router_escalations.get(
    "",
    response_model=list[EscalationResponse],
    summary="List all escalations",
)
def list_escalations(
    limit: int = Query(100, ge=1, le=500),
    service: HandoffService = Depends(get_handoff_service),
) -> list[EscalationResponse]:
    return service.list_escalations(limit=limit)


@router_escalations.get(
    "/analytics/summary",
    response_model=HandoffAnalyticsSummary,
    summary="Escalation and handoff analytics",
)
def get_handoff_analytics(
    service: HandoffService = Depends(get_handoff_service),
) -> HandoffAnalyticsSummary:
    return service.get_analytics()


@router_escalations.get(
    "/{escalation_id}",
    response_model=EscalationResponse,
    summary="Get escalation by ID",
)
def get_escalation(
    escalation_id: str,
    service: HandoffService = Depends(get_handoff_service),
) -> EscalationResponse:
    return service.get_escalation(escalation_id)


@router_queue.get(
    "",
    response_model=list[TransferQueueItemResponse],
    summary="List transfer queue items",
)
def list_handoff_queue(
    status: str | None = Query(None, description="Filter by queue status"),
    limit: int = Query(100, ge=1, le=500),
    service: HandoffService = Depends(get_handoff_service),
) -> list[TransferQueueItemResponse]:
    return service.list_queue_items(status=status, limit=limit)


@router_queue.get(
    "/{queue_id}",
    response_model=TransferQueueItemResponse,
    summary="Get transfer queue item by ID",
)
def get_handoff_queue_item(
    queue_id: str,
    service: HandoffService = Depends(get_handoff_service),
) -> TransferQueueItemResponse:
    return service.get_queue_item(queue_id)
