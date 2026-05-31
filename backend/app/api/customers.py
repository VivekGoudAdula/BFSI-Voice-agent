"""Customer management endpoints."""

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_call_service, get_customer_service
from app.models.call import CallResponse
from app.models.customer import (
    CustomerCreate,
    CustomerListItem,
    CustomerResponse,
    CustomerUpdate,
)
from app.services.call_service import CallService, _serialize_call
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
    description="Register a new customer with name and E.164 phone number.",
)
def create_customer(
    payload: CustomerCreate,
    service: CustomerService = Depends(get_customer_service),
) -> CustomerResponse:
    return service.create_customer(payload)


@router.get(
    "",
    response_model=list[CustomerListItem],
    summary="List all customers",
    description="Retrieve customers with loan ID and last call info for admin portal.",
)
def get_customers(
    search: str = Query("", description="Search by name or phone"),
    service: CustomerService = Depends(get_customer_service),
) -> list[CustomerListItem]:
    return service.get_customers_enriched(search=search)


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get customer by ID",
)
def get_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
) -> CustomerResponse:
    return service.get_customer(customer_id)


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update customer",
)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    service: CustomerService = Depends(get_customer_service),
) -> CustomerResponse:
    return service.update_customer(customer_id, payload)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete customer",
)
def delete_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
) -> None:
    service.delete_customer(customer_id)


@router.get(
    "/{customer_id}/calls",
    response_model=list[CallResponse],
    summary="Get customer call history",
)
def get_customer_calls(
    customer_id: str,
    customer_service: CustomerService = Depends(get_customer_service),
    call_service: CallService = Depends(get_call_service),
) -> list[CallResponse]:
    docs = customer_service.get_customer_calls(customer_id)
    return [_serialize_call(doc) for doc in docs]
