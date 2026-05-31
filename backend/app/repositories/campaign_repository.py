"""MongoDB repository for campaign collections."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.campaign import (
    CampaignAnalyticsResponse,
    CampaignCustomerResponse,
    CampaignCustomerStatus,
    CampaignResponse,
    CampaignRunResponse,
    CampaignRunStatus,
    CampaignStatus,
)
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class CampaignRepository:
    """Data access layer for campaigns, customers, runs, and analytics."""

    # --- Campaigns ---

    def create_campaign(self, name: str, description: str = "") -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "name": name.strip(),
            "description": description.strip(),
            "status": CampaignStatus.DRAFT.value,
            "created_at": now,
            "started_at": None,
            "ended_at": None,
        }
        try:
            result = MongoDB.campaigns().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_campaign(self, campaign_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(campaign_id)
        if not oid:
            return None
        try:
            return MongoDB.campaigns().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def list_campaigns(self) -> list[dict[str, Any]]:
        try:
            return find_sorted(
                MongoDB.campaigns(), sort_field="created_at", sort_direction=-1
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def update_campaign_status(
        self,
        campaign_id: str,
        status: CampaignStatus,
        *,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> None:
        oid = self._to_object_id(campaign_id)
        if not oid:
            return
        updates: dict[str, Any] = {"status": status.value}
        if started_at is not None:
            updates["started_at"] = started_at
        if ended_at is not None:
            updates["ended_at"] = ended_at
        try:
            MongoDB.campaigns().update_one({"_id": oid}, {"$set": updates})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- Campaign customers ---

    def insert_campaign_customers(
        self, campaign_id: str, customers: list[dict[str, Any]]
    ) -> int:
        if not customers:
            return 0
        now = datetime.now(timezone.utc)
        docs = [
            {
                "campaign_id": campaign_id,
                "customer_name": c["customer_name"],
                "phone": c["phone"],
                "loan_id": c["loan_id"],
                "status": CampaignCustomerStatus.PENDING.value,
                "call_id": None,
                "customer_id": None,
                "created_at": now,
                "updated_at": now,
            }
            for c in customers
        ]
        try:
            result = MongoDB.campaign_customers().insert_many(docs)
            return len(result.inserted_ids)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_campaign_customers(
        self,
        campaign_id: str,
        *,
        status: Optional[CampaignCustomerStatus] = None,
        limit: int = 0,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"campaign_id": campaign_id}
        if status:
            query["status"] = status.value
        try:
            return find_sorted(
                MongoDB.campaign_customers(),
                query,
                sort_field="created_at",
                sort_direction=1,
                limit=limit,
                skip=skip,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_campaign_customer(self, customer_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(customer_id)
        if not oid:
            return None
        try:
            return MongoDB.campaign_customers().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def count_campaign_customers(
        self, campaign_id: str, status: Optional[CampaignCustomerStatus] = None
    ) -> int:
        query: dict[str, Any] = {"campaign_id": campaign_id}
        if status:
            query["status"] = status.value
        try:
            return MongoDB.campaign_customers().count_documents(query)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def update_campaign_customer(
        self, customer_id: str, updates: dict[str, Any]
    ) -> None:
        oid = self._to_object_id(customer_id)
        if not oid:
            return
        updates["updated_at"] = datetime.now(timezone.utc)
        try:
            MongoDB.campaign_customers().update_one({"_id": oid}, {"$set": updates})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def claim_pending_customers(
        self, campaign_id: str, limit: int
    ) -> list[dict[str, Any]]:
        """Atomically claim pending customers for calling."""
        claimed: list[dict[str, Any]] = []
        try:
            for _ in range(limit):
                doc = MongoDB.campaign_customers().find_one_and_update(
                    {
                        "campaign_id": campaign_id,
                        "status": CampaignCustomerStatus.PENDING.value,
                    },
                    {
                        "$set": {
                            "status": CampaignCustomerStatus.CALLING.value,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if not doc:
                    break
                claimed.append(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return claimed

    # --- Campaign runs ---

    def create_run(self, campaign_id: str) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "campaign_id": campaign_id,
            "started_at": now,
            "ended_at": None,
            "status": CampaignRunStatus.RUNNING.value,
        }
        try:
            result = MongoDB.campaign_runs().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(run_id)
        if not oid:
            return None
        try:
            return MongoDB.campaign_runs().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_active_run(self, campaign_id: str) -> Optional[dict[str, Any]]:
        try:
            return MongoDB.campaign_runs().find_one(
                {
                    "campaign_id": campaign_id,
                    "status": CampaignRunStatus.RUNNING.value,
                }
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def end_run(self, run_id: str, status: CampaignRunStatus) -> None:
        oid = self._to_object_id(run_id)
        if not oid:
            return
        try:
            MongoDB.campaign_runs().update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": status.value,
                        "ended_at": datetime.now(timezone.utc),
                    }
                },
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- Campaign analytics ---

    def init_analytics(self, campaign_id: str, total_customers: int) -> str:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "campaign_id": campaign_id,
            "total_customers": total_customers,
            "calls_initiated": 0,
            "completed_calls": 0,
            "failed_calls": 0,
            "callbacks": 0,
            "escalations": 0,
            "interested_customers": 0,
            "payment_promises": 0,
            "total_duration_seconds": 0.0,
            "duration_count": 0,
            "updated_at": now,
        }
        try:
            existing = MongoDB.campaign_analytics().find_one(
                {"campaign_id": campaign_id}
            )
            if existing:
                MongoDB.campaign_analytics().update_one(
                    {"campaign_id": campaign_id},
                    {
                        "$set": {
                            "total_customers": total_customers,
                            "updated_at": now,
                        }
                    },
                )
                return str(existing["_id"])
            result = MongoDB.campaign_analytics().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def increment_analytics(
        self, campaign_id: str, increments: dict[str, Any]
    ) -> None:
        """Increment analytics counters atomically."""
        set_fields: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc),
        }
        inc_fields: dict[str, Any] = {}
        for key, value in increments.items():
            if key == "duration_seconds":
                inc_fields["total_duration_seconds"] = value
                inc_fields["duration_count"] = 1
            else:
                inc_fields[key] = value

        update: dict[str, Any] = {"$set": set_fields}
        if inc_fields:
            update["$inc"] = inc_fields

        try:
            MongoDB.campaign_analytics().update_one(
                {"campaign_id": campaign_id}, update, upsert=True
            )
        except PyMongoError as exc:
            logger.error("Failed to increment campaign analytics: %s", exc)

    def get_analytics(self, campaign_id: str) -> Optional[dict[str, Any]]:
        try:
            return MongoDB.campaign_analytics().find_one(
                {"campaign_id": campaign_id}
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    # --- Serialization ---

    def serialize_campaign(
        self, doc: dict[str, Any], total_customers: int = 0
    ) -> CampaignResponse:
        return CampaignResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            description=doc.get("description", ""),
            status=CampaignStatus(doc["status"]),
            created_at=doc["created_at"],
            started_at=doc.get("started_at"),
            ended_at=doc.get("ended_at"),
            total_customers=total_customers,
        )

    def serialize_customer(self, doc: dict[str, Any]) -> CampaignCustomerResponse:
        return CampaignCustomerResponse(
            id=str(doc["_id"]),
            campaign_id=doc["campaign_id"],
            customer_name=doc["customer_name"],
            phone=doc["phone"],
            loan_id=doc["loan_id"],
            status=CampaignCustomerStatus(doc["status"]),
            call_id=doc.get("call_id"),
            customer_id=doc.get("customer_id"),
            created_at=doc["created_at"],
            updated_at=doc.get("updated_at"),
        )

    def serialize_run(self, doc: dict[str, Any]) -> CampaignRunResponse:
        return CampaignRunResponse(
            id=str(doc["_id"]),
            campaign_id=doc["campaign_id"],
            started_at=doc["started_at"],
            ended_at=doc.get("ended_at"),
            status=CampaignRunStatus(doc["status"]),
        )

    def serialize_analytics(self, doc: dict[str, Any]) -> CampaignAnalyticsResponse:
        total = doc.get("total_customers", 0)
        completed = doc.get("completed_calls", 0)
        duration_count = doc.get("duration_count", 0)
        total_duration = doc.get("total_duration_seconds", 0.0)
        avg_duration = (
            total_duration / duration_count if duration_count > 0 else 0.0
        )
        completion_rate = (completed / total * 100) if total > 0 else 0.0

        return CampaignAnalyticsResponse(
            id=str(doc["_id"]),
            campaign_id=doc["campaign_id"],
            total_customers=total,
            calls_initiated=doc.get("calls_initiated", 0),
            completed_calls=completed,
            failed_calls=doc.get("failed_calls", 0),
            callbacks=doc.get("callbacks", 0),
            escalations=doc.get("escalations", 0),
            interested_customers=doc.get("interested_customers", 0),
            payment_promises=doc.get("payment_promises", 0),
            average_call_duration_seconds=round(avg_duration, 1),
            completion_rate=round(completion_rate, 1),
            updated_at=doc.get("updated_at"),
        )

    @staticmethod
    def _to_object_id(value: str) -> Optional[ObjectId]:
        try:
            return ObjectId(value)
        except Exception:
            return None
