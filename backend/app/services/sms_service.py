"""Twilio SMS delivery and audit logging."""

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import PyMongoError
from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from app.core.config import Settings
from app.core.exceptions import InvalidPhoneNumberError
from app.core.logging_config import log_with_context
from app.database.mongodb import MongoDB
from app.models.sms import SmsDeliveryResult, SmsLogResponse
from app.utils.mongo_query import find_sorted
from app.utils.phone import validate_phone

logger = logging.getLogger(__name__)


class SMSService:
    """Sends SMS via Twilio and persists delivery logs to MongoDB."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            if not self._settings.twilio_account_sid or not self._settings.twilio_auth_token:
                raise TwilioException("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured")
            self._client = Client(
                self._settings.twilio_account_sid,
                self._settings.twilio_auth_token,
            )
        return self._client

    @property
    def from_number(self) -> str:
        return (
            self._settings.twilio_sms_number.strip()
            or self._settings.twilio_phone_number.strip()
        )

    def send_sms(
        self,
        phone_number: str,
        message: str,
        *,
        customer_id: str = "",
    ) -> SmsDeliveryResult:
        """
        Send an SMS via Twilio, log delivery status, and return metadata.

        Invalid numbers, Twilio failures, and network errors are logged with
        status FAILED and returned as unsuccessful results.
        """
        try:
            phone = validate_phone(phone_number)
        except InvalidPhoneNumberError as exc:
            log_with_context(
                logger,
                logging.WARNING,
                "Invalid phone number for SMS",
                phone=phone_number,
                customer_id=customer_id,
                event="sms_invalid_phone",
            )
            log_id = self._store_log(
                customer_id=customer_id,
                phone=phone_number,
                message=message,
                status="FAILED",
                error=str(exc.detail),
            )
            return SmsDeliveryResult(
                success=False,
                phone=phone_number,
                status="FAILED",
                error=str(exc.detail),
                log_id=log_id,
            )

        if not self.from_number:
            error = "TWILIO_SMS_NUMBER or TWILIO_PHONE_NUMBER must be configured"
            log_id = self._store_log(
                customer_id=customer_id,
                phone=phone,
                message=message,
                status="FAILED",
                error=error,
            )
            return SmsDeliveryResult(
                success=False,
                phone=phone,
                status="FAILED",
                error=error,
                log_id=log_id,
            )

        log_with_context(
            logger,
            logging.INFO,
            "Sending SMS via Twilio",
            phone=phone,
            customer_id=customer_id,
            event="sms_send_started",
        )

        try:
            twilio_message = self.client.messages.create(
                to=phone,
                from_=self.from_number,
                body=message,
            )
        except TwilioException as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Twilio SMS failed: {exc}",
                phone=phone,
                customer_id=customer_id,
                event="sms_twilio_failed",
            )
            log_id = self._store_log(
                customer_id=customer_id,
                phone=phone,
                message=message,
                status="FAILED",
                error=str(exc),
            )
            return SmsDeliveryResult(
                success=False,
                phone=phone,
                status="FAILED",
                error=str(exc),
                log_id=log_id,
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Network error sending SMS: {exc}",
                phone=phone,
                customer_id=customer_id,
                event="sms_network_failed",
            )
            log_id = self._store_log(
                customer_id=customer_id,
                phone=phone,
                message=message,
                status="FAILED",
                error=str(exc),
            )
            return SmsDeliveryResult(
                success=False,
                phone=phone,
                status="FAILED",
                error=str(exc),
                log_id=log_id,
            )

        log_with_context(
            logger,
            logging.INFO,
            "SMS sent via Twilio",
            phone=phone,
            customer_id=customer_id,
            twilio_sid=twilio_message.sid,
            twilio_status=twilio_message.status,
            event="sms_sent",
        )

        log_id = self._store_log(
            customer_id=customer_id,
            phone=phone,
            message=message,
            status="SENT",
            twilio_sid=twilio_message.sid,
        )

        return SmsDeliveryResult(
            success=True,
            phone=phone,
            twilio_sid=twilio_message.sid,
            status="SENT",
            log_id=log_id,
        )

    def list_logs(self, *, limit: int = 100) -> list[SmsLogResponse]:
        """Return recent SMS delivery logs."""
        try:
            docs = find_sorted(
                MongoDB.sms_logs(),
                sort_field="created_at",
                sort_direction=-1,
                limit=limit,
            )
            return [self._serialize(doc) for doc in docs]
        except PyMongoError as exc:
            logger.error("Failed to fetch SMS logs: %s", exc)
            return []

    def list_by_customer(self, customer_id: str) -> list[SmsLogResponse]:
        """Return SMS delivery logs for a customer."""
        try:
            docs = find_sorted(
                MongoDB.sms_logs(),
                {"customer_id": customer_id},
                sort_field="created_at",
                sort_direction=-1,
            )
            return [self._serialize(doc) for doc in docs]
        except PyMongoError as exc:
            logger.error("Failed to fetch SMS logs for customer %s: %s", customer_id, exc)
            return []

    def _store_log(
        self,
        *,
        customer_id: str,
        phone: str,
        message: str,
        status: str,
        twilio_sid: str | None = None,
        error: str | None = None,
    ) -> str | None:
        doc: dict[str, Any] = {
            "customer_id": customer_id,
            "phone": phone,
            "message": message,
            "status": status,
            "created_at": datetime.now(timezone.utc),
        }
        if twilio_sid:
            doc["twilio_sid"] = twilio_sid
        if error:
            doc["error"] = error

        try:
            result = MongoDB.sms_logs().insert_one(doc)
            return str(result.inserted_id)
        except PyMongoError as exc:
            logger.error("Failed to store SMS log: %s", exc)
            return None

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> SmsLogResponse:
        return SmsLogResponse(
            id=str(doc["_id"]),
            customer_id=doc.get("customer_id", ""),
            phone=doc["phone"],
            message=doc["message"],
            status=doc["status"],
            twilio_sid=doc.get("twilio_sid"),
            error=doc.get("error"),
            created_at=doc["created_at"],
        )

    @staticmethod
    def build_payment_link_message(
        *,
        bank_name: str,
        payment_link: str,
    ) -> str:
        """Format the standard payment-link SMS body."""
        return (
            f"{bank_name}\n\n"
            f"Your payment link:\n\n"
            f"{payment_link}\n\n"
            f"If you have already made the payment, please ignore this message."
        )
