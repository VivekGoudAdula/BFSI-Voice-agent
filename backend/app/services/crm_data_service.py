"""Internal CRM data persistence for summaries, outcomes, and status updates."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import PyMongoError

from app.database.mongodb import MongoDB
from app.models.crm import (
    CallAnalysisResult,
    CallOutcomeResponse,
    ConversationSummaryResponse,
    CRMAnalyticsSummary,
    LeadStatusUpdateResponse,
)
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class CRMDataService:
    """Persists call data to MongoDB (internal CRM layer)."""

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
            docs = find_sorted(
                MongoDB.lead_status_updates(),
                {"call_id": call_id},
                sort_field="created_at",
                sort_direction=-1,
                limit=1,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_lead_status(docs[0]) if docs else None

    def get_analytics_summary(self) -> CRMAnalyticsSummary:
        """Compute internal CRM analytics across all calls."""
        try:
            analytics_col = MongoDB.conversation_analytics()
            status_col = MongoDB.lead_status_updates()

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
