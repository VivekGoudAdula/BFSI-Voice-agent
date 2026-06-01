"""Build runtime agent instances from MongoDB configuration."""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config.languages import SUPPORTED_LANGUAGES
from app.models.agent import AgentConfig, EscalationRule, ObjectionRule
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class RuntimeAgent:
    """Fully resolved agent ready for conversation injection."""

    agent_id: str
    mongo_id: str
    name: str
    description: str
    status: str
    voice_id: str
    language: str
    language_name: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    compliance_rules: list[str] = field(default_factory=list)
    escalation_rules: list[EscalationRule] = field(default_factory=list)
    objection_rules: list[ObjectionRule] = field(default_factory=list)
    greeting_template: str = ""
    escalation_message: str = ""
    unavailable_info_message: str = ""
    purpose: str = ""
    version: int = 1
    supported_languages: list[str] = field(default_factory=lambda: ["en", "hi"])
    default_language: str = "en"
    config: Optional[AgentConfig] = None

    def to_agent_config(self) -> AgentConfig:
        """Return AgentConfig compatible with the conversation engine."""
        if self.config:
            return self.config
        self.config = AgentConfig(
            id=self.mongo_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            purpose=self.purpose or self.description,
            description=self.description,
            language=self.language_name,
            language_code=self.language,
            supported_languages=list(self.supported_languages),
            default_language=self.default_language,
            voice=self.voice_id,
            system_prompt=self.system_prompt,
            rules=self.compliance_rules,
            compliance_rules=self.compliance_rules,
            tools=self.tools,
            escalation_rules=self.escalation_rules,
            objection_rules=self.objection_rules,
            greeting_template=self.greeting_template,
            escalation_message=self.escalation_message,
            unavailable_info_message=self.unavailable_info_message,
            status=self.status,
            version=self.version,
            is_active=self.status == "ACTIVE",
        )
        return self.config


class AgentLoader:
    """Load agent config from MongoDB and build runtime agents with injected context."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    def build_from_document(self, doc: dict[str, Any]) -> RuntimeAgent:
        """Build a RuntimeAgent from a MongoDB agent document."""
        language_code = doc.get("default_language") or doc.get("language", "en")
        language_name = SUPPORTED_LANGUAGES.get(language_code, "English")
        supported_languages = doc.get("supported_languages") or ["en", "hi"]
        default_language = doc.get("default_language") or language_code
        voice_id = doc.get("voice_id", "") or doc.get("voice", "")

        escalation_rules = [
            EscalationRule(**r) if isinstance(r, dict) else r
            for r in doc.get("escalation_rules", [])
        ]
        objection_rules = [
            ObjectionRule(**r) if isinstance(r, dict) else r
            for r in doc.get("objection_rules", [])
        ]

        system_prompt = self._inject_language(
            doc.get("system_prompt", ""),
            language_code,
            language_name,
        )

        tools = list(doc.get("tools", []))
        compliance_rules = list(doc.get("compliance_rules", doc.get("rules", [])))

        runtime = RuntimeAgent(
            agent_id=doc["agent_id"],
            mongo_id=str(doc["_id"]),
            name=doc.get("name", doc.get("agent_name", "")),
            description=doc.get("description", doc.get("purpose", "")),
            status=doc.get("status", "ACTIVE"),
            voice_id=voice_id,
            language=language_code,
            language_name=language_name,
            system_prompt=system_prompt,
            tools=tools,
            compliance_rules=compliance_rules,
            escalation_rules=escalation_rules,
            objection_rules=objection_rules,
            greeting_template=doc.get("greeting_template", ""),
            escalation_message=doc.get(
                "escalation_message",
                "I understand. Let me connect you with a banking representative "
                "who can assist you further.",
            ),
            unavailable_info_message=doc.get(
                "unavailable_info_message",
                "I do not have access to that information right now. "
                "Let me connect you with a banking representative.",
            ),
            purpose=doc.get("purpose", doc.get("description", "")),
            version=doc.get("version", 1),
            supported_languages=supported_languages,
            default_language=default_language,
        )
        runtime.to_agent_config()
        return runtime

    def get_tool_schemas(self, tool_names: list[str]) -> list[dict]:
        """Return OpenAI-compatible schemas for the agent's assigned tools."""
        return self._tools.get_openai_schemas(tool_names)

    @staticmethod
    def _inject_language(
        system_prompt: str,
        language_code: str,
        language_name: str,
    ) -> str:
        if language_code == "en":
            return system_prompt
        return (
            f"{system_prompt}\n\n"
            f"## Language\n"
            f"Respond to the customer in {language_name} ({language_code}). "
            f"Use natural, conversational {language_name} throughout the call."
        )
