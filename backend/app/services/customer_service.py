"""Customer CRUD operations."""

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.core.logging_config import log_with_context
from app.database.mongodb import MongoDB
from app.models.customer import CustomerCreate, CustomerResponse
from app.utils.mongo_query import find_sorted
from app.utils.phone import validate_phone

logger = logging.getLogger(__name__)


def _serialize_customer(doc: dict[str, Any]) -> CustomerResponse:
    return CustomerResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        phone=doc["phone"],
        created_at=doc["created_at"],
    )


class CustomerService:
    """Manages customer records in MongoDB."""

    def create_customer(self, data: CustomerCreate) -> CustomerResponse:
        phone = validate_phone(data.phone)
        document = {
            "name": data.name.strip(),
            "phone": phone,
            "created_at": datetime.now(timezone.utc),
        }

        try:
            result = MongoDB.customers().insert_one(document)
        except PyMongoError as exc:
            logger.error("Failed to create customer: %s", exc)
            raise DatabaseError(str(exc)) from exc

        document["_id"] = result.inserted_id

        log_with_context(
            logger,
            logging.INFO,
            "Customer created",
            customer_id=str(result.inserted_id),
            phone=phone,
            event="customer_created",
        )

        return _serialize_customer(document)

    def get_customers(self) -> list[CustomerResponse]:
        try:
            docs = find_sorted(
                MongoDB.customers(), sort_field="created_at", sort_direction=-1
            )
            return [_serialize_customer(doc) for doc in docs]
        except PyMongoError as exc:
            logger.error("Failed to fetch customers: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def get_customer_by_phone(self, phone: str) -> dict[str, Any] | None:
        """Fetch customer by normalized phone number."""
        normalized = validate_phone(phone)
        try:
            return MongoDB.customers().find_one({"phone": normalized})
        except PyMongoError as exc:
            logger.error("Failed to fetch customer by phone: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def get_or_create(self, data: CustomerCreate) -> CustomerResponse:
        """Return existing customer by phone or create a new one."""
        phone = validate_phone(data.phone)
        existing = self.get_customer_by_phone(phone)
        if existing:
            return _serialize_customer(existing)
        return self.create_customer(data)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any] | None:
        """Fetch raw customer document; returns None if not found or invalid ID."""
        try:
            oid = ObjectId(customer_id)
        except Exception:
            return None

        try:
            return MongoDB.customers().find_one({"_id": oid})
        except PyMongoError as exc:
            logger.error("Failed to fetch customer %s: %s", customer_id, exc)
            raise DatabaseError(str(exc)) from exc
