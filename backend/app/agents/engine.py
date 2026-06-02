"""Core agent engine — orchestrates prompts, state, escalation, and validation."""

import logging
import re
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.escalation_service import EscalationService
from app.agents.objection_handler import ObjectionHandler
from app.agents.states import ConversationState, infer_next_state
from app.agents.validator import ResponseValidator
from app.models.agent import (
    AgentConfig,
    AgentTurnContext,
    EscalationResult,
    ValidationResult,
)
from app.models.handoff import EscalationCategory

logger = logging.getLogger(__name__)

MAX_REGENERATION_ATTEMPTS = 2

TOOL_GUIDANCE = """
## Tool Usage (CRITICAL)
You have access to banking tools. You MUST use tools for any customer request involving:
- Loan details → get_loan_details
- EMI amount, due date, or payment status → check_emi_due
- Payment link via SMS → send_payment_link (ONLY when customer explicitly asks to receive the link, or says yes after you offer to send it)
- Payment link goes to the mobile number already on file — NEVER ask the customer to read out their number.
- Callback scheduling → schedule_callback
- Human agent / complaint / escalation → transfer_to_human

NEVER invent or guess loan amounts, EMI values, due dates, or account details.
ALWAYS call the appropriate tool first, then respond using ONLY the tool result data.
Keep responses to max 15 words, exactly 1 sentence, and end with a single follow-up question when you need input.

## Customer data (outbound calls)
All account data is already linked to this call in the system (customer_id).
NEVER ask for date of birth, mobile number, OTP, PAN, or last-four digits.
Identity = confirm you are speaking with the right person by name only, then discuss EMI.
"""

STATE_GUIDANCE: dict[ConversationState, str] = {
    ConversationState.GREETING: (
        "State: GREETING. Introduce yourself as ABC Bank's EMI Reminder Assistant. "
        "State the purpose of the call and begin identity verification."
    ),
    ConversationState.IDENTITY_VERIFICATION: (
        "State: IDENTITY_VERIFICATION. Ask only: are you speaking with [customer name]? "
        "Do NOT ask for DOB, mobile number, OTP, or PAN — data is already in the system. "
        "Once they confirm their name, call check_emi_due and share the EMI reminder."
    ),
    ConversationState.EMI_DISCUSSION: (
        "State: EMI_DISCUSSION. Share EMI due date and amount ONLY from provided context. "
        "Offer payment options. Ask if they need any assistance with payment."
    ),
    ConversationState.OBJECTION_HANDLING: (
        "State: OBJECTION_HANDLING. Address the customer's concern calmly using approved responses. "
        "Do not argue or pressure."
    ),
    ConversationState.CALLBACK_SCHEDULING: (
        "State: CALLBACK_SCHEDULING. Ask for a convenient time for a callback. "
        "Confirm the time and thank them."
    ),
    ConversationState.ESCALATION: (
        "State: ESCALATION. Inform the customer you are connecting them with a banking representative. "
        "Be brief and professional."
    ),
    ConversationState.CALL_COMPLETION: (
        "State: CALL_COMPLETION. Thank the customer politely and end the call. "
        "Keep it brief."
    ),
}


class AgentEngine:
    """
    Configurable agent engine for BFSI voice conversations.

    Supports multiple agent types loaded from MongoDB without hardcoded logic.
    """

    def __init__(self, escalation_service: "EscalationService | None" = None) -> None:
        if escalation_service is None:
            from app.services.escalation_service import EscalationService

            escalation_service = EscalationService()
        self._escalation = escalation_service
        self._objections = ObjectionHandler()
        self._validator = ResponseValidator()

    def build_greeting(
        self,
        agent_config: AgentConfig,
        customer_name: str,
        agent_context: dict[str, Any] | None = None,
    ) -> str:
        """Build the opening greeting from the agent template."""
        template = agent_config.greeting_template
        if not template:
            template = (
                "Hello {customer_name}. This is ABC Bank calling. "
                "Am I speaking with {customer_name}?"
            )

        ctx = agent_context or {}
        return template.format(
            customer_name=customer_name,
            emi_amount=ctx.get("emi_amount", ""),
            due_date=ctx.get("due_date", ""),
        )

    def build_system_prompt(
        self,
        agent_config: AgentConfig,
        turn_context: AgentTurnContext,
    ) -> str:
        """Assemble the full system prompt with rules, state, and call context."""
        parts: list[str] = [agent_config.system_prompt]

        if agent_config.language_code and agent_config.language_code != "en":
            parts.append(
                f"\n## Active Language\n"
                f"Respond in {agent_config.language} ({agent_config.language_code}). "
                f"Maintain the same language unless the customer requests a switch."
            )

        if agent_config.rules:
            parts.append("\n## Agent Rules")
            for rule in agent_config.rules:
                parts.append(f"- {rule}")

        parts.append(f"\n## {STATE_GUIDANCE.get(turn_context.current_state, '')}")

        parts.append("\n## Call Context")
        parts.append(f"- Customer name: {turn_context.customer_name}")
        parts.append(f"- Identity verified: {turn_context.identity_verified}")
        parts.append(f"- Current state: {turn_context.current_state.value}")

        ctx = turn_context.agent_context
        if ctx.get("emi_amount"):
            parts.append(f"- EMI amount: {ctx['emi_amount']}")
        if ctx.get("due_date"):
            parts.append(f"- Due date: {ctx['due_date']}")
        if ctx.get("loan_account"):
            parts.append(f"- Loan account: {ctx['loan_account']}")
        if ctx.get("payment_status"):
            parts.append(f"- Payment status: {ctx['payment_status']}")

        if ctx.get("emi_amount") or ctx.get("due_date"):
            parts.append(
                "- EMI details are preloaded from the bank system for this customer. "
                "Use check_emi_due if you need a fresh lookup; do NOT ask the customer for account info."
            )
        else:
            parts.append(
                "- NOTE: EMI amount and due date are NOT in context yet. "
                "Call check_emi_due after name confirmation; do NOT guess values."
            )
        parts.append(
            "- NEVER ask the customer for date of birth, mobile number, OTP, or PAN on this call."
        )

        if turn_context.objections_raised:
            parts.append(
                f"- Objections raised this call: {', '.join(turn_context.objections_raised)}"
            )

        parts.append(TOOL_GUIDANCE)

        parts.append(
            "\n## Realtime Response Constraints (MANDATORY)\n"
            "- Respond with <= 15 words total.\n"
            "- Use exactly 1 sentence only.\n"
            "- If the customer needs to decide or answer, ask exactly 1 question to move the call forward.\n"
            "- Speak like a human banking executive: calm, direct, and professional.\n"
        )

        return "\n".join(parts)

    def check_escalation(
        self,
        user_message: str,
        agent_config: AgentConfig,
        turn_context: AgentTurnContext | None = None,
    ) -> EscalationResult:
        """Evaluate whether the conversation should be escalated."""
        ctx = turn_context or AgentTurnContext(
            customer_name="",
            customer_id="",
            call_id="",
            call_sid="",
        )
        analysis = self._escalation.analyze(
            user_message,
            agent_config,
            current_state=ctx.current_state,
            sentiment_history=ctx.sentiment_history,
        )
        if not analysis.should_escalate:
            return EscalationResult(escalate=False)

        legacy_reason = self._escalation.map_category_to_legacy_reason(
            analysis.category or EscalationCategory.CUSTOMER_REQUESTED_HUMAN
        )
        return EscalationResult(escalate=True, reason=legacy_reason)

    def detect_objection(
        self,
        user_message: str,
        agent_config: AgentConfig,
    ) -> tuple[str, str] | None:
        """Detect a customer objection and return scenario + approved response."""
        return self._objections.detect(user_message, agent_config)

    def validate_response(
        self,
        response: str,
        agent_config: AgentConfig,
        turn_context: AgentTurnContext,
        *,
        tools_used: list[str] | None = None,
    ) -> ValidationResult:
        """Validate an AI response before it is spoken."""
        banking_tools = {"check_emi_due", "get_loan_details"}
        has_tool_data = bool(tools_used and banking_tools.intersection(tools_used))
        has_context = has_tool_data or bool(
            turn_context.agent_context.get("emi_amount")
            or turn_context.agent_context.get("due_date")
        )
        return self._validator.validate(
            response,
            agent_config,
            has_account_context=has_context and turn_context.identity_verified,
        )

    def get_regeneration_hint(self, violations: list[str]) -> str:
        """Build hint for response regeneration after validation failure."""
        return self._validator.build_regeneration_hint(violations)

    def get_fallback_response(self, agent_config: AgentConfig) -> str:
        """Safe fallback when generation fails validation repeatedly."""
        return agent_config.unavailable_info_message

    def get_api_failure_response(
        self,
        *,
        customer_name: str = "",
        identity_just_confirmed: bool = False,
    ) -> str:
        """Spoken fallback when the LLM API is temporarily unavailable."""
        name = customer_name.strip() or "there"
        if identity_just_confirmed:
            return (
                f"Thank you for confirming, {name}. "
                "I'm experiencing a brief technical delay. "
                "Let me pull up your EMI details — one moment please."
            )
        return (
            "I apologize for the brief delay on the line. "
            "Could you please repeat what you just said?"
        )

    @staticmethod
    def build_emi_summary_response(
        customer_name: str,
        emi_data: dict[str, Any],
        *,
        language: str = "en",
    ) -> str:
        """Scripted EMI summary when LLM is unavailable after identity confirmation."""
        name = customer_name.strip() or "there"
        amount = emi_data.get("emi_amount", "")
        due_date = emi_data.get("due_date", "")
        status = str(emi_data.get("status", "pending")).lower()
        amount_text = f"Rs. {amount:,}" if isinstance(amount, int) else str(amount)
        if language == "hi":
            return (
                f"धन्यवाद {name} जी, पुष्टि के लिए। "
                f"आपकी EMI {amount_text} की देय तिथि {due_date} थी और स्थिति {status} है। "
                "क्या आप ऑनलाइन भुगतान करेंगे, या मैं आपके पंजीकृत मोबाइल पर पेमेंट लिंक भेज दूँ?"
            )
        return (
            f"Thank you for confirming, {name}. "
            f"Your EMI of {amount_text} was due on {due_date} and the status is {status}. "
            "Would you like to pay online, or shall I send a payment link to your registered mobile number?"
        )

    def get_escalation_response(self, agent_config: AgentConfig) -> str:
        """Approved escalation message."""
        return agent_config.escalation_message

    def update_turn_context(
        self,
        turn_context: AgentTurnContext,
        user_message: str,
        *,
        escalation: EscalationResult | None = None,
    ) -> AgentTurnContext:
        """Update conversation state and flags based on the user's message."""
        text = user_message.lower().strip()

        if escalation and escalation.escalate:
            turn_context.current_state = ConversationState.ESCALATION
            return turn_context

        if self._is_identity_confirmed(text, turn_context.customer_name):
            turn_context.identity_verified = True

        if self._is_call_ending(text):
            turn_context.current_state = ConversationState.CALL_COMPLETION
            return turn_context

        callback_requested = bool(re.search(
            r"\b(callback|call back|call me|schedule|later|tomorrow|evening|morning)\b",
            text,
            re.IGNORECASE,
        ))

        objection_detected = False
        if re.search(r"\b(busy|already paid|no money|stop calling|don't have)\b", text, re.IGNORECASE):
            objection_detected = True

        turn_context.current_state = infer_next_state(
            turn_context.current_state,
            identity_verified=turn_context.identity_verified,
            objection_detected=objection_detected,
            callback_requested=callback_requested,
            escalated=False,
            call_ending=False,
        )

        return turn_context

    def process_user_turn(
        self,
        agent_config: AgentConfig,
        turn_context: AgentTurnContext,
        user_message: str,
    ) -> dict[str, Any]:
        """
        Process a user turn and return guidance for response generation.

        Returns dict with:
            - escalation: EscalationResult
            - use_objection_response: bool
            - objection_response: str
            - objection_scenario: str
            - updated_context: AgentTurnContext
        """
        analysis = self._escalation.analyze(
            user_message,
            agent_config,
            current_state=turn_context.current_state,
            sentiment_history=turn_context.sentiment_history,
        )
        turn_context.sentiment_history.append(analysis.sentiment.value)
        escalation = EscalationResult(
            escalate=analysis.should_escalate,
            reason=analysis.reason if analysis.should_escalate else "",
        )

        if analysis.should_escalate and analysis.category:
            turn_context.current_state = ConversationState.ESCALATION
            return {
                "escalation": escalation,
                "use_objection_response": False,
                "objection_response": "",
                "objection_scenario": "escalation",
                "updated_context": turn_context,
                "forced_response": None,
                "trigger_transfer": True,
                "transfer_reason": analysis.reason,
                "escalation_category": analysis.category.value,
                "transfer_message": self._escalation.get_transfer_message(analysis.category),
            }

        objection = self.detect_objection(user_message, agent_config)
        if objection:
            scenario, response = objection
            if scenario not in turn_context.objections_raised:
                turn_context.objections_raised.append(scenario)
            turn_context.current_state = ConversationState.OBJECTION_HANDLING
            return {
                "escalation": escalation,
                "use_objection_response": True,
                "objection_response": response,
                "objection_scenario": scenario,
                "updated_context": turn_context,
                "forced_response": None,
            }

        turn_context = self.update_turn_context(turn_context, user_message)
        return {
            "escalation": escalation,
            "use_objection_response": False,
            "objection_response": "",
            "objection_scenario": "",
            "updated_context": turn_context,
            "forced_response": None,
        }

    @staticmethod
    def _is_identity_confirmed(text: str, customer_name: str = "") -> bool:
        lower = text.lower()
        patterns = [
            r"\b(yes|yeah|yep|haan|ji|correct|speaking|this is|that's me|that is me)\b",
            r"\b(i am|i'm|main hoon|mein hoon|main hu|mein hu)\b",
            r"\b(mera naam|my name is|naam hai)\b",
            r"नाम\s+.+\s+है",
            r"मैं\s+.+?\s+हू[ंँ]",
            r"ह[ााँ]ं[,،]?\s*मैं",
            r"जी[,،]?\s*मैं",
        ]
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            return True
        if re.search(r"ह[ााँ]ं", text) and AgentEngine._customer_name_in_utterance(
            text, customer_name
        ):
            return True
        if customer_name:
            first = customer_name.strip().split()[0].lower()
            if len(first) >= 3 and first in lower:
                return True
            if AgentEngine._customer_name_in_utterance(text, customer_name):
                return True
        return False

    @staticmethod
    def _customer_name_in_utterance(text: str, customer_name: str) -> bool:
        if not customer_name:
            return False
        first = customer_name.strip().split()[0].lower()
        if len(first) >= 3 and first in text.lower():
            return True
        devanagari_names: dict[str, tuple[str, ...]] = {
            "vivek": ("विवेक",),
            "rahul": ("राहुल",),
            "priya": ("प्रिया",),
            "amit": ("अमित",),
            "anita": ("अनिता",),
        }
        for variant in devanagari_names.get(first, ()):
            if variant in text:
                return True
        return False

    @staticmethod
    def _is_call_ending(text: str) -> bool:
        patterns = [
            r"\b(goodbye|bye|thank you.*bye|that's all|nothing else|no thanks)\b",
            r"\b(hang up|end call|stop now)\b",
        ]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)
