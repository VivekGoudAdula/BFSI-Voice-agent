"""MongoDB access for multilingual configuration and preferences."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.language import AgentPromptTranslation, CustomerLanguagePreference

logger = logging.getLogger(__name__)


class LanguageRepository:
    """Persistence for language preferences and prompt translations."""

    def get_customer_preference(
        self, customer_id: str
    ) -> Optional[CustomerLanguagePreference]:
        try:
            doc = MongoDB.customer_language_preferences().find_one(
                {"customer_id": customer_id}
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        if not doc:
            return None
        return CustomerLanguagePreference(
            id=str(doc["_id"]),
            customer_id=doc["customer_id"],
            language=doc["language"],
            confidence=doc.get("confidence", 0.0),
            updated_at=doc.get("updated_at"),
        )

    def upsert_customer_preference(
        self,
        customer_id: str,
        language: str,
        confidence: float,
    ) -> None:
        now = datetime.now(timezone.utc)
        try:
            MongoDB.customer_language_preferences().update_one(
                {"customer_id": customer_id},
                {
                    "$set": {
                        "customer_id": customer_id,
                        "language": language,
                        "confidence": confidence,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("Failed to upsert language preference: %s", exc)

    def list_prompt_translations(self, agent_id: str) -> list[AgentPromptTranslation]:
        try:
            docs = MongoDB.agent_prompt_translations().find({"agent_id": agent_id})
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return [self._serialize_translation(doc) for doc in docs]

    def get_prompt_translation(
        self, agent_id: str, language: str
    ) -> Optional[AgentPromptTranslation]:
        try:
            doc = MongoDB.agent_prompt_translations().find_one(
                {"agent_id": agent_id, "language": language}
            )
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc
        return self._serialize_translation(doc) if doc else None

    def upsert_prompt_translations(
        self, agent_id: str, translations: list[AgentPromptTranslation]
    ) -> None:
        now = datetime.now(timezone.utc)
        collection = MongoDB.agent_prompt_translations()
        for t in translations:
            doc: dict[str, Any] = {
                "agent_id": agent_id,
                "language": t.language,
                "system_prompt": t.system_prompt,
                "greeting_template": t.greeting_template,
                "escalation_message": t.escalation_message,
                "unavailable_info_message": t.unavailable_info_message,
                "language_instruction": t.language_instruction,
                "updated_at": now,
            }
            try:
                collection.update_one(
                    {"agent_id": agent_id, "language": t.language},
                    {"$set": doc, "$setOnInsert": {"created_at": now}},
                    upsert=True,
                )
            except PyMongoError as exc:
                logger.error(
                    "Failed to upsert prompt translation %s/%s: %s",
                    agent_id,
                    t.language,
                    exc,
                )

    def record_language_switch(self, event: dict[str, Any]) -> None:
        try:
            MongoDB.language_switch_events().insert_one(event)
        except PyMongoError as exc:
            logger.error("Failed to record language switch: %s", exc)

    def increment_language_call_stats(
        self,
        agent_id: str,
        language: str,
        *,
        successful: bool = False,
        switched: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        inc: dict[str, int] = {f"calls_by_language.{language}": 1}
        if successful:
            inc[f"success_by_language.{language}"] = 1
        if switched:
            inc["language_switch_events"] = 1
        try:
            MongoDB.language_analytics().update_one(
                {"agent_id": agent_id},
                {
                    "$inc": inc,
                    "$set": {"updated_at": now},
                    "$setOnInsert": {"agent_id": agent_id, "created_at": now},
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("Failed to update language analytics: %s", exc)

    @staticmethod
    def _serialize_translation(doc: dict[str, Any]) -> AgentPromptTranslation:
        return AgentPromptTranslation(
            agent_id=doc["agent_id"],
            language=doc["language"],
            system_prompt=doc.get("system_prompt", ""),
            greeting_template=doc.get("greeting_template", ""),
            escalation_message=doc.get("escalation_message", ""),
            unavailable_info_message=doc.get("unavailable_info_message", ""),
            language_instruction=doc.get("language_instruction", ""),
        )
