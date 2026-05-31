"""SMS delivery log API endpoints."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_sms_service
from app.models.sms import SmsLogResponse
from app.services.sms_service import SMSService

router = APIRouter(prefix="/sms", tags=["SMS"])


@router.get(
    "/logs",
    response_model=list[SmsLogResponse],
    summary="List recent SMS delivery logs",
)
def list_sms_logs(
    limit: int = 100,
    service: SMSService = Depends(get_sms_service),
) -> list[SmsLogResponse]:
    return service.list_logs(limit=limit)


@router.get(
    "/logs/{customer_id}",
    response_model=list[SmsLogResponse],
    summary="List SMS delivery logs for a customer",
)
def list_customer_sms_logs(
    customer_id: str,
    service: SMSService = Depends(get_sms_service),
) -> list[SmsLogResponse]:
    return service.list_by_customer(customer_id)
