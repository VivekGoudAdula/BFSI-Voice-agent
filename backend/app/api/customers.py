"""Customer management endpoints."""

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_customer_service
from app.models.customer import CustomerCreate, CustomerResponse
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
    response_model=list[CustomerResponse],
    summary="List all customers",
    description="Retrieve all registered customers ordered by creation date.",
)
def get_customers(
    service: CustomerService = Depends(get_customer_service),
) -> list[CustomerResponse]:
    return service.get_customers()
