"""Human handoff and escalation domain models (Phase 7)."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EscalationCategory(str, Enum):
    """Standardized escalation categories."""

    CUSTOMER_REQUESTED_HUMAN = "CUSTOMER_REQUESTED_HUMAN"
    COMPLAINT = "COMPLAINT"
    LEGAL_QUERY = "LEGAL_QUERY"
    ACCOUNT_DISPUTE = "ACCOUNT_DISPUTE"
    NEGATIVE_SENTIMENT = "NEGATIVE_SENTIMENT"
    HIGH_RISK_QUERY = "HIGH_RISK_QUERY"


class SentimentLevel(str, Enum):
    """Sentiment classification for conversation analysis."""

    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    VERY_NEGATIVE = "VERY_NEGATIVE"


class TransferPriority(str, Enum):
    """Transfer queue priority levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TransferQueueStatus(str, Enum):
    """Status of a transfer queue entry."""

    WAITING = "WAITING"
    ASSIGNED = "ASSIGNED"
    TRANSFERRED = "TRANSFERRED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class HandoffLogStatus(str, Enum):
    """Status recorded in human_handoff_logs."""

    QUEUED = "QUEUED"
    TRANSFERRED = "TRANSFERRED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class EscalationAnalysisResult(BaseModel):
    """Output from the escalation detection engine."""

    should_escalate: bool = False
    category: Optional[EscalationCategory] = None
    reason: str = ""
    sentiment: SentimentLevel = SentimentLevel.NEUTRAL


class HandoffContextPackage(BaseModel):
    """Conversation context attached before human transfer."""

    customer_name: str = ""
    customer_id: str = ""
    call_id: str = ""
    call_sid: str = ""
    call_reason: str = ""
    summary: str = ""
    sentiment: str = ""
    transcript_id: str = ""
    tool_usage: list[str] = Field(default_factory=list)
    agent_id: str = ""
    escalation_category: str = ""
    escalation_reason: str = ""
    messages_snapshot: list[dict[str, str]] = Field(default_factory=list)


class EscalationResponse(BaseModel):
    """API response for an escalation record."""

    id: str
    call_sid: str
    customer_id: str
    escalation_type: str
    reason: str
    created_at: datetime
    call_id: Optional[str] = None


class HumanHandoffLogResponse(BaseModel):
    """API response for a human handoff log."""

    id: str
    call_sid: str
    customer_id: str
    status: str
    transferred_at: datetime
    call_id: Optional[str] = None
    escalation_id: Optional[str] = None


class TransferQueueItemResponse(BaseModel):
    """API response for a transfer queue entry."""

    id: str
    customer_id: str
    call_sid: str
    category: str
    priority: str
    status: str
    created_at: datetime
    call_id: Optional[str] = None
    reason: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class HandoffAnalyticsSummary(BaseModel):
    """Aggregated handoff and escalation metrics."""

    total_escalations: int = 0
    escalation_rate: float = 0.0
    complaint_escalations: int = 0
    legal_escalations: int = 0
    negative_sentiment_escalations: int = 0
    human_transfer_count: int = 0
    human_transfer_rate: float = 0.0
    total_calls: int = 0
    queue_waiting: int = 0
    queue_high_priority: int = 0


class TransferToHumanRequest(BaseModel):
    """Input schema for transfer_to_human tool."""

    reason: str = ""
    category: str = ""


class TransferToHumanResult(BaseModel):
    """Output schema for transfer_to_human tool."""

    transferred: bool = False
    queue_id: Optional[str] = None
    escalation_id: Optional[str] = None
