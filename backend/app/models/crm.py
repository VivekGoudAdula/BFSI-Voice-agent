"""CRM integration domain models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LeadStatus(str, Enum):
    """Automated lead status classification."""

    INTERESTED = "INTERESTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
    PAYMENT_PROMISED = "PAYMENT_PROMISED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    ESCALATED = "ESCALATED"
    NO_RESPONSE = "NO_RESPONSE"
    WRONG_NUMBER = "WRONG_NUMBER"
    DISCONNECTED = "DISCONNECTED"


class CallOutcome(str, Enum):
    """Call outcome classification."""

    SUCCESSFUL = "SUCCESSFUL"
    FOLLOW_UP_REQUIRED = "FOLLOW_UP_REQUIRED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    TRANSFERRED_TO_AGENT = "TRANSFERRED_TO_AGENT"
    FAILED = "FAILED"


class CRMProviderType(str, Enum):
    """Supported CRM providers."""

    SALESFORCE = "salesforce"
    ZOHO = "zoho"
    LEADSQUARED = "leadsquared"


class CRMSyncStatus(str, Enum):
    """CRM synchronization status."""

    SUCCESS = "SUCCESS"
    PENDING = "PENDING"
    RETRY = "RETRY"
    FAILED = "FAILED"


class FollowUpRequest(BaseModel):
    """Extracted follow-up scheduling details."""

    follow_up_date: Optional[str] = None
    follow_up_time: Optional[str] = None
    notes: str = ""


class CallAnalysisResult(BaseModel):
    """Structured output from post-call conversation analysis."""

    summary: str
    lead_status: LeadStatus
    call_outcome: CallOutcome
    intent: str = ""
    follow_up_actions: list[str] = Field(default_factory=list)
    follow_up: FollowUpRequest = Field(default_factory=FollowUpRequest)
    confidence: float = 0.0


class ConversationSummaryResponse(BaseModel):
    """Stored conversation summary."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    call_sid: str
    call_id: str
    customer_id: str
    summary: str
    intent: str = ""
    follow_up_actions: list[str] = Field(default_factory=list)
    follow_up_date: Optional[str] = None
    follow_up_time: Optional[str] = None
    created_at: datetime


class LeadStatusUpdateResponse(BaseModel):
    """Stored lead status classification."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    call_sid: str
    call_id: str
    customer_id: str
    status: LeadStatus
    reason: str
    created_at: datetime


class CallOutcomeResponse(BaseModel):
    """Stored call outcome."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    call_sid: str
    call_id: str
    customer_id: str
    outcome: CallOutcome
    created_at: datetime


class CRMSyncLogResponse(BaseModel):
    """CRM synchronization audit log."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    call_sid: str
    call_id: str
    provider: str
    status: CRMSyncStatus
    attempts: int
    error_message: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None


class ProcessedCallData(BaseModel):
    """Aggregated call data for CRM sync."""

    call_id: str
    call_sid: str
    customer_id: str
    customer_name: str
    customer_phone: str
    loan_id: str = ""
    transcript: str
    summary: str
    lead_status: LeadStatus
    call_outcome: CallOutcome
    intent: str = ""
    follow_up_actions: list[str] = Field(default_factory=list)
    follow_up_date: Optional[str] = None
    follow_up_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    escalation_triggered: bool = False
    escalation_reason: str = ""
    tools_used: list[str] = Field(default_factory=list)
    agent_context: dict[str, Any] = Field(default_factory=dict)


class CRMAnalyticsSummary(BaseModel):
    """Extended analytics including CRM metrics."""

    total_calls: int = 0
    successful_calls: int = 0
    interested_customers: int = 0
    callback_requests: int = 0
    payment_promises: int = 0
    escalations: int = 0
    average_call_duration_seconds: float = 0.0
    crm_sync_success_rate: float = 0.0
