"""Campaign engine domain models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CampaignStatus(str, Enum):
    """Campaign lifecycle status."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class CampaignRunStatus(str, Enum):
    """Individual campaign run status."""

    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"


class CampaignCustomerStatus(str, Enum):
    """Per-customer status within a campaign."""

    PENDING = "pending"
    CALLING = "calling"
    COMPLETED = "completed"
    FAILED = "failed"
    CALLBACK_REQUESTED = "callback_requested"
    ESCALATED = "escalated"


class CampaignCreateRequest(BaseModel):
    """Request body for creating a campaign."""

    name: str = Field(..., min_length=1, examples=["EMI Reminder Campaign"])
    description: str = Field(default="", examples=["June EMI Reminder"])
    agent_id: str = Field(default="emi_agent", examples=["emi_agent"])


class CampaignResponse(BaseModel):
    """Campaign record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str = ""
    agent_id: str = ""
    status: CampaignStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    total_customers: int = 0


class CSVImportResult(BaseModel):
    """Result of CSV customer import."""

    total_rows: int
    imported: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class CampaignRunResponse(BaseModel):
    """Campaign execution run record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: CampaignRunStatus


class CampaignCustomerResponse(BaseModel):
    """Campaign customer record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    customer_name: str
    phone: str
    loan_id: str
    status: CampaignCustomerStatus
    call_id: Optional[str] = None
    customer_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CampaignAnalyticsResponse(BaseModel):
    """Aggregated campaign analytics."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    total_customers: int = 0
    calls_initiated: int = 0
    completed_calls: int = 0
    failed_calls: int = 0
    callbacks: int = 0
    escalations: int = 0
    interested_customers: int = 0
    payment_promises: int = 0
    average_call_duration_seconds: float = 0.0
    completion_rate: float = 0.0
    updated_at: Optional[datetime] = None


class CampaignResultItem(BaseModel):
    """Combined call result for a campaign customer."""

    customer: CampaignCustomerResponse
    summary: Optional[str] = None
    lead_status: Optional[str] = None
    call_outcome: Optional[str] = None
    follow_up_date: Optional[str] = None
    call_status: Optional[str] = None
    duration_seconds: Optional[float] = None


class CampaignStartResponse(BaseModel):
    """Response when a campaign is started."""

    campaign_id: str
    run_id: str
    status: CampaignStatus
    message: str
