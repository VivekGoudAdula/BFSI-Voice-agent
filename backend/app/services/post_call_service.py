"""Post-call processing orchestrator for internal CRM."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.states import ConversationState
from app.core.config import Settings
from app.core.logging_config import log_with_context
from app.database.mongodb import MongoDB
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.call_analysis_service import CallAnalysisService
from app.services.call_session_manager import ActiveCallSession
from app.services.callback_service import CallbackService
from app.services.crm_data_service import CRMDataService
from app.services.customer_service import CustomerService
from app.services.tool_execution_service import ToolExecutionService
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class PostCallService:
    """
    Orchestrates post-call processing:
    analytics → analysis → internal CRM persistence → campaign tracking.
    """

    def __init__(
        self,
        settings: Settings,
        analytics_service: AgentAnalyticsService,
        call_analysis_service: CallAnalysisService,
        crm_data_service: CRMDataService,
        customer_service: CustomerService,
        tool_execution_service: ToolExecutionService,
        callback_service: CallbackService,
        campaign_queue_service: Any = None,
        audit_service: Any = None,
    ) -> None:
        self._settings = settings
        self._analytics = analytics_service
        self._analysis = call_analysis_service
        self._crm_data = crm_data_service
        self._customers = customer_service
        self._tool_logs = tool_execution_service
        self._callbacks = callback_service
        self._campaign_queue = campaign_queue_service
        self._audit = audit_service
        self._processed_calls: set[str] = set()

    def set_campaign_queue_service(self, queue_service: Any) -> None:
        self._campaign_queue = queue_service

    async def process_call_end(self, session: ActiveCallSession) -> None:
        """Run full post-call pipeline when a call session ends."""
        call_id = session.call_id

        if call_id in self._processed_calls or self._crm_data.is_call_processed(call_id):
            log_with_context(
                logger,
                logging.DEBUG,
                "Post-call processing already completed",
                call_id=call_id,
                event="post_call_skipped",
            )
            return

        self._processed_calls.add(call_id)

        self._finalize_analytics(session)

        transcript = self._build_transcript(session.call_id)
        tool_logs = self._tool_logs.get_logs_by_call(session.call_id)
        tools_used = list(session.tools_used) or [log.tool_name for log in tool_logs]

        duration = None
        if session.started_at:
            duration = (datetime.now(timezone.utc) - session.started_at).total_seconds()

        escalation_triggered = session.current_state == ConversationState.ESCALATION

        analysis = await self._analysis.analyze_call(
            call_id=session.call_id,
            call_sid=session.call_sid,
            customer_name=session.customer_name,
            transcript=transcript,
            messages=[m for m in session.messages if m["role"] in ("user", "assistant")],
            tools_used=tools_used,
            current_state=session.current_state,
            escalation_triggered=escalation_triggered,
            escalation_reason=session.escalation_reason,
            duration_seconds=duration,
            agent_context=session.agent_context,
        )

        self._crm_data.store_summary(
            call_id=session.call_id,
            call_sid=session.call_sid,
            customer_id=session.customer_id,
            analysis=analysis,
        )
        self._crm_data.store_lead_status(
            call_id=session.call_id,
            call_sid=session.call_sid,
            customer_id=session.customer_id,
            analysis=analysis,
        )
        self._crm_data.store_call_outcome(
            call_id=session.call_id,
            call_sid=session.call_sid,
            customer_id=session.customer_id,
            analysis=analysis,
        )

        self._create_follow_up_callback(session, analysis)
        await self._update_campaign_tracking(session.call_id, analysis, duration)
        self._store_compliance_on_call_end(session, analysis, duration)

        log_with_context(
            logger,
            logging.INFO,
            "Post-call processing completed",
            call_id=call_id,
            lead_status=analysis.lead_status.value,
            call_outcome=analysis.call_outcome.value,
            event="post_call_completed",
        )

    async def handle_call_status_update(
        self,
        call_id: str,
        status: str,
    ) -> None:
        """Handle terminal call statuses for campaign tracking (no session)."""
        if status not in ("failed", "busy", "no-answer", "canceled"):
            return

        call = MongoDB.calls().find_one({"_id": self._to_object_id(call_id)})
        if not call:
            return

        campaign_id = call.get("campaign_id")
        campaign_customer_id = call.get("campaign_customer_id")
        if not campaign_id or not campaign_customer_id:
            return

        if self._campaign_queue:
            await self._campaign_queue.on_call_failed(
                campaign_id, campaign_customer_id
            )

    async def _update_campaign_tracking(
        self,
        call_id: str,
        analysis: Any,
        duration: Optional[float],
    ) -> None:
        call = MongoDB.calls().find_one({"_id": self._to_object_id(call_id)})
        if not call:
            return

        campaign_id = call.get("campaign_id")
        campaign_customer_id = call.get("campaign_customer_id")
        if not campaign_id or not campaign_customer_id or not self._campaign_queue:
            return

        await self._campaign_queue.on_call_finished(
            campaign_id,
            campaign_customer_id,
            success=True,
            lead_status=analysis.lead_status.value,
            duration_seconds=duration,
        )

    def _store_compliance_on_call_end(
        self,
        session: ActiveCallSession,
        analysis: Any,
        duration: Optional[float],
    ) -> None:
        if not self._audit:
            return

        self._audit.on_call_ended(
            call_sid=session.call_sid,
            call_id=session.call_id,
            duration_seconds=duration,
            outcome=analysis.call_outcome.value if analysis else "",
        )

        call = MongoDB.calls().find_one({"_id": self._to_object_id(session.call_id)})
        if call and call.get("audio_file"):
            recording_url = (
                f"{self._settings.base_url.rstrip('/')}"
                f"/webhooks/twilio/play/{call['audio_file']}"
            )
            self._audit.on_recording_stored(
                call_sid=session.call_sid,
                call_id=session.call_id,
                recording_url=recording_url,
                duration=duration,
                storage_provider="local",
            )

    def _finalize_analytics(self, session: ActiveCallSession) -> None:
        if not session.analytics_id:
            return

        reminder_successful = (
            session.identity_verified
            and session.current_state == ConversationState.EMI_DISCUSSION
            and not session.objections_raised
        )

        self._analytics.end_conversation(
            session.analytics_id,
            final_state=session.current_state,
            identity_verified=session.identity_verified,
            reminder_successful=reminder_successful,
            objections_raised=session.objections_raised,
            escalation_triggered=session.current_state == ConversationState.ESCALATION,
            escalation_reason=session.escalation_reason,
            started_at=session.started_at,
        )

        duration = None
        if session.started_at:
            duration = (datetime.now(timezone.utc) - session.started_at).total_seconds()

        callback_used = "schedule_callback" in session.tools_used
        self._analytics.record_call_outcome(
            agent_id=session.agent_id,
            successful=reminder_successful or session.current_state == ConversationState.CALL_COMPLETION,
            escalated=session.current_state == ConversationState.ESCALATION,
            callback=callback_used,
            duration_seconds=duration,
        )

    def _create_follow_up_callback(
        self,
        session: ActiveCallSession,
        analysis: Any,
    ) -> None:
        follow_up = analysis.follow_up
        if not follow_up.follow_up_date:
            return

        existing = self._has_scheduled_callback(session.call_id)
        if existing:
            return

        self._callbacks.schedule(
            customer_id=session.customer_id,
            date=follow_up.follow_up_date,
            time=follow_up.follow_up_time or "10:00",
            call_id=session.call_id,
            notes=analysis.summary[:500],
        )

    @staticmethod
    def _has_scheduled_callback(call_id: str) -> bool:
        try:
            return MongoDB.callbacks().count_documents({"call_id": call_id}) > 0
        except Exception:
            return False

    @staticmethod
    def _build_transcript(call_id: str) -> str:
        try:
            entries = find_sorted(
                MongoDB.transcripts(),
                {"call_id": call_id},
                sort_field="timestamp",
                sort_direction=1,
            )
            lines = []
            for entry in entries:
                role = entry.get("role", "unknown").upper()
                content = entry.get("content", "")
                lines.append(f"{role}: {content}")
            return "\n".join(lines)
        except Exception as exc:
            logger.error("Failed to build transcript for call %s: %s", call_id, exc)
            return ""

    @staticmethod
    def _to_object_id(call_id: str):
        from bson import ObjectId

        try:
            return ObjectId(call_id)
        except Exception:
            return None
