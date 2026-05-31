"""MongoDB repository for Phase 8 compliance and audit collections."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.compliance import (
    CallPromptUsageResponse,
    CallRecordingResponse,
    ComplianceEventType,
    ConsentResponse,
    ConsentStatus,
    ConsolidatedTranscriptResponse,
    CRMAuditLogResponse,
    DisclosureResponse,
    EscalationAuditLogResponse,
    PromptVersionResponse,
    ToolAuditLogResponse,
    TranscriptMessage,
)
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class ComplianceRepository:
    """Data access layer for compliance collections."""

    # --- Disclosures ---

    def store_disclosure(
        self,
        *,
        call_sid: str,
        call_id: str,
        disclosure_text: str,
        played: bool = True,
    ) -> DisclosureResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "disclosure_text": disclosure_text,
            "played": played,
            "played_at": now,
        }
        try:
            result = MongoDB.disclosures().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = result.inserted_id
        return self._serialize_disclosure(doc)

    def get_disclosure_by_call_sid(self, call_sid: str) -> Optional[DisclosureResponse]:
        try:
            doc = MongoDB.disclosures().find_one({"call_sid": call_sid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_disclosure(doc) if doc else None

    # --- Consents ---

    def store_consent(
        self,
        *,
        call_sid: str,
        call_id: str,
        status: ConsentStatus,
    ) -> ConsentResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "status": status.value,
            "captured_at": now,
        }
        try:
            result = MongoDB.consents().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = result.inserted_id
        return self._serialize_consent(doc)

    def get_consent_by_call_sid(self, call_sid: str) -> Optional[ConsentResponse]:
        try:
            docs = find_sorted(
                MongoDB.consents(),
                {"call_sid": call_sid},
                sort_field="captured_at",
                sort_direction=-1,
                limit=1,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_consent(docs[0]) if docs else None

    # --- Call recordings ---

    def store_recording_metadata(
        self,
        *,
        call_sid: str,
        call_id: str,
        recording_url: str,
        duration: Optional[float] = None,
        storage_provider: str = "local",
    ) -> CallRecordingResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "recording_url": recording_url,
            "duration": duration,
            "storage_provider": storage_provider,
            "created_at": now,
        }
        try:
            result = MongoDB.call_recordings().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = result.inserted_id
        return self._serialize_recording(doc)

    def get_recording_by_call_sid(self, call_sid: str) -> Optional[CallRecordingResponse]:
        try:
            doc = MongoDB.call_recordings().find_one({"call_sid": call_sid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_recording(doc) if doc else None

    # --- Consolidated transcripts ---

    def append_transcript_message(
        self,
        *,
        call_sid: str,
        call_id: str,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        message = {"role": role, "content": content, "timestamp": ts}
        now = datetime.now(timezone.utc)
        try:
            MongoDB.compliance_transcripts().update_one(
                {"call_sid": call_sid},
                {
                    "$push": {"messages": message},
                    "$set": {"call_id": call_id, "updated_at": now},
                    "$setOnInsert": {"call_sid": call_sid, "created_at": now},
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("Failed to append compliance transcript: %s", exc)

    def get_consolidated_transcript(
        self, call_sid: str
    ) -> Optional[ConsolidatedTranscriptResponse]:
        try:
            doc = MongoDB.compliance_transcripts().find_one({"call_sid": call_sid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_transcript(doc) if doc else None

    def get_consolidated_transcript_by_call_id(
        self, call_id: str
    ) -> Optional[ConsolidatedTranscriptResponse]:
        try:
            doc = MongoDB.compliance_transcripts().find_one({"call_id": call_id})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_transcript(doc) if doc else None

    # --- Prompt versions ---

    def ensure_prompt_version(
        self,
        *,
        agent_name: str,
        version: int,
        prompt: str,
    ) -> PromptVersionResponse:
        """Store prompt version if not already recorded for this agent+version."""
        try:
            existing = MongoDB.prompt_versions().find_one(
                {"agent_name": agent_name, "version": version}
            )
            if existing:
                return self._serialize_prompt_version(existing)

            now = datetime.now(timezone.utc)
            doc: dict[str, Any] = {
                "agent_name": agent_name,
                "version": version,
                "prompt": prompt,
                "created_at": now,
            }
            result = MongoDB.prompt_versions().insert_one(doc)
            doc["_id"] = result.inserted_id
            return self._serialize_prompt_version(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def record_call_prompt_usage(
        self,
        *,
        call_sid: str,
        call_id: str,
        agent_name: str,
        agent_id: str,
        prompt_version: int,
    ) -> CallPromptUsageResponse:
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "prompt_version": prompt_version,
            "agent_name": agent_name,
            "agent_id": agent_id,
        }
        try:
            result = MongoDB.call_prompt_usage().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = result.inserted_id
        return self._serialize_prompt_usage(doc)

    def get_prompt_usage_by_call_sid(
        self, call_sid: str
    ) -> Optional[CallPromptUsageResponse]:
        try:
            doc = MongoDB.call_prompt_usage().find_one({"call_sid": call_sid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_prompt_usage(doc) if doc else None

    # --- Tool audit ---

    def store_tool_audit(
        self,
        *,
        call_sid: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        execution_time_ms: float,
    ) -> ToolAuditLogResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "execution_time_ms": round(execution_time_ms, 2),
            "executed_at": now,
        }
        try:
            inserted = MongoDB.tool_audit_logs().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = inserted.inserted_id
        return self._serialize_tool_audit(doc)

    def list_tool_audit_by_call_sid(self, call_sid: str) -> list[ToolAuditLogResponse]:
        try:
            docs = find_sorted(
                MongoDB.tool_audit_logs(),
                {"call_sid": call_sid},
                sort_field="executed_at",
                sort_direction=1,
            )
            return [self._serialize_tool_audit(d) for d in docs]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def list_tool_audit_by_call_id(self, call_id: str) -> list[ToolAuditLogResponse]:
        try:
            docs = find_sorted(
                MongoDB.tool_audit_logs(),
                {"call_id": call_id},
                sort_field="executed_at",
                sort_direction=1,
            )
            return [self._serialize_tool_audit(d) for d in docs]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- CRM audit ---

    def store_crm_audit(
        self,
        *,
        call_sid: str,
        call_id: str,
        action: str,
        previous_value: str = "",
        new_value: str = "",
    ) -> CRMAuditLogResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "action": action,
            "previous_value": previous_value,
            "new_value": new_value,
            "updated_at": now,
        }
        try:
            result = MongoDB.crm_audit_logs().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = result.inserted_id
        return self._serialize_crm_audit(doc)

    def list_crm_audit_by_call_sid(self, call_sid: str) -> list[CRMAuditLogResponse]:
        try:
            docs = find_sorted(
                MongoDB.crm_audit_logs(),
                {"call_sid": call_sid},
                sort_field="updated_at",
                sort_direction=1,
            )
            return [self._serialize_crm_audit(d) for d in docs]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- Escalation audit ---

    def store_escalation_audit(
        self,
        *,
        call_sid: str,
        call_id: str,
        category: str,
        reason: str,
    ) -> EscalationAuditLogResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "category": category,
            "reason": reason,
            "created_at": now,
        }
        try:
            result = MongoDB.escalation_audit_logs().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        doc["_id"] = result.inserted_id
        return self._serialize_escalation_audit(doc)

    def list_escalation_audit_by_call_sid(
        self, call_sid: str
    ) -> list[EscalationAuditLogResponse]:
        try:
            docs = find_sorted(
                MongoDB.escalation_audit_logs(),
                {"call_sid": call_sid},
                sort_field="created_at",
                sort_direction=1,
            )
            return [self._serialize_escalation_audit(d) for d in docs]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- Compliance events (source of truth) ---

    def record_event(
        self,
        *,
        call_sid: str,
        call_id: str,
        event_type: ComplianceEventType,
        event_data: Optional[dict[str, Any]] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "event_type": event_type.value,
            "event_data": event_data or {},
            "timestamp": now,
        }
        try:
            MongoDB.compliance_events().insert_one(doc)
        except PyMongoError as exc:
            logger.error("Failed to record compliance event: %s", exc)

    def list_events_by_call_sid(
        self, call_sid: str
    ) -> list[dict[str, Any]]:
        try:
            return find_sorted(
                MongoDB.compliance_events(),
                {"call_sid": call_sid},
                sort_field="timestamp",
                sort_direction=1,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- Dashboard counts ---

    def count_disclosures(self) -> int:
        return MongoDB.disclosures().count_documents({})

    def count_consents(self, status: Optional[str] = None) -> int:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        return MongoDB.consents().count_documents(query)

    def count_recordings(self) -> int:
        return MongoDB.call_recordings().count_documents({})

    def count_escalation_audits(self) -> int:
        return MongoDB.escalation_audit_logs().count_documents({})

    def count_tool_audits(self) -> int:
        return MongoDB.tool_audit_logs().count_documents({})

    def count_prompt_versions(self) -> int:
        return MongoDB.prompt_versions().count_documents({})

    def count_compliance_events(self) -> int:
        return MongoDB.compliance_events().count_documents({})

    def count_unique_calls_with_events(self) -> int:
        pipeline = [{"$group": {"_id": "$call_sid"}}, {"$count": "total"}]
        result = list(MongoDB.compliance_events().aggregate(pipeline))
        return result[0]["total"] if result else 0

    # --- Serializers ---

    @staticmethod
    def _serialize_disclosure(doc: dict[str, Any]) -> DisclosureResponse:
        return DisclosureResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            disclosure_text=doc["disclosure_text"],
            played=doc.get("played", False),
            played_at=doc["played_at"],
        )

    @staticmethod
    def _serialize_consent(doc: dict[str, Any]) -> ConsentResponse:
        return ConsentResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            status=ConsentStatus(doc["status"]),
            captured_at=doc["captured_at"],
        )

    @staticmethod
    def _serialize_recording(doc: dict[str, Any]) -> CallRecordingResponse:
        return CallRecordingResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            recording_url=doc["recording_url"],
            duration=doc.get("duration"),
            storage_provider=doc.get("storage_provider", "local"),
            created_at=doc["created_at"],
        )

    @staticmethod
    def _serialize_transcript(doc: dict[str, Any]) -> ConsolidatedTranscriptResponse:
        return ConsolidatedTranscriptResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            messages=[
                TranscriptMessage(
                    role=m["role"],
                    content=m["content"],
                    timestamp=m["timestamp"],
                )
                for m in doc.get("messages", [])
            ],
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    @staticmethod
    def _serialize_prompt_version(doc: dict[str, Any]) -> PromptVersionResponse:
        return PromptVersionResponse(
            id=str(doc["_id"]),
            agent_name=doc["agent_name"],
            version=doc["version"],
            prompt=doc["prompt"],
            created_at=doc["created_at"],
        )

    @staticmethod
    def _serialize_prompt_usage(doc: dict[str, Any]) -> CallPromptUsageResponse:
        return CallPromptUsageResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            prompt_version=doc["prompt_version"],
            agent_name=doc["agent_name"],
            agent_id=doc.get("agent_id", ""),
        )

    @staticmethod
    def _serialize_tool_audit(doc: dict[str, Any]) -> ToolAuditLogResponse:
        return ToolAuditLogResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            tool_name=doc["tool_name"],
            arguments=doc.get("arguments", {}),
            result=doc.get("result", {}),
            execution_time_ms=doc.get("execution_time_ms", 0),
            executed_at=doc["executed_at"],
        )

    @staticmethod
    def _serialize_crm_audit(doc: dict[str, Any]) -> CRMAuditLogResponse:
        return CRMAuditLogResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            action=doc["action"],
            previous_value=doc.get("previous_value", ""),
            new_value=doc.get("new_value", ""),
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _serialize_escalation_audit(doc: dict[str, Any]) -> EscalationAuditLogResponse:
        return EscalationAuditLogResponse(
            id=str(doc["_id"]),
            call_sid=doc["call_sid"],
            call_id=doc.get("call_id", ""),
            category=doc["category"],
            reason=doc["reason"],
            created_at=doc["created_at"],
        )

    @staticmethod
    def _to_object_id(value: str) -> Optional[ObjectId]:
        try:
            return ObjectId(value)
        except Exception:
            return None
