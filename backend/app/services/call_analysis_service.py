"""Post-call conversation analysis using Groq LLM."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.states import ConversationState
from app.core.config import Settings
from app.core.logging_config import log_with_context
from app.models.crm import (
    CallAnalysisResult,
    CallOutcome,
    FollowUpRequest,
    LeadStatus,
)
from app.services.groq_service import GroqService

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """You are a BFSI call analysis engine. Analyze the completed voice call conversation and return ONLY valid JSON with no markdown.

Return this exact JSON structure:
{
  "summary": "Concise bullet-style summary of the call (2-5 lines)",
  "lead_status": "One of: INTERESTED, NOT_INTERESTED, CALLBACK_REQUESTED, PAYMENT_PROMISED, PAYMENT_COMPLETED, ESCALATED, NO_RESPONSE, WRONG_NUMBER, DISCONNECTED",
  "call_outcome": "One of: SUCCESSFUL, FOLLOW_UP_REQUIRED, PAYMENT_PENDING, PAYMENT_CONFIRMED, TRANSFERRED_TO_AGENT, FAILED",
  "intent": "Primary customer intent in one sentence",
  "follow_up_actions": ["list of follow-up actions needed"],
  "follow_up_date": "YYYY-MM-DD or null if not requested",
  "follow_up_time": "HH:MM in 24h format or null if not requested",
  "confidence": 0.0 to 1.0
}

Classification rules:
- CALLBACK_REQUESTED: customer asked to be called back at a specific time
- PAYMENT_PROMISED: customer said they will pay (today, soon, etc.)
- PAYMENT_COMPLETED: customer confirmed payment was made
- NOT_INTERESTED: customer explicitly declined
- ESCALATED: call was transferred to human agent
- NO_RESPONSE: no meaningful customer engagement
- WRONG_NUMBER: wrong person answered
- DISCONNECTED: call ended abruptly without resolution
- INTERESTED: customer engaged positively without specific action

Outcome rules:
- SUCCESSFUL: call objective achieved (EMI reminder acknowledged, payment confirmed)
- FOLLOW_UP_REQUIRED: callback or follow-up needed
- PAYMENT_PENDING: payment link sent or payment promised
- PAYMENT_CONFIRMED: payment completed
- TRANSFERRED_TO_AGENT: escalated to human
- FAILED: call did not achieve objective"""


class CallAnalysisService:
    """Analyzes completed calls to extract structured outcomes."""

    def __init__(self, settings: Settings, groq_service: GroqService) -> None:
        self._settings = settings
        self._groq = groq_service

    async def analyze_call(
        self,
        *,
        call_id: str,
        call_sid: str,
        customer_name: str,
        transcript: str,
        messages: list[dict[str, str]],
        tools_used: list[str],
        current_state: ConversationState,
        escalation_triggered: bool,
        escalation_reason: str,
        duration_seconds: float | None,
        agent_context: dict[str, Any],
    ) -> CallAnalysisResult:
        """Analyze a completed call and return structured classification."""
        context_block = self._build_context_block(
            customer_name=customer_name,
            transcript=transcript,
            tools_used=tools_used,
            current_state=current_state,
            escalation_triggered=escalation_triggered,
            escalation_reason=escalation_reason,
            duration_seconds=duration_seconds,
            agent_context=agent_context,
        )

        try:
            result = await self._analyze_with_groq(context_block, call_id)
            if result:
                return result
        except Exception as exc:
            log_with_context(
                logger,
                logging.WARNING,
                f"Groq call analysis failed, using rule-based fallback: {exc}",
                call_id=call_id,
                event="call_analysis_fallback",
            )

        return self._rule_based_analysis(
            transcript=transcript,
            tools_used=tools_used,
            current_state=current_state,
            escalation_triggered=escalation_triggered,
            customer_name=customer_name,
        )

    async def _analyze_with_groq(
        self,
        context_block: str,
        call_id: str,
    ) -> CallAnalysisResult | None:
        user_prompt = f"Analyze this completed BFSI voice call:\n\n{context_block}"
        messages = [{"role": "user", "content": user_prompt}]

        response_text, _ = await self._groq.generate_response(
            messages,
            ANALYSIS_SYSTEM_PROMPT,
        )

        parsed = self._parse_json_response(response_text)
        if not parsed:
            return None

        return CallAnalysisResult(
            summary=parsed.get("summary", "Call completed."),
            lead_status=LeadStatus(parsed.get("lead_status", "NO_RESPONSE")),
            call_outcome=CallOutcome(parsed.get("call_outcome", "FAILED")),
            intent=parsed.get("intent", ""),
            follow_up_actions=parsed.get("follow_up_actions", []),
            follow_up=FollowUpRequest(
                follow_up_date=parsed.get("follow_up_date"),
                follow_up_time=parsed.get("follow_up_time"),
            ),
            confidence=float(parsed.get("confidence", 0.8)),
        )

    def _rule_based_analysis(
        self,
        *,
        transcript: str,
        tools_used: list[str],
        current_state: ConversationState,
        escalation_triggered: bool,
        customer_name: str,
    ) -> CallAnalysisResult:
        """Fallback rule-based classification when Groq is unavailable."""
        text_lower = transcript.lower()
        follow_up = FollowUpRequest()
        follow_up_actions: list[str] = []
        summary_lines: list[str] = []

        lead_status = LeadStatus.NO_RESPONSE
        call_outcome = CallOutcome.FAILED

        if escalation_triggered or "transfer_to_human" in tools_used:
            lead_status = LeadStatus.ESCALATED
            call_outcome = CallOutcome.TRANSFERRED_TO_AGENT
            summary_lines.append("Call escalated to human agent.")
        elif any(p in text_lower for p in ("not interested", "don't want", "stop calling")):
            lead_status = LeadStatus.NOT_INTERESTED
            call_outcome = CallOutcome.SUCCESSFUL
            summary_lines.append("Customer indicated they are not interested.")
        elif "schedule_callback" in tools_used or any(
            p in text_lower for p in ("call me tomorrow", "call back", "call me next")
        ):
            lead_status = LeadStatus.CALLBACK_REQUESTED
            call_outcome = CallOutcome.FOLLOW_UP_REQUIRED
            follow_up_actions.append("Schedule callback")
            follow_up = self._extract_follow_up_from_text(text_lower)
            summary_lines.append("Customer requested a callback.")
        elif "send_payment_link" in tools_used or any(
            p in text_lower for p in ("will pay", "pay today", "send payment link", "payment link")
        ):
            lead_status = LeadStatus.PAYMENT_PROMISED
            call_outcome = CallOutcome.PAYMENT_PENDING
            follow_up_actions.append("Follow up on payment")
            summary_lines.append("Customer requested payment link or promised payment.")
        elif any(p in text_lower for p in ("already paid", "payment done", "paid already")):
            lead_status = LeadStatus.PAYMENT_COMPLETED
            call_outcome = CallOutcome.PAYMENT_CONFIRMED
            summary_lines.append("Customer confirmed payment completed.")
        elif any(p in text_lower for p in ("wrong number", "wrong person")):
            lead_status = LeadStatus.WRONG_NUMBER
            call_outcome = CallOutcome.FAILED
            summary_lines.append("Wrong number reported.")
        elif current_state == ConversationState.CALL_COMPLETION:
            lead_status = LeadStatus.INTERESTED
            call_outcome = CallOutcome.SUCCESSFUL
            summary_lines.append(f"Call completed successfully with {customer_name}.")
        elif len(transcript.strip()) < 20:
            lead_status = LeadStatus.DISCONNECTED
            call_outcome = CallOutcome.FAILED
            summary_lines.append("Call disconnected with minimal conversation.")
        else:
            lead_status = LeadStatus.INTERESTED
            call_outcome = CallOutcome.FOLLOW_UP_REQUIRED
            summary_lines.append("Customer engaged in conversation.")

        if "check_emi_due" in tools_used:
            summary_lines.append("EMI due amount discussed.")
        if "get_loan_details" in tools_used:
            summary_lines.append("Loan details retrieved.")

        return CallAnalysisResult(
            summary="\n".join(summary_lines),
            lead_status=lead_status,
            call_outcome=call_outcome,
            intent=f"Customer interaction regarding EMI/loan services",
            follow_up_actions=follow_up_actions,
            follow_up=follow_up,
            confidence=0.6,
        )

    @staticmethod
    def _extract_follow_up_from_text(text_lower: str) -> FollowUpRequest:
        """Extract follow-up date/time from common phrases."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        follow_up_date = None
        follow_up_time = None

        if "tomorrow" in text_lower:
            follow_up_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "next week" in text_lower:
            follow_up_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")

        if "11 am" in text_lower or "11:00" in text_lower:
            follow_up_time = "11:00"
        elif "after 5" in text_lower or "5 pm" in text_lower:
            follow_up_time = "17:00"

        return FollowUpRequest(
            follow_up_date=follow_up_date,
            follow_up_time=follow_up_time,
        )

    @staticmethod
    def _build_context_block(
        *,
        customer_name: str,
        transcript: str,
        tools_used: list[str],
        current_state: ConversationState,
        escalation_triggered: bool,
        escalation_reason: str,
        duration_seconds: float | None,
        agent_context: dict[str, Any],
    ) -> str:
        lines = [
            f"Customer: {customer_name}",
            f"Final State: {current_state.value}",
            f"Escalation: {escalation_triggered} ({escalation_reason})",
            f"Tools Used: {', '.join(tools_used) if tools_used else 'none'}",
            f"Duration: {duration_seconds}s" if duration_seconds else "Duration: unknown",
        ]
        if agent_context:
            lines.append(f"Agent Context: {json.dumps(agent_context)}")
        lines.append(f"\nTranscript:\n{transcript}")
        return "\n".join(lines)

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any] | None:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return None
