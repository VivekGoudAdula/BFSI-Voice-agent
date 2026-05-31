"""Agent configuration persistence and retrieval."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.agents.seed.emi_reminder_agent import (
    EMI_REMINDER_AGENT_NAME,
    build_emi_reminder_agent,
)
from app.core.config import Settings
from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.agent import AgentConfig, AgentConfigCreate
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class AgentConfigService:
    """CRUD operations for agent_configs collection."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def seed_default_agents(self) -> None:
        """Ensure default agents exist in the database."""
        if self.get_agent_by_name(EMI_REMINDER_AGENT_NAME):
            logger.info("EMI Reminder Agent already seeded")
            return

        agent = build_emi_reminder_agent(voice_id=self._settings.elevenlabs_voice_id)
        self.create_agent(agent)
        logger.info("Seeded default EMI Reminder Agent")

    def create_agent(self, config: AgentConfig | AgentConfigCreate) -> AgentConfig:
        """Insert a new agent configuration."""
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "agent_name": config.agent_name,
            "purpose": config.purpose,
            "language": config.language,
            "voice": config.voice,
            "system_prompt": config.system_prompt,
            "rules": config.rules,
            "escalation_rules": [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in config.escalation_rules
            ],
            "objection_rules": [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in config.objection_rules
            ],
            "greeting_template": config.greeting_template,
            "escalation_message": (
                config.escalation_message
                or "I understand. Let me connect you with a banking representative."
            ),
            "unavailable_info_message": (
                config.unavailable_info_message
                or "I do not have access to that information right now. "
                "Let me connect you with a banking representative."
            ),
            "version": getattr(config, "version", 1),
            "is_active": config.is_active,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = MongoDB.agent_configs().insert_one(doc)
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return self._serialize({**doc, "_id": result.inserted_id})

    def get_agent_by_id(self, agent_id: str) -> Optional[AgentConfig]:
        """Fetch agent config by MongoDB ID."""
        try:
            oid = ObjectId(agent_id)
        except Exception:
            return None

        try:
            doc = MongoDB.agent_configs().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return self._serialize(doc) if doc else None

    def get_agent_by_name(self, agent_name: str) -> Optional[AgentConfig]:
        """Fetch agent config by name."""
        try:
            doc = MongoDB.agent_configs().find_one({"agent_name": agent_name})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return self._serialize(doc) if doc else None

    def get_default_agent(self) -> Optional[AgentConfig]:
        """Return the default active agent (EMI Reminder)."""
        agent = self.get_agent_by_name(EMI_REMINDER_AGENT_NAME)
        if agent:
            return agent

        try:
            doc = MongoDB.agent_configs().find_one({"is_active": True})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return self._serialize(doc) if doc else None

    def list_agents(self) -> list[AgentConfig]:
        """List all agent configurations."""
        try:
            docs = find_sorted(
                MongoDB.agent_configs(), sort_field="created_at", sort_direction=-1
            )
            return [self._serialize(doc) for doc in docs]
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

    def update_agent(
        self,
        agent_id: str,
        updates: AgentConfigCreate,
    ) -> Optional[AgentConfig]:
        """Update an agent config and increment version."""
        try:
            oid = ObjectId(agent_id)
        except Exception:
            return None

        existing = MongoDB.agent_configs().find_one({"_id": oid})
        if not existing:
            return None

        new_version = existing.get("version", 1) + 1
        update_doc: dict[str, Any] = {
            "agent_name": updates.agent_name,
            "purpose": updates.purpose,
            "language": updates.language,
            "voice": updates.voice,
            "system_prompt": updates.system_prompt,
            "rules": updates.rules,
            "escalation_rules": [r.model_dump() for r in updates.escalation_rules],
            "objection_rules": [r.model_dump() for r in updates.objection_rules],
            "greeting_template": updates.greeting_template,
            "is_active": updates.is_active,
            "version": new_version,
            "updated_at": datetime.now(timezone.utc),
        }
        if updates.escalation_message:
            update_doc["escalation_message"] = updates.escalation_message
        if updates.unavailable_info_message:
            update_doc["unavailable_info_message"] = updates.unavailable_info_message

        try:
            MongoDB.agent_configs().update_one({"_id": oid}, {"$set": update_doc})
            doc = MongoDB.agent_configs().find_one({"_id": oid})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        return self._serialize(doc) if doc else None

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> AgentConfig:
        return AgentConfig(
            id=str(doc["_id"]),
            agent_name=doc["agent_name"],
            purpose=doc["purpose"],
            language=doc.get("language", "English"),
            voice=doc.get("voice", ""),
            system_prompt=doc["system_prompt"],
            rules=doc.get("rules", []),
            escalation_rules=doc.get("escalation_rules", []),
            objection_rules=doc.get("objection_rules", []),
            greeting_template=doc.get("greeting_template", ""),
            escalation_message=doc.get(
                "escalation_message",
                "I understand. Let me connect you with a banking representative.",
            ),
            unavailable_info_message=doc.get(
                "unavailable_info_message",
                "I do not have access to that information right now. "
                "Let me connect you with a banking representative.",
            ),
            version=doc.get("version", 1),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )
