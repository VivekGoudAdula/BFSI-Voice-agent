"""CRM data persistence for summaries, outcomes, and status updates."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.crm import (
    CallAnalysisResult,
    CallOutcomeResponse,
    ConversationSummaryResponse,
    CRMAnalyticsSummary,
    CRMSyncLogResponse,
    CRMSyncStatus,
    LeadStatusUpdateResponse,
)

logger = logging.getLogger(__name__)


class CRMDataService:
    """Persists CRM-related call data to MongoDB."""

    def is_call_processed(self, call_id: str) -> bool:
        """Check if post-call processing already ran for this call."""
        try:
            return MongoDB.conversation_summaries().count_documents({"call_id": call_id}) > 0
        except PyMongoError:
            return False

    def store_summary(
        self,
        *,
        call_id: str,
        call_sid: str,
        customer_id: str,
        analysis: CallAnalysisResult,
    ) -> ConversationSummaryResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "customer_id": customer_id,
            "summary": analysis.summary,
            "intent": analysis.intent,
            "follow_up_actions": analysis.follow_up_actions,
            "follow_up_date": analysis.follow_up.follow_up_date,
            "follow_up_time": analysis.follow_up.follow_up_time,
            "created_at": now,
        }

        try:
            result = MongoDB.conversation_summaries().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        doc["_id"] = result.inserted_id
        return self._serialize_summary(doc)

    def store_lead_status(
        self,
        *,
        call_id: str,
        call_sid: str,
        customer_id: str,
        analysis: CallAnalysisResult,
    ) -> LeadStatusUpdateResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "customer_id": customer_id,
            "status": analysis.lead_status.value,
            "reason": analysis.intent,
            "created_at": now,
        }

        try:
            result = MongoDB.lead_status_updates().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        doc["_id"] = result.inserted_id
        return self._serialize_lead_status(doc)

    def store_call_outcome(
        self,
        *,
        call_id: str,
        call_sid: str,
        customer_id: str,
        analysis: CallAnalysisResult,
    ) -> CallOutcomeResponse:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "customer_id": customer_id,
            "outcome": analysis.call_outcome.value,
            "created_at": now,
        }

        try:
            result = MongoDB.call_outcomes().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        doc["_id"] = result.inserted_id
        return self._serialize_outcome(doc)

    def create_sync_log(
        self,
        *,
        call_id: str,
        call_sid: str,
        provider: str,
        status: CRMSyncStatus = CRMSyncStatus.PENDING,
    ) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "call_id": call_id,
            "provider": provider,
            "status": status.value,
            "attempts": 0,
            "error_message": "",
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = MongoDB.crm_sync_logs().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return str(result.inserted_id)

    def update_sync_log(
        self,
        log_id: str,
        *,
        status: CRMSyncStatus,
        attempts: int,
        error_message: str = "",
    ) -> None:
        try:
            oid = ObjectId(log_id)
        except Exception:
            return

        try:
            MongoDB.crm_sync_logs().update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": status.value,
                        "attempts": attempts,
                        "error_message": error_message,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
        except PyMongoError as exc:
            logger.error("Failed to update CRM sync log: %s", exc)

    def get_summary_by_call_id(self, call_id: str) -> Optional[ConversationSummaryResponse]:
        try:
            doc = MongoDB.conversation_summaries().find_one({"call_id": call_id})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_summary(doc) if doc else None

    def get_outcome_by_call_id(self, call_id: str) -> Optional[CallOutcomeResponse]:
        try:
            doc = MongoDB.call_outcomes().find_one({"call_id": call_id})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_outcome(doc) if doc else None

    def get_status_by_call_id(self, call_id: str) -> Optional[LeadStatusUpdateResponse]:
        try:
            doc = (
                MongoDB.lead_status_updates()
                .find({"call_id": call_id})
                .sort("created_at", -1)
                .limit(1)
            )
            docs = list(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_lead_status(docs[0]) if docs else None

    def get_sync_logs(self, limit: int = 50) -> list[CRMSyncLogResponse]:
        try:
            cursor = (
                MongoDB.crm_sync_logs()
                .find()
                .sort("created_at", -1)
                .limit(limit)
            )
            return [self._serialize_sync_log(doc) for doc in cursor]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_analytics_summary(self) -> CRMAnalyticsSummary:
        """Compute CRM-enriched analytics across all calls."""
        try:
            analytics_col = MongoDB.conversation_analytics()
            status_col = MongoDB.lead_status_updates()
            sync_col = MongoDB.crm_sync_logs()

            total_calls = analytics_col.count_documents({})
            successful_calls = analytics_col.count_documents({"reminder_successful": True})
            escalations = analytics_col.count_documents({"escalation_triggered": True})

            interested = status_col.count_documents({"status": "INTERESTED"})
            callbacks = status_col.count_documents({"status": "CALLBACK_REQUESTED"})
            payment_promises = status_col.count_documents({"status": "PAYMENT_PROMISED"})

            pipeline = [
                {"$match": {"duration_seconds": {"$ne": None}}},
                {"$group": {"_id": None, "avg": {"$avg": "$duration_seconds"}}},
            ]
            avg_result = list(analytics_col.aggregate(pipeline))
            avg_duration = avg_result[0]["avg"] if avg_result else 0.0

            total_syncs = sync_col.count_documents({})
            successful_syncs = sync_col.count_documents({"status": "SUCCESS"})
            sync_rate = (successful_syncs / total_syncs * 100) if total_syncs > 0 else 0.0

        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return CRMAnalyticsSummary(
            total_calls=total_calls,
            successful_calls=successful_calls,
            interested_customers=interested,
            callback_requests=callbacks,
            payment_promises=payment_promises,
            escalations=escalations,
            average_call_duration_seconds=round(avg_duration or 0.0, 1),
            crm_sync_success_rate=round(sync_rate, 1),
        )

    @staticmethod
    def _serialize_summary(doc: dict[str, Any]) -> ConversationSummaryResponse:
        return ConversationSummaryResponse(
            id=str(doc["_id"]),
            call_sid=doc.get("call_sid", ""),
            call_id=doc["call_id"],
            customer_id=doc["customer_id"],
            summary=doc["summary"],
            intent=doc.get("intent", ""),
            follow_up_actions=doc.get("follow_up_actions", []),
            follow_up_date=doc.get("follow_up_date"),
            follow_up_time=doc.get("follow_up_time"),
            created_at=doc["created_at"],
        )

    @staticmethod
    def _serialize_lead_status(doc: dict[str, Any]) -> LeadStatusUpdateResponse:
        from app.models.crm import LeadStatus

        return LeadStatusUpdateResponse(
            id=str(doc["_id"]),
            call_sid=doc.get("call_sid", ""),
            call_id=doc["call_id"],
            customer_id=doc["customer_id"],
            status=LeadStatus(doc["status"]),
            reason=doc.get("reason", ""),
            created_at=doc["created_at"],
        )

    @staticmethod
    def _serialize_outcome(doc: dict[str, Any]) -> CallOutcomeResponse:
        from app.models.crm import CallOutcome

        return CallOutcomeResponse(
            id=str(doc["_id"]),
            call_sid=doc.get("call_sid", ""),
            call_id=doc["call_id"],
            customer_id=doc["customer_id"],
            outcome=CallOutcome(doc["outcome"]),
            created_at=doc["created_at"],
        )

    @staticmethod
    def _serialize_sync_log(doc: dict[str, Any]) -> CRMSyncLogResponse:
        return CRMSyncLogResponse(
            id=str(doc["_id"]),
            call_sid=doc.get("call_sid", ""),
            call_id=doc.get("call_id", ""),
            provider=doc["provider"],
            status=CRMSyncStatus(doc["status"]),
            attempts=doc.get("attempts", 0),
            error_message=doc.get("error_message", ""),
            created_at=doc["created_at"],
            updated_at=doc.get("updated_at"),
        )
