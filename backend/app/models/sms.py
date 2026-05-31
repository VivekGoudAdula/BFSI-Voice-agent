"""SMS delivery log models."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SmsStatus = Literal["SENT", "FAILED"]


class SmsLogResponse(BaseModel):
    """SMS delivery audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str = ""
    phone: str
    message: str
    status: SmsStatus
    twilio_sid: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


class SmsDeliveryResult(BaseModel):
    """Result returned by SMSService.send_sms."""

    success: bool
    phone: str
    twilio_sid: Optional[str] = None
    status: SmsStatus
    error: Optional[str] = None
    log_id: Optional[str] = None
