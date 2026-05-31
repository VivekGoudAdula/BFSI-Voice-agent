"""Customer domain models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    """Request body for creating a customer."""

    name: str = Field(..., min_length=1, max_length=200, examples=["John Doe"])
    phone: str = Field(..., examples=["+919876543210"])


class CustomerUpdate(BaseModel):
    """Request body for updating a customer."""

    name: str = Field(..., min_length=1, max_length=200)
    phone: str = Field(..., examples=["+919876543210"])


class CustomerResponse(BaseModel):
    """Customer record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    phone: str
    created_at: datetime


class CustomerListItem(CustomerResponse):
    """Customer with admin portal enrichment."""

    loan_id: str = ""
    status: str = "active"
    last_call_at: Optional[datetime] = None
    last_call_status: str = ""
