"""Call domain models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentCallContext(BaseModel):
    """Optional EMI/account context passed to the agent for a call."""

    emi_amount: str = Field(default="", examples=["Rs. 15,000"])
    due_date: str = Field(default="", examples=["15th June 2026"])
    loan_account: str = Field(default="", examples=["LN-123456"])
    payment_status: str = Field(default="", examples=["overdue"])


class CallInitiateRequest(BaseModel):
    """Request body for initiating an outbound call."""

    customer_id: str = Field(..., examples=["507f1f77bcf86cd799439011"])
    agent_id: str = Field(
        default="",
        description="Agent config ID. Uses default EMI Reminder Agent if empty.",
    )
    agent_context: AgentCallContext = Field(default_factory=AgentCallContext)


class CallResponse(BaseModel):
    """Call record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    phone: str
    status: str
    message: str
    twilio_call_sid: str = ""
    audio_file: Optional[str] = None
    agent_id: str = ""
    agent_name: str = ""
    created_at: datetime
