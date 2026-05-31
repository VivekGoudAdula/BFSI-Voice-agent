"""Conversation and transcript domain models."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessage(BaseModel):
    """Single message in a conversation session."""

    role: Literal["system", "user", "assistant"]
    content: str


class ConversationSessionResponse(BaseModel):
    """Full conversation session returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    call_id: str
    call_sid: str
    customer_id: str
    agent_id: str = ""
    current_state: str = "GREETING"
    identity_verified: bool = False
    messages: list[ConversationMessage]
    started_at: datetime
    updated_at: datetime


class TranscriptEntry(BaseModel):
    """Individual transcript line."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime


class TranscriptResponse(BaseModel):
    """Formatted transcript for a call."""

    call_id: str
    call_sid: str
    customer_id: str
    entries: list[TranscriptEntry]
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LatencyMetrics(BaseModel):
    """Latency measurements for a conversation turn."""

    stt_ms: Optional[float] = None
    groq_ms: Optional[float] = None
    elevenlabs_ms: Optional[float] = None
    total_ms: Optional[float] = None
