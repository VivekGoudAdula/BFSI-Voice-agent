"""Compliance read service and dashboard aggregation (Phase 8)."""

import logging
from typing import Optional

from app.core.retention_policy import get_retention_policy
from app.database.mongodb import MongoDB
from app.models.compliance import (
    CallCompliancePackage,
    ComplianceDashboardSummary,
    ComplianceEventResponse,
    ComplianceEventType,
    ConsentResponse,
    ConsolidatedTranscriptResponse,
)
from app.repositories.compliance_repository import ComplianceRepository
from app.services.crm_data_service import CRMDataService

logger = logging.getLogger(__name__)


class ComplianceService:
    """Query compliance records and dashboard metrics."""

    def __init__(
        self,
        repository: ComplianceRepository,
        crm_data_service: Optional[CRMDataService] = None,
    ) -> None:
        self._repo = repository
        self._crm = crm_data_service

    def resolve_call_sid(self, call_sid_or_id: str) -> tuple[str, str]:
        """Resolve call_sid and call_id from either identifier."""
        call_sid = call_sid_or_id
        call_id = call_sid_or_id

        try:
            from bson import ObjectId

            if ObjectId.is_valid(call_sid_or_id):
                doc = MongoDB.calls().find_one({"_id": ObjectId(call_sid_or_id)})
                if doc:
                    call_id = str(doc["_id"])
                    call_sid = doc.get("twilio_call_sid") or call_sid_or_id
                    return call_sid, call_id
        except Exception:
            pass

        doc = MongoDB.calls().find_one({"twilio_call_sid": call_sid_or_id})
        if doc:
            return doc.get("twilio_call_sid", call_sid_or_id), str(doc["_id"])

        event = MongoDB.compliance_events().find_one(
            {"$or": [{"call_sid": call_sid_or_id}, {"call_id": call_sid_or_id}]}
        )
        if event:
            return event.get("call_sid", call_sid_or_id), event.get(
                "call_id", call_sid_or_id
            )

        return call_sid_or_id, call_sid_or_id

    def get_call_compliance_package(self, call_sid: str) -> CallCompliancePackage:
        resolved_sid, call_id = self.resolve_call_sid(call_sid)

        summary_text = None
        if self._crm:
            summary = self._crm.get_summary_by_call_id(call_id)
            if summary:
                summary_text = summary.summary

        events_raw = self._repo.list_events_by_call_sid(resolved_sid)
        events = [
            ComplianceEventResponse(
                id=str(e["_id"]),
                call_sid=e["call_sid"],
                call_id=e.get("call_id", ""),
                event_type=ComplianceEventType(e["event_type"]),
                event_data=e.get("event_data", {}),
                timestamp=e["timestamp"],
            )
            for e in events_raw
        ]

        return CallCompliancePackage(
            call_sid=resolved_sid,
            call_id=call_id,
            disclosure=self._repo.get_disclosure_by_call_sid(resolved_sid),
            consent=self._repo.get_consent_by_call_sid(resolved_sid),
            recording=self._repo.get_recording_by_call_sid(resolved_sid),
            transcript=self._get_transcript(resolved_sid, call_id),
            prompt_usage=self._repo.get_prompt_usage_by_call_sid(resolved_sid),
            summary=summary_text,
            tool_executions=self._repo.list_tool_audit_by_call_sid(resolved_sid),
            crm_updates=self._repo.list_crm_audit_by_call_sid(resolved_sid),
            escalations=self._repo.list_escalation_audit_by_call_sid(resolved_sid),
            events=events,
        )

    def get_transcript(self, call_sid: str) -> Optional[ConsolidatedTranscriptResponse]:
        resolved_sid, call_id = self.resolve_call_sid(call_sid)
        return self._get_transcript(resolved_sid, call_id)

    def _get_transcript(
        self, call_sid: str, call_id: str
    ) -> Optional[ConsolidatedTranscriptResponse]:
        transcript = self._repo.get_consolidated_transcript(call_sid)
        if transcript:
            return transcript
        return self._repo.get_consolidated_transcript_by_call_id(call_id)

    def get_audit_trail(self, call_sid: str) -> list[ComplianceEventResponse]:
        resolved_sid, _ = self.resolve_call_sid(call_sid)
        events_raw = self._repo.list_events_by_call_sid(resolved_sid)
        return [
            ComplianceEventResponse(
                id=str(e["_id"]),
                call_sid=e["call_sid"],
                call_id=e.get("call_id", ""),
                event_type=ComplianceEventType(e["event_type"]),
                event_data=e.get("event_data", {}),
                timestamp=e["timestamp"],
            )
            for e in events_raw
        ]

    def get_consent(self, call_sid: str) -> Optional[ConsentResponse]:
        resolved_sid, _ = self.resolve_call_sid(call_sid)
        return self._repo.get_consent_by_call_sid(resolved_sid)

    def get_tool_history(self, call_sid: str):
        resolved_sid, call_id = self.resolve_call_sid(call_sid)
        logs = self._repo.list_tool_audit_by_call_sid(resolved_sid)
        if logs:
            return logs
        return self._repo.list_tool_audit_by_call_id(call_id)

    def get_dashboard_summary(self) -> ComplianceDashboardSummary:
        total_calls = self._repo.count_unique_calls_with_events()
        if total_calls == 0:
            try:
                total_calls = MongoDB.calls().count_documents({})
            except Exception:
                total_calls = 0

        calls_with_consent = self._repo.count_consents("CONSENT_GRANTED")
        calls_without = (
            self._repo.count_consents("CONSENT_DENIED")
            + self._repo.count_consents("NO_RESPONSE")
        )

        return ComplianceDashboardSummary(
            total_calls=total_calls,
            calls_with_consent=calls_with_consent,
            calls_without_consent=calls_without,
            recorded_calls=self._repo.count_recordings(),
            escalated_calls=self._repo.count_escalation_audits(),
            tool_executions=self._repo.count_tool_audits(),
            prompt_versions=self._repo.count_prompt_versions(),
            audit_events=self._repo.count_compliance_events(),
        )

    def get_retention_policy(self) -> dict[str, int]:
        return get_retention_policy().as_dict()
