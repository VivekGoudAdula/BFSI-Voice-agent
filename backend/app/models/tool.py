"""Tool models for execution logs and callbacks."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CallbackCreate(BaseModel):
    """Request to schedule a callback."""

    customer_id: str
    date: str = Field(..., examples=["2026-06-01"])
    time: str = Field(..., examples=["10:00 AM"])
    call_id: str = ""
    notes: str = ""


class CallbackResponse(BaseModel):
    """Scheduled callback record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    date: str
    time: str
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"
    call_id: str = ""
    notes: str = ""
    created_at: datetime


class ToolExecutionLogResponse(BaseModel):
    """Tool execution audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    call_id: str
    call_sid: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    success: bool
    execution_time_ms: float
    executed_at: datetime


class ToolCallRequest(BaseModel):
    """Structured tool invocation (for testing/debug)."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    customer_id: str = ""
    call_id: str = ""
    call_sid: str = ""


class ToolCallResponse(BaseModel):
    """Result of a manual tool invocation."""

    tool_name: str
    success: bool
    result: dict[str, Any]
    execution_time_ms: float
