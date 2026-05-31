"""Agent configuration, escalation, and analytics domain models."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.states import ConversationState


class EscalationRule(BaseModel):
    """Rule that triggers escalation to a human agent."""

    trigger: str = Field(..., description="Trigger identifier, e.g. customer_requested_human")
    patterns: list[str] = Field(default_factory=list, description="User phrase patterns")
    description: str = ""


class ObjectionRule(BaseModel):
    """Approved response for a common customer objection."""

    scenario: str
    trigger_patterns: list[str]
    response: str


class AgentConfig(BaseModel):
    """Configurable agent definition stored in MongoDB."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    agent_name: str
    purpose: str
    language: str = "English"
    voice: str = ""
    system_prompt: str
    rules: list[str] = Field(default_factory=list)
    escalation_rules: list[EscalationRule] = Field(default_factory=list)
    objection_rules: list[ObjectionRule] = Field(default_factory=list)
    greeting_template: str = ""
    escalation_message: str = (
        "I understand. Let me connect you with a banking representative who can assist you further."
    )
    unavailable_info_message: str = (
        "I do not have access to that information right now. "
        "Let me connect you with a banking representative."
    )
    version: int = 1
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentConfigCreate(BaseModel):
    """Request body for creating or updating an agent config."""

    agent_name: str
    purpose: str
    language: str = "English"
    voice: str = ""
    system_prompt: str
    rules: list[str] = Field(default_factory=list)
    escalation_rules: list[EscalationRule] = Field(default_factory=list)
    objection_rules: list[ObjectionRule] = Field(default_factory=list)
    greeting_template: str = ""
    escalation_message: str = ""
    unavailable_info_message: str = ""
    is_active: bool = True


class EscalationResult(BaseModel):
    """Output from the escalation engine."""

    escalate: bool = False
    reason: str = ""


class AgentTurnContext(BaseModel):
    """Runtime context for a single conversation turn."""

    customer_name: str = ""
    customer_id: str = ""
    call_id: str = ""
    call_sid: str = ""
    current_state: ConversationState = ConversationState.GREETING
    identity_verified: bool = False
    agent_context: dict[str, Any] = Field(default_factory=dict)
    objections_raised: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Result of response validation."""

    is_valid: bool
    violations: list[str] = Field(default_factory=list)


class ConversationAnalytics(BaseModel):
    """Per-call analytics record."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    call_id: str
    agent_id: str
    agent_name: str
    customer_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    final_state: ConversationState = ConversationState.GREETING
    identity_verified: bool = False
    reminder_successful: bool = False
    objections_raised: list[str] = Field(default_factory=list)
    escalation_triggered: bool = False
    escalation_reason: str = ""
    turn_count: int = 0
    completed: bool = False


class AnalyticsSummary(BaseModel):
    """Aggregated analytics across all conversations."""

    total_conversations: int = 0
    successful_reminders: int = 0
    objections_raised: int = 0
    escalations: int = 0
    average_call_duration_seconds: float = 0.0
    completion_rate: float = 0.0
