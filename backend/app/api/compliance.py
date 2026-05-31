"""Compliance and audit API endpoints (Phase 8)."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.dependencies import get_compliance_service
from app.core.exceptions import AppException
from app.models.compliance import (
    CallCompliancePackage,
    ComplianceDashboardSummary,
    ComplianceEventResponse,
    ConsentResponse,
    ConsolidatedTranscriptResponse,
    ToolAuditLogResponse,
)
from app.services.compliance_service import ComplianceService

router = APIRouter(prefix="/compliance", tags=["Compliance & Audit"])


class ComplianceRecordNotFoundError(AppException):
    def __init__(self, call_sid: str, record_type: str) -> None:
        super().__init__(
            status_code=404,
            detail=f"{record_type} not found for call {call_sid}",
        )


@router.get(
    "/call/{call_sid}",
    response_model=CallCompliancePackage,
    summary="Full compliance package for a call",
)
def get_call_compliance(
    call_sid: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> CallCompliancePackage:
    package = service.get_call_compliance_package(call_sid)
    if not package.events and not package.disclosure and not package.transcript:
        raise ComplianceRecordNotFoundError(call_sid, "Compliance record")
    return package


@router.get(
    "/transcript/{call_sid}",
    response_model=ConsolidatedTranscriptResponse,
    summary="Consolidated transcript for a call",
)
def get_call_transcript(
    call_sid: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> ConsolidatedTranscriptResponse:
    transcript = service.get_transcript(call_sid)
    if not transcript:
        raise ComplianceRecordNotFoundError(call_sid, "Transcript")
    return transcript


@router.get(
    "/audit/{call_sid}",
    response_model=list[ComplianceEventResponse],
    summary="Compliance audit trail for a call",
)
def get_call_audit_trail(
    call_sid: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> list[ComplianceEventResponse]:
    events = service.get_audit_trail(call_sid)
    if not events:
        raise ComplianceRecordNotFoundError(call_sid, "Audit trail")
    return events


@router.get(
    "/consent/{call_sid}",
    response_model=ConsentResponse,
    summary="Consent record for a call",
)
def get_call_consent(
    call_sid: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> ConsentResponse:
    consent = service.get_consent(call_sid)
    if not consent:
        raise ComplianceRecordNotFoundError(call_sid, "Consent record")
    return consent


@router.get(
    "/tool-history/{call_sid}",
    response_model=list[ToolAuditLogResponse],
    summary="Tool execution audit history for a call",
)
def get_tool_history(
    call_sid: str,
    service: ComplianceService = Depends(get_compliance_service),
) -> list[ToolAuditLogResponse]:
    logs = service.get_tool_history(call_sid)
    if not logs:
        raise ComplianceRecordNotFoundError(call_sid, "Tool audit history")
    return logs


@router.get(
    "/dashboard/summary",
    response_model=ComplianceDashboardSummary,
    summary="Compliance dashboard metrics",
)
def get_dashboard_summary(
    service: ComplianceService = Depends(get_compliance_service),
) -> ComplianceDashboardSummary:
    return service.get_dashboard_summary()


@router.get(
    "/retention-policy",
    summary="Configured retention policy (framework only)",
)
def get_retention_policy(
    service: ComplianceService = Depends(get_compliance_service),
) -> dict[str, Any]:
    return {
        "policy": service.get_retention_policy(),
        "deletion_enabled": False,
        "note": "Retention framework only — automated deletion not implemented.",
    }
