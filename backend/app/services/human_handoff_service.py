"""Human handoff orchestration — transfer queue, context packaging, mock transfer."""

import logging
from typing import Any, Optional

from app.core.logging_config import log_with_context
from app.models.handoff import (
    EscalationCategory,
    HandoffContextPackage,
    HandoffLogStatus,
    TransferPriority,
    TransferQueueStatus,
)
from app.repositories.handoff_repository import HandoffRepository
from app.services.sentiment_service import SentimentService
from app.services.twilio_service import TwilioService

logger = logging.getLogger(__name__)

_CATEGORY_PRIORITY: dict[EscalationCategory, TransferPriority] = {
    EscalationCategory.LEGAL_QUERY: TransferPriority.HIGH,
    EscalationCategory.HIGH_RISK_QUERY: TransferPriority.HIGH,
    EscalationCategory.ACCOUNT_DISPUTE: TransferPriority.HIGH,
    EscalationCategory.COMPLAINT: TransferPriority.MEDIUM,
    EscalationCategory.NEGATIVE_SENTIMENT: TransferPriority.MEDIUM,
    EscalationCategory.CUSTOMER_REQUESTED_HUMAN: TransferPriority.LOW,
}


class HumanHandoffService:
    """
    Escalation Engine → Human Handoff Service → Transfer Queue → Human Agent.

    Mock transfer is used in Phase 7; architecture supports live Twilio/SIP later.
    """

    def __init__(
        self,
        repository: HandoffRepository,
        twilio_service: TwilioService,
        sentiment_service: Optional[SentimentService] = None,
        audit_service: Any = None,
    ) -> None:
        self._repo = repository
        self._twilio = twilio_service
        self._sentiment = sentiment_service or SentimentService()
        self._audit = audit_service

    def priority_for_category(self, category: str) -> TransferPriority:
        try:
            cat = EscalationCategory(category)
        except ValueError:
            return TransferPriority.MEDIUM
        return _CATEGORY_PRIORITY.get(cat, TransferPriority.MEDIUM)

    def build_context_package(
        self,
        *,
        call_id: str,
        call_sid: str,
        customer_id: str,
        customer_name: str,
        agent_id: str,
        call_reason: str,
        summary: str,
        escalation_category: str,
        escalation_reason: str,
        messages: list[dict[str, str]],
        tool_usage: list[str],
        sentiment_history: list[str],
    ) -> HandoffContextPackage:
        levels = []
        for label in sentiment_history:
            try:
                from app.models.handoff import SentimentLevel

                levels.append(SentimentLevel(label))
            except ValueError:
                continue
        aggregate = self._sentiment.aggregate_sentiment(levels).value

        return HandoffContextPackage(
            customer_name=customer_name,
            customer_id=customer_id,
            call_id=call_id,
            call_sid=call_sid,
            call_reason=call_reason,
            summary=summary,
            sentiment=aggregate,
            transcript_id=call_id,
            tool_usage=list(tool_usage),
            agent_id=agent_id,
            escalation_category=escalation_category,
            escalation_reason=escalation_reason,
            messages_snapshot=messages[-20:],
        )

    def build_summary_from_messages(
        self,
        messages: list[dict[str, str]],
        escalation_reason: str,
    ) -> str:
        """Generate a concise conversation summary for human agents."""
        user_lines = [
            m["content"] for m in messages if m.get("role") == "user"
        ][-5:]
        if not user_lines:
            return escalation_reason

        recent = " ".join(user_lines[-3:])
        if len(recent) > 200:
            recent = recent[:197] + "..."
        return f"{escalation_reason}. Recent customer statements: {recent}"

    async def transfer_to_human(
        self,
        *,
        call_sid: str,
        customer_id: str,
        call_id: str,
        reason: str,
        category: str,
        context: Optional[HandoffContextPackage] = None,
        human_destination: str = "",
    ) -> dict[str, Any]:
        """
        Full handoff pipeline: record escalation → queue → log → mock transfer.

        Returns tool-compatible output with transferred=true.
        """
        escalation_id = self._repo.create_escalation(
            call_sid=call_sid,
            customer_id=customer_id,
            escalation_type=category,
            reason=reason,
            call_id=call_id,
        )

        if self._audit:
            self._audit.on_escalation_created(
                call_sid=call_sid,
                call_id=call_id,
                category=category,
                reason=reason,
            )

        context_dict = context.model_dump() if context else {}
        transcript_id = call_id
        if context:
            transcript_id = context.transcript_id or call_id
            context_store_id = self._repo.store_handoff_context(
                call_id,
                context_dict,
            )
            context_dict["context_record_id"] = context_store_id

        priority = self.priority_for_category(category)
        queue_id = self._repo.enqueue_transfer(
            customer_id=customer_id,
            call_sid=call_sid,
            category=category,
            priority=priority,
            reason=reason,
            call_id=call_id,
            context=context_dict,
        )

        transfer_result = self._twilio.mock_transfer_call(
            call_sid=call_sid,
            destination=human_destination,
            category=category,
        )

        log_status = (
            HandoffLogStatus.TRANSFERRED
            if transfer_result.get("transferred")
            else HandoffLogStatus.FAILED
        )
        handoff_log_id = self._repo.create_handoff_log(
            call_sid=call_sid,
            customer_id=customer_id,
            status=log_status,
            call_id=call_id,
            escalation_id=escalation_id,
        )

        if transfer_result.get("transferred"):
            self._repo.update_queue_status(queue_id, TransferQueueStatus.TRANSFERRED)

        log_with_context(
            logger,
            logging.INFO,
            "Human handoff completed",
            call_id=call_id,
            call_sid=call_sid,
            category=category,
            priority=priority.value,
            queue_id=queue_id,
            event="human_handoff",
        )

        return {
            "transferred": transfer_result.get("transferred", True),
            "queue_id": queue_id,
            "escalation_id": escalation_id,
            "handoff_log_id": handoff_log_id,
            "call_sid": call_sid,
            "category": category,
            "priority": priority.value,
            "reason": reason,
            "transcript_id": transcript_id,
            "transfer_mode": transfer_result.get("mode", "mock"),
            "message": "Customer queued for human agent transfer",
        }
