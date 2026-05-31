"""BFSI banking tools for the voice agent."""

import logging
from typing import Any

from app.core.config import get_settings
from app.models.handoff import EscalationCategory
from app.services.banking_service import BankingService
from app.services.callback_service import CallbackService
from app.services.customer_service import CustomerService
from app.services.human_handoff_service import HumanHandoffService
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
        "needs legal clarification, fraud concerns, or when escalation is required."
    )

    def __init__(
        self,
        handoff_service: HumanHandoffService,
        agent_config_service: Any = None,
    ) -> None:
        self._handoff = handoff_service
        self._agent_configs = agent_config_service

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
                    "description": "Human-readable reason for transfer",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Escalation category: CUSTOMER_REQUESTED_HUMAN, COMPLAINT, "
                        "LEGAL_QUERY, ACCOUNT_DISPUTE, NEGATIVE_SENTIMENT, HIGH_RISK_QUERY"
                    ),
                },
            },
            "required": ["reason", "category"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        call_sid = arguments.get("call_sid") or context.call_sid
        reason = arguments.get("reason", "Escalation required")
        category = arguments.get("category", EscalationCategory.CUSTOMER_REQUESTED_HUMAN.value)

        if category not in {c.value for c in EscalationCategory}:
            category = EscalationCategory.CUSTOMER_REQUESTED_HUMAN.value

        agent_config = (
            self._agent_configs.get_default_agent() if self._agent_configs else None
        )
        call_reason = (
            context.extra.get("agent_purpose")
            or (agent_config.purpose if agent_config else "Voice Agent Call")
        )

        summary = self._handoff.build_summary_from_messages(
            context.messages,
            reason,
        )
        context_package = self._handoff.build_context_package(
            call_id=context.call_id,
            call_sid=call_sid,
            customer_id=context.customer_id,
            customer_name=context.customer_name,
            agent_id=context.agent_id,
            call_reason=call_reason,
            summary=summary,
            escalation_category=category,
            escalation_reason=reason,
            messages=context.messages,
            tool_usage=list(context.tools_used),
            sentiment_history=list(context.sentiment_history),
        )

        settings = get_settings()
        try:
            result = await self._handoff.transfer_to_human(
                call_sid=call_sid,
                customer_id=context.customer_id,
                call_id=context.call_id,
                reason=reason,
                category=category,
                context=context_package,
                human_destination=settings.human_agent_phone,
            )
            context.handoff_initiated = True
            return ToolResult(success=True, data=result)
        except Exception as exc:
            logger.error("Human handoff failed: %s", exc)
            return ToolResult(success=False, data={"transferred": False}, error=str(exc))


class VerifyCustomerTool(Tool):
    """Verify customer identity for KYC compliance."""

    name = "verify_customer"
    description = (
        "Run KYC identity verification for the customer after verbal identity confirmation. "
        "Use when the customer has confirmed their identity during a KYC call."
    )

    def __init__(self, customer_service: CustomerService) -> None:
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
                error="Identity must be verified before running KYC check.",
            )
        customer = self._customers.get_customer_by_id(customer_id)
        if not customer:
            return ToolResult(success=False, data={}, error="Customer not found.")
        return ToolResult(
            success=True,
            data={
                "verified": True,
                "customer_id": customer_id,
                "customer_name": customer.get("name", ""),
                "kyc_status": "pending_review",
                "message": "KYC verification submitted for backend review.",
            },
        )


class CreateSupportTicketTool(Tool):
    """Create a customer support ticket."""

    name = "create_support_ticket"
    description = (
        "Create a support ticket for the customer's issue. "
        "Use when the issue requires backend follow-up or cannot be resolved on the call."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The customer ID",
                },
                "subject": {
                    "type": "string",
                    "description": "Brief subject line for the ticket",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority: low, medium, or high",
                },
            },
            "required": ["customer_id", "subject", "description"],
        }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        customer_id = arguments.get("customer_id") or context.customer_id
        subject = arguments.get("subject", "Customer support request")
        description = arguments.get("description", "")
        priority = arguments.get("priority", "medium")

        ticket_id = f"TKT-{context.call_id[:8].upper()}"
        logger.info(
            "Support ticket created | ticket=%s customer=%s subject=%s",
            ticket_id,
            customer_id,
            subject,
        )
        return ToolResult(
            success=True,
            data={
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "subject": subject,
                "description": description,
                "priority": priority,
                "status": "open",
                "call_id": context.call_id,
            },
        )

