"""Compliance and audit domain models (Phase 8)."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ComplianceEventType(str, Enum):
    """Standard compliance event taxonomy."""

    CALL_STARTED = "CALL_STARTED"
    DISCLOSURE_PLAYED = "DISCLOSURE_PLAYED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_DENIED = "CONSENT_DENIED"
    CONSENT_NO_RESPONSE = "CONSENT_NO_RESPONSE"
    USER_MESSAGE = "USER_MESSAGE"
    ASSISTANT_MESSAGE = "ASSISTANT_MESSAGE"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    ESCALATION_CREATED = "ESCALATION_CREATED"
    CALLBACK_SCHEDULED = "CALLBACK_SCHEDULED"
    CRM_UPDATED = "CRM_UPDATED"
    CALL_ENDED = "CALL_ENDED"
    PROMPT_VERSION_RECORDED = "PROMPT_VERSION_RECORDED"
    RECORDING_STORED = "RECORDING_STORED"


class ConsentStatus(str, Enum):
    """Customer consent outcomes."""

    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_DENIED = "CONSENT_DENIED"
    NO_RESPONSE = "NO_RESPONSE"
    PENDING = "PENDING"


class TranscriptMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime


class DisclosureResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    disclosure_text: str
    played: bool
    played_at: datetime


class ConsentResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    status: ConsentStatus
    captured_at: datetime


class CallRecordingResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    recording_url: str
    duration: Optional[float] = None
    storage_provider: str = "local"
    created_at: datetime


class ConsolidatedTranscriptResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    messages: list[TranscriptMessage]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PromptVersionResponse(BaseModel):
    id: str
    agent_name: str
    version: int
    prompt: str
    created_at: datetime


class CallPromptUsageResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    prompt_version: int
    agent_name: str
    agent_id: str = ""


class ToolAuditLogResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float
    executed_at: datetime


class CRMAuditLogResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    action: str
    previous_value: str = ""
    new_value: str = ""
    updated_at: datetime


class EscalationAuditLogResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    category: str
    reason: str
    created_at: datetime


class ComplianceEventResponse(BaseModel):
    id: str
    call_sid: str
    call_id: str = ""
    event_type: ComplianceEventType
    event_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class CallCompliancePackage(BaseModel):
    """Full compliance record for a single call."""

    call_sid: str
    call_id: str
    disclosure: Optional[DisclosureResponse] = None
    consent: Optional[ConsentResponse] = None
    recording: Optional[CallRecordingResponse] = None
    transcript: Optional[ConsolidatedTranscriptResponse] = None
    prompt_usage: Optional[CallPromptUsageResponse] = None
    summary: Optional[str] = None
    tool_executions: list[ToolAuditLogResponse] = Field(default_factory=list)
    crm_updates: list[CRMAuditLogResponse] = Field(default_factory=list)
    escalations: list[EscalationAuditLogResponse] = Field(default_factory=list)
    events: list[ComplianceEventResponse] = Field(default_factory=list)


class ComplianceDashboardSummary(BaseModel):
    total_calls: int
    calls_with_consent: int
    calls_without_consent: int
    recorded_calls: int
    escalated_calls: int
    tool_executions: int
    prompt_versions: int
    audit_events: int
