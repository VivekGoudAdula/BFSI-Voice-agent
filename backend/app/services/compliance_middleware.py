"""Compliance middleware — disclosure, consent, and pre-call compliance flow."""

import logging
from typing import TYPE_CHECKING, Optional

from app.core.logging_config import log_with_context
from app.models.compliance import ConsentStatus
from app.services.audit_service import AuditService
from app.services.language_manager import INITIAL_HELLO

if TYPE_CHECKING:
    from app.services.call_session_manager import ActiveCallSession
    from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class ComplianceMiddleware:
    """
    Sits between Voice Agent and Conversation Processing.

    Ensures AI disclosure and consent capture before the main conversation.
    """

    def __init__(self, audit_service: AuditService) -> None:
        self._audit = audit_service

    @property
    def enabled(self) -> bool:
        return self._audit.enabled

    @property
    def use_language_first_flow(self) -> bool:
        return bool(self._audit.settings.compliance_language_first_flow)

    async def run_initial_hello(
        self,
        session: "ActiveCallSession",
        conversation_service: "ConversationService",
    ) -> None:
        """Say a short Hello and wait for the customer to speak (language detection)."""
        session.awaiting_initial_language = True
        session.awaiting_consent = False
        session.messages[-1] = {"role": "assistant", "content": INITIAL_HELLO}
        await conversation_service._speak(session, INITIAL_HELLO)
        log_with_context(
            logger,
            logging.INFO,
            "Initial hello played — awaiting customer language",
            call_id=session.call_id,
            event="initial_hello_played",
        )

    async def run_pre_call_compliance(
        self,
        session: "ActiveCallSession",
        conversation_service: "ConversationService",
    ) -> None:
        """Play disclosure + consent prompt at call start (legacy flow)."""
        if not self.enabled:
            return

        disclosure = self._audit.build_disclosure_text()
        consent_prompt = self._audit.build_consent_prompt()

        session.awaiting_consent = True
        session.consent_status = ConsentStatus.PENDING.value
        session.compliance_disclosure_text = disclosure

        combined = f"{disclosure} {consent_prompt}"
        session.messages[-1] = {"role": "assistant", "content": combined}

        await conversation_service._speak(session, combined)

        self._audit.on_disclosure_played(
            call_sid=session.call_sid,
            call_id=session.call_id,
            disclosure_text=disclosure,
        )
        self._audit.on_assistant_message(
            call_sid=session.call_sid,
            call_id=session.call_id,
            content=consent_prompt,
        )

        log_with_context(
            logger,
            logging.INFO,
            "Compliance disclosure and consent prompt played",
            call_id=session.call_id,
            event="compliance_disclosure_played",
        )

    def record_opening_consent(
        self,
        session: "ActiveCallSession",
        *,
        language: str,
        customer_response: str,
    ) -> None:
        """Record implied consent after customer responds to Hello and hears the intro."""
        session.awaiting_consent = False
        session.consent_status = ConsentStatus.CONSENT_GRANTED.value
        self._audit.on_consent_captured(
            call_sid=session.call_sid,
            call_id=session.call_id,
            status=ConsentStatus.CONSENT_GRANTED,
            raw_response=customer_response,
        )
        log_with_context(
            logger,
            logging.INFO,
            "Opening consent recorded (language-first flow)",
            call_id=session.call_id,
            language=language,
            event="compliance_consent_granted",
        )

    async def handle_consent_response(
        self,
        session: "ActiveCallSession",
        transcript: str,
        conversation_service: "ConversationService",
    ) -> bool:
        """
        Process customer consent response.

        Returns True if conversation should continue, False if call should end.
        """
        if not session.awaiting_consent:
            return True

        status = self._audit.parse_consent_response(transcript)
        session.awaiting_consent = False
        session.consent_status = status.value

        self._audit.on_consent_captured(
            call_sid=session.call_sid,
            call_id=session.call_id,
            status=status,
            raw_response=transcript,
        )

        if status == ConsentStatus.CONSENT_DENIED:
            farewell = (
                "I understand. Thank you for your time. "
                "If you change your mind, please contact us at your convenience. Goodbye."
            )
            session.consent_denied = True
            self._audit.on_assistant_message(
                call_sid=session.call_sid,
                call_id=session.call_id,
                content=farewell,
            )
            await conversation_service._speak(session, farewell)
            session.handoff_initiated = True
            log_with_context(
                logger,
                logging.INFO,
                "Customer denied consent — ending call",
                call_id=session.call_id,
                event="compliance_consent_denied",
            )
            return False

        if status == ConsentStatus.NO_RESPONSE:
            reprompt = (
                "I did not catch your response. "
                "Do I have your permission to continue this conversation? Please say yes or no."
            )
            session.awaiting_consent = True
            self._audit.on_assistant_message(
                call_sid=session.call_sid,
                call_id=session.call_id,
                content=reprompt,
            )
            await conversation_service._speak(session, reprompt)
            return False

        # CONSENT_GRANTED — play the agent greeting
        session.skip_next_agent_turn = True
        if session.pending_greeting:
            session.messages[-1] = {"role": "assistant", "content": session.pending_greeting}
            await conversation_service._speak(session, session.pending_greeting)
            self._audit.on_assistant_message(
                call_sid=session.call_sid,
                call_id=session.call_id,
                content=session.pending_greeting,
            )

        log_with_context(
            logger,
            logging.INFO,
            "Customer granted consent",
            call_id=session.call_id,
            event="compliance_consent_granted",
        )
        return True

    def on_call_started(self, session: "ActiveCallSession") -> None:
        self._audit.on_call_started(
            call_sid=session.call_sid,
            call_id=session.call_id,
            customer_id=session.customer_id,
            agent_config=session.agent_config,
        )
