"""MongoDB repository for escalations, handoff logs, and transfer queue."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.handoff import (
    EscalationResponse,
    HandoffLogStatus,
    HumanHandoffLogResponse,
    TransferPriority,
    TransferQueueItemResponse,
    TransferQueueStatus,
)
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class HandoffRepository:
    """Data access layer for Phase 7 handoff collections."""

    def create_escalation(
        self,
        *,
        call_sid: str,
        customer_id: str,
        escalation_type: str,
        reason: str,
        call_id: str = "",
    ) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "customer_id": customer_id,
            "call_id": call_id,
            "escalation_type": escalation_type,
            "reason": reason,
            "created_at": now,
        }
        try:
            result = MongoDB.escalations().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_escalation(self, escalation_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(escalation_id)
        if not oid:
            return None
        try:
            return MongoDB.escalations().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def list_escalations(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            return find_sorted(
                MongoDB.escalations(),
                sort_field="created_at",
                sort_direction=-1,
                limit=limit,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def create_handoff_log(
        self,
        *,
        call_sid: str,
        customer_id: str,
        status: HandoffLogStatus,
        call_id: str = "",
        escalation_id: str = "",
    ) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "call_sid": call_sid,
            "customer_id": customer_id,
            "call_id": call_id,
            "status": status.value,
            "transferred_at": now,
            "escalation_id": escalation_id,
        }
        try:
            result = MongoDB.human_handoff_logs().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_handoff_log(self, log_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(log_id)
        if not oid:
            return None
        try:
            return MongoDB.human_handoff_logs().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def list_handoff_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            return find_sorted(
                MongoDB.human_handoff_logs(),
                sort_field="transferred_at",
                sort_direction=-1,
                limit=limit,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def enqueue_transfer(
        self,
        *,
        customer_id: str,
        call_sid: str,
        category: str,
        priority: TransferPriority,
        reason: str,
        call_id: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "customer_id": customer_id,
            "call_sid": call_sid,
            "call_id": call_id,
            "category": category,
            "priority": priority.value,
            "status": TransferQueueStatus.WAITING.value,
            "reason": reason,
            "context": context or {},
            "created_at": now,
        }
        try:
            result = MongoDB.transfer_queue().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_queue_item(self, queue_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(queue_id)
        if not oid:
            return None
        try:
            return MongoDB.transfer_queue().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def list_queue_items(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        try:
            return find_sorted(
                MongoDB.transfer_queue(),
                sort_field="created_at",
                sort_direction=-1,
                query=query,
                limit=limit,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def update_queue_status(self, queue_id: str, status: TransferQueueStatus) -> None:
        oid = self._to_object_id(queue_id)
        if not oid:
            return
        try:
            MongoDB.transfer_queue().update_one(
                {"_id": oid},
                {"$set": {"status": status.value}},
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def store_handoff_context(self, call_id: str, context: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        doc = {
            "call_id": call_id,
            "context": context,
            "created_at": now,
        }
        try:
            result = MongoDB.handoff_context().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def count_escalations_by_type(self, escalation_type: str) -> int:
        try:
            return MongoDB.escalations().count_documents(
                {"escalation_type": escalation_type}
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def count_escalations(self) -> int:
        try:
            return MongoDB.escalations().count_documents({})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def count_handoff_logs(self, status: Optional[str] = None) -> int:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        try:
            return MongoDB.human_handoff_logs().count_documents(query)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def count_queue_waiting(self) -> int:
        try:
            return MongoDB.transfer_queue().count_documents(
                {"status": TransferQueueStatus.WAITING.value}
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def count_queue_high_priority(self) -> int:
        try:
            return MongoDB.transfer_queue().count_documents(
                {
                    "status": TransferQueueStatus.WAITING.value,
                    "priority": TransferPriority.HIGH.value,
                }
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    @staticmethod
    def serialize_escalation(doc: dict[str, Any]) -> EscalationResponse:
        return EscalationResponse(
            id=str(doc["_id"]),
            call_sid=doc.get("call_sid", ""),
            customer_id=doc.get("customer_id", ""),
            escalation_type=doc.get("escalation_type", ""),
            reason=doc.get("reason", ""),
            created_at=doc.get("created_at"),
            call_id=doc.get("call_id") or None,
        )

    @staticmethod
    def serialize_handoff_log(doc: dict[str, Any]) -> HumanHandoffLogResponse:
        return HumanHandoffLogResponse(
            id=str(doc["_id"]),
            call_sid=doc.get("call_sid", ""),
            customer_id=doc.get("customer_id", ""),
            status=doc.get("status", ""),
            transferred_at=doc.get("transferred_at"),
            call_id=doc.get("call_id") or None,
            escalation_id=doc.get("escalation_id") or None,
        )

    @staticmethod
    def serialize_queue_item(doc: dict[str, Any]) -> TransferQueueItemResponse:
        return TransferQueueItemResponse(
            id=str(doc["_id"]),
            customer_id=doc.get("customer_id", ""),
            call_sid=doc.get("call_sid", ""),
            category=doc.get("category", ""),
            priority=doc.get("priority", ""),
            status=doc.get("status", ""),
            created_at=doc.get("created_at"),
            call_id=doc.get("call_id") or None,
            reason=doc.get("reason"),
            context=doc.get("context"),
        )

    @staticmethod
    def _to_object_id(value: str) -> Optional[ObjectId]:
        try:
            return ObjectId(value)
        except Exception:
            return None
