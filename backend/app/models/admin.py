"""Admin portal domain models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RecentActivityItem(BaseModel):
    """Single item in the dashboard activity feed."""

    id: str
    type: str
    title: str
    description: str = ""
    timestamp: datetime


class DashboardSummary(BaseModel):
    """Unified admin dashboard metrics."""

    total_calls: int = 0
    active_campaigns: int = 0
    completed_calls: int = 0
    escalations: int = 0
    callbacks: int = 0
    agents: int = 0
    customers: int = 0
    live_calls: int = 0
    call_success_rate: float = 0.0
    recent_activity: list[RecentActivityItem] = Field(default_factory=list)


class ActiveCallResponse(BaseModel):
    """Real-time active call session snapshot."""

    call_id: str
    call_sid: str
    customer_id: str
    customer_name: str
    agent_id: str
    agent_name: str = ""
    current_state: str
    duration_seconds: float = 0.0
    started_at: Optional[datetime] = None


class PlatformSettingsResponse(BaseModel):
    """Platform configuration for the admin settings page."""

    bank_name: str
    twilio_configured: bool
    twilio_phone_number: str
    groq_configured: bool
    groq_model: str
    elevenlabs_configured: bool
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    deepgram_configured: bool
    campaign_batch_size: int
    campaign_call_interval_seconds: float
    campaign_max_concurrent_calls: int
    handoff_enabled: bool
    human_agent_phone: str
    compliance_enabled: bool
    compliance_disclosure_template: str
    compliance_consent_prompt: str
    base_url: str


class PlatformSettingsUpdate(BaseModel):
    """Mutable platform settings (non-secret)."""

    bank_name: Optional[str] = None
    campaign_batch_size: Optional[int] = Field(None, ge=1, le=100)
    campaign_call_interval_seconds: Optional[float] = Field(None, ge=0.5, le=60)
    campaign_max_concurrent_calls: Optional[int] = Field(None, ge=1, le=200)
    handoff_enabled: Optional[bool] = None
    human_agent_phone: Optional[str] = None
    compliance_enabled: Optional[bool] = None
    compliance_disclosure_template: Optional[str] = None
    compliance_consent_prompt: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    groq_model: Optional[str] = None
