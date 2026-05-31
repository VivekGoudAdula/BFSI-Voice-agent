"""Agent configuration persistence — legacy facade delegating to AgentManager."""

import logging
from typing import Any, Optional

from app.core.config import Settings
from app.models.agent import AgentConfig, AgentConfigCreate

logger = logging.getLogger(__name__)


class AgentConfigService:
    """Backward-compatible facade over the Phase 9 AgentManager."""

    def __init__(self, settings: Settings, agent_manager: Any = None) -> None:
        self._settings = settings
        self._manager = agent_manager

    def _get_manager(self):
        if self._manager is None:
            from app.core.dependencies import get_agent_manager

            self._manager = get_agent_manager()
        return self._manager

    def seed_default_agents(self) -> None:
        self._get_manager().seed_default_agents()

    def create_agent(self, config: AgentConfig | AgentConfigCreate) -> AgentConfig:
        from app.models.agent import AgentCreateRequest

        payload = AgentCreateRequest(
            agent_id=config.agent_name.lower().replace(" ", "_"),
            name=config.agent_name,
            description=config.purpose,
            purpose=config.purpose,
            voice_id=config.voice,
            language="en",
            system_prompt=config.system_prompt,
            tools=[],
            compliance_rules=config.rules,
            escalation_rules=config.escalation_rules,
            objection_rules=config.objection_rules,
            greeting_template=config.greeting_template,
            escalation_message=config.escalation_message,
            unavailable_info_message=config.unavailable_info_message,
            status="ACTIVE" if config.is_active else "INACTIVE",
        )
        doc = self._get_manager().register(payload)
        return self._get_manager().load_agent(doc.agent_id).to_agent_config()

    def get_agent_by_id(self, agent_id: str) -> Optional[AgentConfig]:
        try:
            return self._get_manager().load_agent(agent_id).to_agent_config()
        except Exception:
            return None

    def get_agent_by_name(self, agent_name: str) -> Optional[AgentConfig]:
        for doc in self._get_manager().list_agents():
            if doc.name == agent_name:
                return self._get_manager().load_agent(doc.agent_id).to_agent_config()
        return None

    def get_default_agent(self) -> Optional[AgentConfig]:
        try:
            return self._get_manager().get_default_agent().to_agent_config()
        except Exception:
            return None

    def list_agents(self) -> list[AgentConfig]:
        return [
            self._get_manager().load_agent(doc.agent_id).to_agent_config()
            for doc in self._get_manager().list_agents()
        ]

    def update_agent(
        self, agent_id: str, updates: AgentConfigCreate
    ) -> Optional[AgentConfig]:
        from app.models.agent import AgentUpdateRequest

        payload = AgentUpdateRequest(
            name=updates.agent_name,
            description=updates.purpose,
            purpose=updates.purpose,
            voice_id=updates.voice,
            language="en",
            system_prompt=updates.system_prompt,
            tools=[],
            compliance_rules=updates.rules,
            escalation_rules=updates.escalation_rules,
            objection_rules=updates.objection_rules,
            greeting_template=updates.greeting_template,
            escalation_message=updates.escalation_message,
            unavailable_info_message=updates.unavailable_info_message,
            status="ACTIVE" if updates.is_active else "INACTIVE",
        )
        doc = self._get_manager().update_agent(agent_id, payload)
        return self._get_manager().load_agent(doc.agent_id).to_agent_config()
