"""Internal CRM domain models (MongoDB-backed)."""

from datetime import datetime
from enum import Enum
from typing import Optional

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


class CRMAnalyticsSummary(BaseModel):
    """Internal CRM analytics across all calls."""

    total_calls: int = 0
    successful_calls: int = 0
    interested_customers: int = 0
    callback_requests: int = 0
    payment_promises: int = 0
    escalations: int = 0
    average_call_duration_seconds: float = 0.0
