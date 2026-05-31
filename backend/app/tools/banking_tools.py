"""BFSI banking tools for the voice agent."""

import logging
from typing import Any

from app.services.banking_service import BankingService
from app.services.callback_service import CallbackService
from app.services.customer_service import CustomerService
from app.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class GetLoanDetailsTool(Tool):
    """Fetch customer loan information from core banking."""

    name = "get_loan_details"
    description = (
        "Fetch the customer's loan information including loan type, outstanding amount, "
        "EMI amount, and next due date. Use when customer asks about their loan details."
    )

    def __init__(self, banking_service: BankingService) -> None:
        self._banking = banking_service

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The customer ID",
                },
            },
            "required": ["customer_id"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        customer_id = arguments.get("customer_id") or context.customer_id
        if not context.identity_verified:
            return ToolResult(
                success=False,
                data={},
                error="Identity must be verified before accessing loan details.",
            )
        try:
            data = self._banking.get_loan_details(customer_id)
            return ToolResult(success=True, data=data)
        except Exception as exc:
            return ToolResult(success=False, data={}, error=str(exc))


class CheckEmiDueTool(Tool):
    """Retrieve EMI due amount, date, and status."""

    name = "check_emi_due"
    description = (
        "Check the customer's pending EMI amount, due date, and payment status. "
        "Use when customer asks how much EMI is pending, due date, or payment status."
    )

    def __init__(self, banking_service: BankingService) -> None:
        self._banking = banking_service

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The customer ID",
                },
            },
            "required": ["customer_id"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        customer_id = arguments.get("customer_id") or context.customer_id
        if not context.identity_verified:
            return ToolResult(
                success=False,
                data={},
                error="Identity must be verified before checking EMI details.",
            )
        try:
            data = self._banking.check_emi_due(customer_id)
            return ToolResult(success=True, data=data)
        except Exception as exc:
            return ToolResult(success=False, data={}, error=str(exc))


class ScheduleCallbackTool(Tool):
    """Schedule a future callback for the customer."""

    name = "schedule_callback"
    description = (
        "Schedule a callback at a requested date and time. "
        "Use when customer asks to be called back later, e.g. 'call me tomorrow morning'."
    )

    def __init__(self, callback_service: CallbackService) -> None:
        self._callbacks = callback_service

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The customer ID",
                },
                "date": {
                    "type": "string",
                    "description": "Callback date, e.g. '2026-06-01' or 'tomorrow'",
                },
                "time": {
                    "type": "string",
                    "description": "Callback time, e.g. '10:00 AM' or 'morning'",
                },
            },
            "required": ["customer_id", "date", "time"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        customer_id = arguments.get("customer_id") or context.customer_id
        date = arguments.get("date", "")
        time = arguments.get("time", "")
        if not date or not time:
            return ToolResult(success=False, data={}, error="Date and time are required.")
        try:
            data = self._callbacks.schedule(
                customer_id=customer_id,
                date=date,
                time=time,
                call_id=context.call_id,
            )
            return ToolResult(success=True, data=data)
        except Exception as exc:
            return ToolResult(success=False, data={}, error=str(exc))


class SendPaymentLinkTool(Tool):
    """Send payment link via SMS (mock in Phase 4)."""

    name = "send_payment_link"
    description = (
        "Send an EMI payment link to the customer's registered mobile number via SMS. "
        "Use when customer asks for a payment link or wants to pay online."
    )

    def __init__(
        self,
        banking_service: BankingService,
        customer_service: CustomerService,
    ) -> None:
        self._banking = banking_service
        self._customers = customer_service

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The customer ID",
                },
            },
            "required": ["customer_id"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        customer_id = arguments.get("customer_id") or context.customer_id
        if not context.identity_verified:
            return ToolResult(
                success=False,
                data={},
                error="Identity must be verified before sending payment link.",
            )
        try:
            payment = self._banking.get_payment_link(customer_id)
            customer = self._customers.get_customer_by_id(customer_id)
            phone = customer["phone"] if customer else "registered number"

            # Phase 4: mock SMS send. Future: Twilio SMS/WhatsApp API.
            logger.info(
                "Mock SMS sent | phone=%s link=%s",
                phone,
                payment["payment_link"],
            )
            return ToolResult(
                success=True,
                data={
                    "sent": True,
                    "channel": "sms",
                    "phone": phone,
                    "payment_link": payment["payment_link"],
                    "emi_amount": payment["emi_amount"],
                },
            )
        except Exception as exc:
            return ToolResult(success=False, data={}, error=str(exc))


class TransferToHumanTool(Tool):
    """Transfer the call to a human banking representative."""

    name = "transfer_to_human"
    description = (
        "Transfer the customer to a human banking representative. "
        "Use when customer requests a human agent, has a complaint, disputes account info, "
        "needs legal clarification, or when escalation is required."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "call_sid": {
                    "type": "string",
                    "description": "The Twilio call SID",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for transfer, e.g. customer_requested_human",
                },
            },
            "required": ["call_sid", "reason"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        call_sid = arguments.get("call_sid") or context.call_sid
        reason = arguments.get("reason", "customer_requested_human")

        # Phase 4: mock transfer. Future: Twilio live transfer via <Dial>.
        logger.info(
            "Mock call transfer initiated | call_sid=%s reason=%s",
            call_sid,
            reason,
        )
        return ToolResult(
            success=True,
            data={
                "transferred": True,
                "call_sid": call_sid,
                "reason": reason,
                "message": "Call queued for human agent transfer",
            },
        )
