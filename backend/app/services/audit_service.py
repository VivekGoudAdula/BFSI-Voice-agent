"""Central audit logging service — event-driven compliance (Phase 8).

Developers should not manually log compliance events in business logic;
hooks in session manager, tool executor, CRM, and handoff services call this layer.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, Optional

from app.core.config import Settings
from app.core.logging_config import log_with_context
from app.models.compliance import ComplianceEventType, ConsentStatus
from app.repositories.compliance_repository import ComplianceRepository

if TYPE_CHECKING:
    from app.models.agent import AgentConfig

logger = logging.getLogger(__name__)

_CONSENT_GRANTED_PATTERNS = re.compile(
    r"\b(yes|yeah|yep|sure|ok|okay|fine|proceed|go ahead|continue|agree|permission granted)\b",
    re.IGNORECASE,
)
_CONSENT_DENIED_PATTERNS = re.compile(
    r"\b(no|nope|don't|do not|stop|refuse|not interested|deny|decline)\b",
    re.IGNORECASE,
)


class AuditService:
    """Automatic compliance audit logger."""

    def __init__(
        self,
        repository: ComplianceRepository,
        settings: Settings,
    ) -> None:
        self._repo = repository
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.compliance_enabled

    @property
    def settings(self) -> Settings:
        return self._settings

    def on_call_started(
        self,
        *,
        call_sid: str,
        call_id: str,
        customer_id: str,
        agent_config: Optional["AgentConfig"] = None,
    ) -> None:
        if not self.enabled:
            return

        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.CALL_STARTED,
            event_data={
                "customer_id": customer_id,
                "agent_id": agent_config.id if agent_config else "",
                "agent_name": agent_config.agent_name if agent_config else "",
            },
        )

        if agent_config:
            self._repo.ensure_prompt_version(
                agent_name=agent_config.agent_name,
                version=agent_config.version,
                prompt=agent_config.system_prompt,
            )
            self._repo.record_call_prompt_usage(
                call_sid=call_sid,
                call_id=call_id,
                agent_name=agent_config.agent_name,
                agent_id=agent_config.id or "",
                prompt_version=agent_config.version,
            )
            self._repo.record_event(
                call_sid=call_sid,
                call_id=call_id,
                event_type=ComplianceEventType.PROMPT_VERSION_RECORDED,
                event_data={
                    "agent_name": agent_config.agent_name,
                    "version": agent_config.version,
                },
            )

        log_with_context(
            logger,
            logging.INFO,
            "Compliance: call started",
            call_id=call_id,
            call_sid=call_sid,
            event="compliance_call_started",
        )

    def on_disclosure_played(
        self,
        *,
        call_sid: str,
        call_id: str,
        disclosure_text: str,
    ) -> None:
        if not self.enabled:
            return

        self._repo.store_disclosure(
            call_sid=call_sid,
            call_id=call_id,
            disclosure_text=disclosure_text,
            played=True,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.DISCLOSURE_PLAYED,
            event_data={"disclosure_text": disclosure_text},
        )
        self._repo.append_transcript_message(
            call_sid=call_sid,
            call_id=call_id,
            role="assistant",
            content=disclosure_text,
        )

    def on_consent_captured(
        self,
        *,
        call_sid: str,
        call_id: str,
        status: ConsentStatus,
        raw_response: str = "",
    ) -> None:
        if not self.enabled:
            return

        self._repo.store_consent(
            call_sid=call_sid,
            call_id=call_id,
            status=status,
        )

        event_map = {
            ConsentStatus.CONSENT_GRANTED: ComplianceEventType.CONSENT_GRANTED,
            ConsentStatus.CONSENT_DENIED: ComplianceEventType.CONSENT_DENIED,
            ConsentStatus.NO_RESPONSE: ComplianceEventType.CONSENT_NO_RESPONSE,
        }
        event_type = event_map.get(status, ComplianceEventType.CONSENT_NO_RESPONSE)
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=event_type,
            event_data={"raw_response": raw_response, "status": status.value},
        )

        if raw_response and status in (
            ConsentStatus.CONSENT_DENIED,
            ConsentStatus.NO_RESPONSE,
        ):
            self._repo.append_transcript_message(
                call_sid=call_sid,
                call_id=call_id,
                role="user",
                content=raw_response,
            )

    def parse_consent_response(self, transcript: str) -> ConsentStatus:
        text = transcript.strip()
        if not text:
            return ConsentStatus.NO_RESPONSE
        if _CONSENT_DENIED_PATTERNS.search(text):
            return ConsentStatus.CONSENT_DENIED
        if _CONSENT_GRANTED_PATTERNS.search(text):
            return ConsentStatus.CONSENT_GRANTED
        return ConsentStatus.NO_RESPONSE

    def build_disclosure_text(self) -> str:
        bank = self._settings.bank_name
        if self._settings.compliance_brief_mode:
            return (
                f"Hello, I am an AI assistant calling from {bank}. "
                "This call may be recorded."
            )
        notice = self._settings.compliance_recording_notice.strip()
        disclosure = self._settings.compliance_disclosure_template.format(
            bank_name=bank
        )
        if notice:
            return f"{disclosure} {notice}"
        return disclosure

    def build_consent_prompt(self) -> str:
        if self._settings.compliance_brief_mode:
            return "May I continue? Please say yes or no."
        return self._settings.compliance_consent_prompt

    def on_user_message(
        self,
        *,
        call_sid: str,
        call_id: str,
        content: str,
    ) -> None:
        if not self.enabled:
            return

        self._repo.append_transcript_message(
            call_sid=call_sid,
            call_id=call_id,
            role="user",
            content=content,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.USER_MESSAGE,
            event_data={"content": content[:500]},
        )

    def on_assistant_message(
        self,
        *,
        call_sid: str,
        call_id: str,
        content: str,
    ) -> None:
        if not self.enabled:
            return

        self._repo.append_transcript_message(
            call_sid=call_sid,
            call_id=call_id,
            role="assistant",
            content=content,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.ASSISTANT_MESSAGE,
            event_data={"content": content[:500]},
        )

    def on_tool_executed(
        self,
        *,
        call_sid: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        execution_time_ms: float,
    ) -> None:
        if not self.enabled:
            return

        self._repo.store_tool_audit(
            call_sid=call_sid,
            call_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            execution_time_ms=execution_time_ms,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.TOOL_EXECUTED,
            event_data={
                "tool_name": tool_name,
                "arguments": arguments,
                "execution_time_ms": execution_time_ms,
            },
        )

    def on_escalation_created(
        self,
        *,
        call_sid: str,
        call_id: str,
        category: str,
        reason: str,
    ) -> None:
        if not self.enabled:
            return

        self._repo.store_escalation_audit(
            call_sid=call_sid,
            call_id=call_id,
            category=category,
            reason=reason,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.ESCALATION_CREATED,
            event_data={"category": category, "reason": reason},
        )

    def on_callback_scheduled(
        self,
        *,
        call_sid: str,
        call_id: str,
        callback_id: str,
        date: str,
        time: str,
    ) -> None:
        if not self.enabled:
            return

        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.CALLBACK_SCHEDULED,
            event_data={
                "callback_id": callback_id,
                "date": date,
                "time": time,
            },
        )

    def on_crm_updated(
        self,
        *,
        call_sid: str,
        call_id: str,
        action: str,
        previous_value: str = "",
        new_value: str = "",
    ) -> None:
        if not self.enabled:
            return

        self._repo.store_crm_audit(
            call_sid=call_sid,
            call_id=call_id,
            action=action,
            previous_value=previous_value,
            new_value=new_value,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.CRM_UPDATED,
            event_data={
                "action": action,
                "previous_value": previous_value,
                "new_value": new_value,
            },
        )

    def on_call_ended(
        self,
        *,
        call_sid: str,
        call_id: str,
        duration_seconds: Optional[float] = None,
        outcome: str = "",
    ) -> None:
        if not self.enabled:
            return

        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.CALL_ENDED,
            event_data={
                "duration_seconds": duration_seconds,
                "outcome": outcome,
            },
        )

    def on_recording_stored(
        self,
        *,
        call_sid: str,
        call_id: str,
        recording_url: str,
        duration: Optional[float] = None,
        storage_provider: str = "local",
    ) -> None:
        if not self.enabled:
            return

        self._repo.store_recording_metadata(
            call_sid=call_sid,
            call_id=call_id,
            recording_url=recording_url,
            duration=duration,
            storage_provider=storage_provider,
        )
        self._repo.record_event(
            call_sid=call_sid,
            call_id=call_id,
            event_type=ComplianceEventType.RECORDING_STORED,
            event_data={"recording_url": recording_url, "duration": duration},
        )
