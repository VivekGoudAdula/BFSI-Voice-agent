"""Internal CRM API endpoints (MongoDB-backed)."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_crm_data_service
from app.core.exceptions import CRMRecordNotFoundError
from app.models.crm import (
    CRMAnalyticsSummary,
    CallOutcomeResponse,
    ConversationSummaryResponse,
    LeadStatusUpdateResponse,
)
from app.services.crm_data_service import CRMDataService

router = APIRouter(prefix="/crm", tags=["Internal CRM"])


@router.get(
    "/summary/{call_id}",
    response_model=ConversationSummaryResponse,
    summary="Get conversation summary for a call",
)
def get_call_summary(
    call_id: str,
    service: CRMDataService = Depends(get_crm_data_service),
) -> ConversationSummaryResponse:
    summary = service.get_summary_by_call_id(call_id)
    if not summary:
        raise CRMRecordNotFoundError(call_id, "Conversation summary")
    return summary


@router.get(
    "/outcome/{call_id}",
    response_model=CallOutcomeResponse,
    summary="Get call outcome for a call",
)
def get_call_outcome(
    call_id: str,
    service: CRMDataService = Depends(get_crm_data_service),
) -> CallOutcomeResponse:
    outcome = service.get_outcome_by_call_id(call_id)
    if not outcome:
        raise CRMRecordNotFoundError(call_id, "Call outcome")
    return outcome


@router.get(
    "/status/{call_id}",
    response_model=LeadStatusUpdateResponse,
    summary="Get lead status update for a call",
)
def get_lead_status(
    call_id: str,
    service: CRMDataService = Depends(get_crm_data_service),
) -> LeadStatusUpdateResponse:
    status_update = service.get_status_by_call_id(call_id)
    if not status_update:
        raise CRMRecordNotFoundError(call_id, "Lead status")
    return status_update


@router.get(
    "/analytics/summary",
    response_model=CRMAnalyticsSummary,
    summary="Internal CRM analytics summary",
)
def get_crm_analytics(
    service: CRMDataService = Depends(get_crm_data_service),
) -> CRMAnalyticsSummary:
    return service.get_analytics_summary()
