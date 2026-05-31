"""Customer CRUD operations."""

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.exceptions import CustomerNotFoundError, DatabaseError
from app.core.logging_config import log_with_context
from app.database.mongodb import MongoDB
from app.models.customer import CustomerCreate, CustomerListItem, CustomerResponse, CustomerUpdate
from app.utils.mongo_query import find_one_sorted, find_sorted
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

    def get_customers_enriched(
        self, search: str = ""
    ) -> list[CustomerListItem]:
        """List customers with loan ID and last call info for admin portal."""
        try:
            query: dict[str, Any] = {}
            if search.strip():
                pattern = {"$regex": search.strip(), "$options": "i"}
                query = {"$or": [{"name": pattern}, {"phone": pattern}]}

            docs = find_sorted(
                MongoDB.customers(),
                query=query,
                sort_field="created_at",
                sort_direction=-1,
            )

            items: list[CustomerListItem] = []
            for doc in docs:
                customer_id = str(doc["_id"])
                loan_id = self._get_loan_id(customer_id, doc.get("phone", ""))
                last_call = self._get_last_call(customer_id)
                status = "active"
                if last_call:
                    status = last_call.get("status", "active")

                items.append(
                    CustomerListItem(
                        id=customer_id,
                        name=doc["name"],
                        phone=doc["phone"],
                        created_at=doc["created_at"],
                        loan_id=loan_id,
                        status=status,
                        last_call_at=last_call.get("created_at") if last_call else None,
                        last_call_status=last_call.get("status", "") if last_call else "",
                    )
                )
            return items
        except PyMongoError as exc:
            logger.error("Failed to fetch enriched customers: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def _get_loan_id(self, customer_id: str, phone: str) -> str:
        cc = find_one_sorted(
            MongoDB.campaign_customers(),
            {"$or": [{"customer_id": customer_id}, {"phone": phone}]},
            sort_field="created_at",
            sort_direction=-1,
        )
        return cc.get("loan_id", "") if cc else ""

    def _get_last_call(self, customer_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(customer_id)
        except Exception:
            return None
        return find_one_sorted(
            MongoDB.calls(),
            {"customer_id": oid},
            sort_field="created_at",
            sort_direction=-1,
        )

    def get_customer(self, customer_id: str) -> CustomerResponse:
        doc = self.get_customer_by_id(customer_id)
        if not doc:
            raise CustomerNotFoundError(customer_id)
        return _serialize_customer(doc)

    def update_customer(
        self, customer_id: str, data: CustomerUpdate
    ) -> CustomerResponse:
        doc = self.get_customer_by_id(customer_id)
        if not doc:
            raise CustomerNotFoundError(customer_id)

        phone = validate_phone(data.phone)
        update = {
            "name": data.name.strip(),
            "phone": phone,
        }

        try:
            MongoDB.customers().update_one(
                {"_id": doc["_id"]}, {"$set": update}
            )
        except PyMongoError as exc:
            logger.error("Failed to update customer %s: %s", customer_id, exc)
            raise DatabaseError(str(exc)) from exc

        doc.update(update)
        return _serialize_customer(doc)

    def delete_customer(self, customer_id: str) -> None:
        doc = self.get_customer_by_id(customer_id)
        if not doc:
            raise CustomerNotFoundError(customer_id)

        try:
            MongoDB.customers().delete_one({"_id": doc["_id"]})
        except PyMongoError as exc:
            logger.error("Failed to delete customer %s: %s", customer_id, exc)
            raise DatabaseError(str(exc)) from exc

    def get_customer_calls(self, customer_id: str) -> list[dict[str, Any]]:
        doc = self.get_customer_by_id(customer_id)
        if not doc:
            raise CustomerNotFoundError(customer_id)

        try:
            return find_sorted(
                MongoDB.calls(),
                query={"customer_id": doc["_id"]},
                sort_field="created_at",
                sort_direction=-1,
            )
        except PyMongoError as exc:
            logger.error("Failed to fetch customer calls: %s", exc)
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
