"""MongoDB repository for the agents collection."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class AgentRepository:
    """Data access layer for agent configurations."""

    def insert(self, doc: dict[str, Any]) -> str:
        try:
            result = MongoDB.agents().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_by_mongo_id(self, mongo_id: str) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(mongo_id)
        if not oid:
            return None
        try:
            return MongoDB.agents().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_by_agent_id(self, agent_id: str) -> Optional[dict[str, Any]]:
        try:
            return MongoDB.agents().find_one({"agent_id": agent_id})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def find_by_identifier(self, identifier: str) -> Optional[dict[str, Any]]:
        """Resolve agent by slug (agent_id) or MongoDB ObjectId."""
        doc = self.get_by_agent_id(identifier)
        if doc:
            return doc
        return self.get_by_mongo_id(identifier)

    def list_all(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if active_only:
            query["status"] = "ACTIVE"
        try:
            return find_sorted(
                MongoDB.agents(), query, sort_field="created_at", sort_direction=-1
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def update(self, mongo_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        oid = self._to_object_id(mongo_id)
        if not oid:
            return None
        updates["updated_at"] = datetime.now(timezone.utc)
        try:
            MongoDB.agents().update_one({"_id": oid}, {"$set": updates})
            return MongoDB.agents().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def set_status(self, mongo_id: str, status: str) -> Optional[dict[str, Any]]:
        return self.update(mongo_id, {"status": status})

    def upsert_by_agent_id(self, agent_id: str, doc: dict[str, Any]) -> str:
        """Insert or update agent by slug — used for seeding."""
        existing = self.get_by_agent_id(agent_id)
        now = datetime.now(timezone.utc)
        if existing:
            mongo_id = str(existing["_id"])
            doc.pop("created_at", None)
            doc["updated_at"] = now
            self.update(mongo_id, doc)
            return mongo_id

        doc.setdefault("created_at", now)
        doc.setdefault("updated_at", now)
        try:
            result = MongoDB.agents().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def get_campaign_agent(self, campaign_id: str) -> Optional[str]:
        """Return agent_id slug mapped to a campaign."""
        try:
            doc = MongoDB.campaign_agent_mapping().find_one(
                {"campaign_id": campaign_id}
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return doc.get("agent_id") if doc else None

    def set_campaign_agent(self, campaign_id: str, agent_id: str) -> None:
        now = datetime.now(timezone.utc)
        try:
            MongoDB.campaign_agent_mapping().update_one(
                {"campaign_id": campaign_id},
                {
                    "$set": {
                        "campaign_id": campaign_id,
                        "agent_id": agent_id,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    @staticmethod
    def _to_object_id(value: str) -> Optional[ObjectId]:
        try:
            return ObjectId(value)
        except Exception:
            return None
