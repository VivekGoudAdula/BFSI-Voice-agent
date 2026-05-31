"""Conversation analytics tracking for BFSI agents."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.agents.states import ConversationState
from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.agent import AnalyticsSummary, ConversationAnalytics

logger = logging.getLogger(__name__)


class AgentAnalyticsService:
    """Tracks and aggregates conversation analytics in MongoDB."""

    def start_conversation(
        self,
        call_id: str,
        agent_id: str,
        agent_name: str,
        customer_id: str,
    ) -> str:
        """Create an analytics record when a call session starts."""
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_id": call_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "customer_id": customer_id,
            "started_at": now,
            "ended_at": None,
            "duration_seconds": None,
            "final_state": ConversationState.GREETING.value,
            "identity_verified": False,
            "reminder_successful": False,
            "objections_raised": [],
            "escalation_triggered": False,
            "escalation_reason": "",
            "turn_count": 0,
            "completed": False,
        }

        try:
            result = MongoDB.conversation_analytics().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return str(result.inserted_id)

    def update_turn(
        self,
        analytics_id: str,
        *,
        current_state: ConversationState,
        identity_verified: bool = False,
        objections_raised: list[str] | None = None,
        escalation_triggered: bool = False,
        escalation_reason: str = "",
    ) -> None:
        """Update analytics after each conversation turn."""
        try:
            oid = ObjectId(analytics_id)
        except Exception:
            return

        update: dict[str, Any] = {
            "final_state": current_state.value,
            "identity_verified": identity_verified,
            "turn_count_increment": 1,
        }

        set_fields: dict[str, Any] = {
            "final_state": current_state.value,
            "identity_verified": identity_verified,
        }

        if objections_raised:
            set_fields["objections_raised"] = objections_raised
        if escalation_triggered:
            set_fields["escalation_triggered"] = True
            set_fields["escalation_reason"] = escalation_reason

        try:
            MongoDB.conversation_analytics().update_one(
                {"_id": oid},
                {
                    "$set": set_fields,
                    "$inc": {"turn_count": 1},
                },
            )
        except PyMongoError as exc:
            logger.error("Failed to update analytics turn: %s", exc)

    def end_conversation(
        self,
        analytics_id: str,
        *,
        final_state: ConversationState,
        identity_verified: bool = False,
        reminder_successful: bool = False,
        objections_raised: list[str] | None = None,
        escalation_triggered: bool = False,
        escalation_reason: str = "",
        started_at: datetime | None = None,
    ) -> None:
        """Finalize analytics when a call ends."""
        try:
            oid = ObjectId(analytics_id)
        except Exception:
            return

        now = datetime.now(timezone.utc)
        duration = None
        if started_at:
            duration = (now - started_at).total_seconds()

        completed = final_state in (
            ConversationState.CALL_COMPLETION,
            ConversationState.ESCALATION,
        )

        set_fields: dict[str, Any] = {
            "ended_at": now,
            "duration_seconds": duration,
            "final_state": final_state.value,
            "identity_verified": identity_verified,
            "reminder_successful": reminder_successful,
            "escalation_triggered": escalation_triggered,
            "escalation_reason": escalation_reason,
            "completed": completed,
        }
        if objections_raised:
            set_fields["objections_raised"] = objections_raised

        try:
            MongoDB.conversation_analytics().update_one(
                {"_id": oid},
                {"$set": set_fields},
            )
        except PyMongoError as exc:
            logger.error("Failed to finalize analytics: %s", exc)

    def get_by_call_id(self, call_id: str) -> Optional[ConversationAnalytics]:
        """Fetch analytics for a specific call."""
        try:
            doc = MongoDB.conversation_analytics().find_one({"call_id": call_id})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return self._serialize(doc) if doc else None

    def get_summary(self) -> AnalyticsSummary:
        """Compute aggregated analytics across all conversations."""
        try:
            collection = MongoDB.conversation_analytics()
            total = collection.count_documents({})
            successful = collection.count_documents({"reminder_successful": True})
            escalations = collection.count_documents({"escalation_triggered": True})
            completed = collection.count_documents({"completed": True})

            pipeline = [
                {"$match": {"duration_seconds": {"$ne": None}}},
                {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_seconds"}}},
            ]
            avg_result = list(collection.aggregate(pipeline))
            avg_duration = avg_result[0]["avg_duration"] if avg_result else 0.0

            objection_pipeline = [
                {"$project": {"count": {"$size": {"$ifNull": ["$objections_raised", []]}}}},
                {"$group": {"_id": None, "total": {"$sum": "$count"}}},
            ]
            objection_result = list(collection.aggregate(objection_pipeline))
            objections = objection_result[0]["total"] if objection_result else 0

        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        completion_rate = (completed / total * 100) if total > 0 else 0.0

        return AnalyticsSummary(
            total_conversations=total,
            successful_reminders=successful,
            objections_raised=objections,
            escalations=escalations,
            average_call_duration_seconds=round(avg_duration or 0.0, 1),
            completion_rate=round(completion_rate, 1),
        )

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> ConversationAnalytics:
        return ConversationAnalytics(
            id=str(doc["_id"]),
            call_id=doc["call_id"],
            agent_id=doc["agent_id"],
            agent_name=doc["agent_name"],
            customer_id=doc["customer_id"],
            started_at=doc["started_at"],
            ended_at=doc.get("ended_at"),
            duration_seconds=doc.get("duration_seconds"),
            final_state=ConversationState(doc.get("final_state", "GREETING")),
            identity_verified=doc.get("identity_verified", False),
            reminder_successful=doc.get("reminder_successful", False),
            objections_raised=doc.get("objections_raised", []),
            escalation_triggered=doc.get("escalation_triggered", False),
            escalation_reason=doc.get("escalation_reason", ""),
            turn_count=doc.get("turn_count", 0),
            completed=doc.get("completed", False),
        )
