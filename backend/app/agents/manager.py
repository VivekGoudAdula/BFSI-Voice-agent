"""Agent lifecycle management: register, load, activate, deactivate, validate."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.loader import AgentLoader, RuntimeAgent
from app.agents.seed.default_agents import DEFAULT_AGENT_ID, build_default_agent_seeds
from app.agents.seed.language_prompts import build_emi_prompt_translations
from app.config.languages import SUPPORTED_LANGUAGES
from app.models.language import AgentPromptTranslation
from app.repositories.language_repository import LanguageRepository
from app.core.config import Settings
from app.core.exceptions import AgentNotFoundError, AgentValidationError
from app.models.agent import AgentCreateRequest, AgentDocument, AgentUpdateRequest
from app.repositories.agent_repository import AgentRepository
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentManager:
    """
    Central manager for multi-agent platform operations.

    Responsibilities: register, load, activate, deactivate, validate agents.
    """

    _cache: dict[str, RuntimeAgent] = {}

    def __init__(
        self,
        repository: AgentRepository,
        loader: AgentLoader,
        tool_registry: ToolRegistry,
        settings: Settings,
    ) -> None:
        self._repo = repository
        self._loader = loader
        self._tools = tool_registry
        self._settings = settings

    def seed_default_agents(self) -> None:
        """Upsert all default agent configurations from seed data."""
        default_voice = self._settings.elevenlabs_voice_id
        lang_repo = LanguageRepository()
        for seed in build_default_agent_seeds(default_voice):
            agent_id = seed["agent_id"]
            if not seed.get("voice_id"):
                seed["voice_id"] = default_voice
            mongo_id = self._repo.upsert_by_agent_id(agent_id, seed)
            self._ensure_analytics_record(agent_id)
            logger.info("Seeded agent: %s (mongo_id=%s)", agent_id, mongo_id)

        emi_translations = [
            AgentPromptTranslation(**t)
            for t in build_emi_prompt_translations(default_voice)
        ]
        lang_repo.upsert_prompt_translations("emi_agent", emi_translations)
        logger.info("Seeded %d prompt translations for emi_agent", len(emi_translations))

    def register(self, payload: AgentCreateRequest) -> AgentDocument:
        """Create and register a new agent after validation."""
        self.validate_config(
            voice_id=payload.voice_id or self._settings.elevenlabs_voice_id,
            tools=payload.tools,
            system_prompt=payload.system_prompt,
            language=payload.language,
            compliance_rules=payload.compliance_rules,
            status=payload.status,
        )

        if self._repo.get_by_agent_id(payload.agent_id):
            raise AgentValidationError(
                f"Agent with agent_id '{payload.agent_id}' already exists"
            )

        now = datetime.now(timezone.utc)
        doc = self._build_document(payload, now=now)
        mongo_id = self._repo.insert(doc)
        doc["_id"] = mongo_id
        self._ensure_analytics_record(payload.agent_id)
        self._invalidate_cache(payload.agent_id)
        return self._serialize(doc)

    def load_agent(self, identifier: str) -> RuntimeAgent:
        """Load and cache a runtime agent by slug or MongoDB ID."""
        if identifier in self._cache:
            cached = self._cache[identifier]
            if cached.status == "ACTIVE":
                return cached

        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)
        if doc.get("status") != "ACTIVE":
            raise AgentValidationError(
                f"Agent '{doc.get('agent_id', identifier)}' is not active"
            )

        runtime = self._loader.build_from_document(doc)
        self._cache[runtime.agent_id] = runtime
        self._cache[runtime.mongo_id] = runtime
        return runtime

    def get_default_agent(self) -> RuntimeAgent:
        """Return the default EMI agent, or first active agent."""
        doc = self._repo.get_by_agent_id(DEFAULT_AGENT_ID)
        if doc and doc.get("status") == "ACTIVE":
            return self.load_agent(doc["agent_id"])

        docs = self._repo.list_all(active_only=True)
        if not docs:
            raise AgentNotFoundError("default")
        return self.load_agent(docs[0]["agent_id"])

    def resolve_agent(self, agent_identifier: str = "") -> RuntimeAgent:
        """Resolve agent by identifier or fall back to default."""
        if agent_identifier:
            return self.load_agent(agent_identifier)
        return self.get_default_agent()

    def resolve_for_campaign(self, campaign_id: str, campaign_doc: dict) -> RuntimeAgent:
        """Resolve agent for a campaign from doc or mapping collection."""
        agent_id = campaign_doc.get("agent_id") or self._repo.get_campaign_agent(
            campaign_id
        )
        if agent_id:
            return self.load_agent(agent_id)
        return self.get_default_agent()

    def list_agents(self, *, active_only: bool = False) -> list[AgentDocument]:
        docs = self._repo.list_all(active_only=active_only)
        return [self._serialize(doc) for doc in docs]

    def get_agent(self, identifier: str) -> AgentDocument:
        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)
        return self._serialize(doc)

    def update_agent(
        self, identifier: str, payload: AgentUpdateRequest
    ) -> AgentDocument:
        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)

        voice_id = payload.voice_id or doc.get("voice_id", "")
        if not voice_id:
            voice_id = self._settings.elevenlabs_voice_id

        self.validate_config(
            voice_id=voice_id,
            tools=payload.tools,
            system_prompt=payload.system_prompt,
            language=payload.language,
            compliance_rules=payload.compliance_rules,
            status=payload.status,
        )

        mongo_id = str(doc["_id"])
        update_doc: dict[str, Any] = {
            "name": payload.name,
            "description": payload.description,
            "purpose": payload.purpose or payload.description,
            "status": payload.status,
            "voice_id": voice_id,
            "language": payload.language,
            "supported_languages": payload.supported_languages,
            "default_language": payload.default_language,
            "voice_configs": [vc.model_dump() for vc in payload.voice_configs],
            "system_prompt": payload.system_prompt,
            "tools": payload.tools,
            "compliance_rules": payload.compliance_rules,
            "escalation_rules": [r.model_dump() for r in payload.escalation_rules],
            "objection_rules": [r.model_dump() for r in payload.objection_rules],
            "greeting_template": payload.greeting_template,
            "version": doc.get("version", 1) + 1,
        }
        if payload.escalation_message:
            update_doc["escalation_message"] = payload.escalation_message
        if payload.unavailable_info_message:
            update_doc["unavailable_info_message"] = payload.unavailable_info_message

        updated = self._repo.update(mongo_id, update_doc)
        self._invalidate_cache(doc["agent_id"])
        return self._serialize(updated)

    def deactivate_agent(self, identifier: str) -> AgentDocument:
        """Soft-delete: set agent status to INACTIVE."""
        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)

        mongo_id = str(doc["_id"])
        updated = self._repo.set_status(mongo_id, "INACTIVE")
        self._invalidate_cache(doc["agent_id"])
        return self._serialize(updated)

    def activate_agent(self, identifier: str) -> AgentDocument:
        """Reactivate a deactivated agent after validation."""
        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)

        self.validate_config(
            voice_id=doc.get("voice_id") or self._settings.elevenlabs_voice_id,
            tools=doc.get("tools", []),
            system_prompt=doc.get("system_prompt", ""),
            language=doc.get("language", "en"),
            compliance_rules=doc.get("compliance_rules", []),
            status="ACTIVE",
        )

        mongo_id = str(doc["_id"])
        updated = self._repo.set_status(mongo_id, "ACTIVE")
        self._invalidate_cache(doc["agent_id"])
        return self._serialize(updated)

    def map_campaign_agent(self, campaign_id: str, agent_id: str) -> None:
        """Persist campaign-to-agent mapping."""
        self.load_agent(agent_id)
        self._repo.set_campaign_agent(campaign_id, agent_id)

    def validate_config(
        self,
        *,
        voice_id: str,
        tools: list[str],
        system_prompt: str,
        language: str,
        compliance_rules: list[str],
        status: str = "ACTIVE",
    ) -> None:
        """Validate agent configuration before activation."""
        errors: list[str] = []

        if not voice_id and status == "ACTIVE":
            errors.append("Voice ID is required for active agents")

        if not system_prompt or not system_prompt.strip():
            errors.append("System prompt is required")

        if language not in SUPPORTED_LANGUAGES:
            errors.append(
                f"Unsupported language '{language}'. "
                f"Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
            )

        if not compliance_rules:
            errors.append("At least one compliance rule is required")

        registered_tools = {t.name for t in self._tools.list_tools()}
        for tool_name in tools:
            if tool_name not in registered_tools:
                errors.append(f"Unknown tool: {tool_name}")

        if not tools:
            errors.append("At least one tool must be assigned")

        if errors:
            raise AgentValidationError("; ".join(errors))

    def get_agent_document_raw(self, identifier: str) -> dict[str, Any]:
        """Return raw MongoDB agent document for language runtime."""
        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)
        return doc

    def update_agent_languages(
        self,
        identifier: str,
        *,
        supported_languages: list[str],
        default_language: str,
        voice_configs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        doc = self._repo.find_by_identifier(identifier)
        if not doc:
            raise AgentNotFoundError(identifier)

        for lang in supported_languages:
            if lang not in SUPPORTED_LANGUAGES:
                raise AgentValidationError(f"Unsupported language: {lang}")
        if default_language not in supported_languages:
            raise AgentValidationError(
                "default_language must be in supported_languages"
            )

        mongo_id = str(doc["_id"])
        update_doc = {
            "supported_languages": supported_languages,
            "default_language": default_language,
            "voice_configs": voice_configs,
            "language": default_language,
            "updated_at": datetime.now(timezone.utc),
        }
        updated = self._repo.update(mongo_id, update_doc)
        self._invalidate_cache(doc["agent_id"])
        return updated

    def _build_document(
        self, payload: AgentCreateRequest, *, now: datetime
    ) -> dict[str, Any]:
        voice_id = payload.voice_id or self._settings.elevenlabs_voice_id
        return {
            "agent_id": payload.agent_id,
            "name": payload.name,
            "description": payload.description,
            "purpose": payload.purpose or payload.description,
            "status": payload.status,
            "voice_id": voice_id,
            "language": payload.language,
            "supported_languages": payload.supported_languages,
            "default_language": payload.default_language,
            "voice_configs": [vc.model_dump() for vc in payload.voice_configs],
            "system_prompt": payload.system_prompt,
            "tools": payload.tools,
            "compliance_rules": payload.compliance_rules,
            "escalation_rules": [r.model_dump() for r in payload.escalation_rules],
            "objection_rules": [r.model_dump() for r in payload.objection_rules],
            "greeting_template": payload.greeting_template,
            "escalation_message": payload.escalation_message
            or "I understand. Let me connect you with a banking representative.",
            "unavailable_info_message": payload.unavailable_info_message
            or "I do not have access to that information right now. "
            "Let me connect you with a banking representative.",
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }

    def _ensure_analytics_record(self, agent_id: str) -> None:
        from app.database.mongodb import MongoDB

        try:
            MongoDB.agent_analytics().update_one(
                {"agent_id": agent_id},
                {
                    "$setOnInsert": {
                        "agent_id": agent_id,
                        "total_calls": 0,
                        "successful_calls": 0,
                        "escalations": 0,
                        "callbacks": 0,
                        "avg_duration": 0.0,
                        "created_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
        except Exception as exc:
            logger.warning("Failed to ensure analytics record for %s: %s", agent_id, exc)

    def _invalidate_cache(self, agent_id: str) -> None:
        keys_to_remove = [
            key for key, val in self._cache.items()
            if val.agent_id == agent_id or key == agent_id
        ]
        for key in keys_to_remove:
            self._cache.pop(key, None)

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> AgentDocument:
        return AgentDocument(
            id=str(doc["_id"]),
            agent_id=doc["agent_id"],
            name=doc.get("name", ""),
            description=doc.get("description", ""),
            purpose=doc.get("purpose", doc.get("description", "")),
            status=doc.get("status", "ACTIVE"),
            voice_id=doc.get("voice_id", ""),
            language=doc.get("language", "en"),
            supported_languages=doc.get(
                "supported_languages",
                ["en", "hi", "te", "ta", "kn", "mr", "bn"],
            ),
            default_language=doc.get("default_language", doc.get("language", "en")),
            voice_configs=doc.get("voice_configs", []),
            system_prompt=doc.get("system_prompt", ""),
            tools=doc.get("tools", []),
            compliance_rules=doc.get("compliance_rules", []),
            escalation_rules=doc.get("escalation_rules", []),
            objection_rules=doc.get("objection_rules", []),
            greeting_template=doc.get("greeting_template", ""),
            escalation_message=doc.get("escalation_message", ""),
            unavailable_info_message=doc.get("unavailable_info_message", ""),
            version=doc.get("version", 1),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )
