"""Callback scheduling persistence."""

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.tool import CallbackResponse

logger = logging.getLogger(__name__)


class CallbackService:
    """Manages scheduled callbacks in MongoDB."""

    def schedule(
        self,
        customer_id: str,
        date: str,
        time: str,
        *,
        call_id: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Schedule a callback and persist to MongoDB."""
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "customer_id": customer_id,
            "date": date,
            "time": time,
            "status": "scheduled",
            "call_id": call_id,
            "notes": notes,
            "created_at": now,
        }

        try:
            result = MongoDB.callbacks().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        logger.info(
            "Callback scheduled | customer_id=%s date=%s time=%s",
            customer_id,
            date,
            time,
        )

        return {
            "scheduled": True,
            "callback_id": str(result.inserted_id),
            "date": date,
            "time": time,
        }

    def list_by_customer(self, customer_id: str) -> list[CallbackResponse]:
        """List callbacks for a customer."""
        try:
            cursor = (
                MongoDB.callbacks()
                .find({"customer_id": customer_id})
                .sort("created_at", -1)
            )
            return [self._serialize(doc) for doc in cursor]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def list_all(self) -> list[CallbackResponse]:
        """List all scheduled callbacks."""
        try:
            cursor = MongoDB.callbacks().find().sort("created_at", -1)
            return [self._serialize(doc) for doc in cursor]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> CallbackResponse:
        return CallbackResponse(
            id=str(doc["_id"]),
            customer_id=doc["customer_id"],
            date=doc["date"],
            time=doc["time"],
            status=doc.get("status", "scheduled"),
            call_id=doc.get("call_id", ""),
            notes=doc.get("notes", ""),
            created_at=doc["created_at"],
        )
