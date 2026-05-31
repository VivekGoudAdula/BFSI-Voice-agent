"""Post-call processing orchestrator for CRM integration."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.states import ConversationState
from app.core.config import Settings
from app.core.logging_config import log_with_context
from app.database.mongodb import MongoDB
from app.models.crm import ProcessedCallData
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.call_analysis_service import CallAnalysisService
from app.services.call_session_manager import ActiveCallSession
from app.services.callback_service import CallbackService
from app.services.crm_data_service import CRMDataService
from app.services.crm_sync_service import CRMSyncService
from app.services.customer_service import CustomerService
from app.services.tool_execution_service import ToolExecutionService

logger = logging.getLogger(__name__)


class PostCallService:
    """
    Orchestrates post-call processing:
    analytics → analysis → persistence → CRM sync.
    """

    def __init__(
        self,
        settings: Settings,
        analytics_service: AgentAnalyticsService,
        call_analysis_service: CallAnalysisService,
        crm_data_service: CRMDataService,
        crm_sync_service: CRMSyncService,
        customer_service: CustomerService,
        tool_execution_service: ToolExecutionService,
        callback_service: CallbackService,
    ) -> None:
        self._settings = settings
        self._analytics = analytics_service
        self._analysis = call_analysis_service
        self._crm_data = crm_data_service
        self._crm_sync = crm_sync_service
        self._customers = customer_service
        self._tool_logs = tool_execution_service
        self._callbacks = callback_service
        self._processed_calls: set[str] = set()

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

        customer = self._customers.get_customer_by_id(session.customer_id)
        customer_phone = customer.get("phone", "") if customer else ""

        processed = ProcessedCallData(
            call_id=session.call_id,
            call_sid=session.call_sid,
            customer_id=session.customer_id,
            customer_name=session.customer_name,
            customer_phone=customer_phone,
            loan_id=session.agent_context.get("loan_account", ""),
            transcript=transcript,
            summary=analysis.summary,
            lead_status=analysis.lead_status,
            call_outcome=analysis.call_outcome,
            intent=analysis.intent,
            follow_up_actions=analysis.follow_up_actions,
            follow_up_date=analysis.follow_up.follow_up_date,
            follow_up_time=analysis.follow_up.follow_up_time,
            duration_seconds=duration,
            escalation_triggered=escalation_triggered,
            escalation_reason=session.escalation_reason,
            tools_used=tools_used,
            agent_context=session.agent_context,
        )

        self._crm_sync.schedule_background_sync(processed)

        log_with_context(
            logger,
            logging.INFO,
            "Post-call processing completed",
            call_id=call_id,
            lead_status=analysis.lead_status.value,
            call_outcome=analysis.call_outcome.value,
            event="post_call_completed",
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
            cursor = (
                MongoDB.transcripts()
                .find({"call_id": call_id})
                .sort("timestamp", 1)
            )
            lines = []
            for entry in cursor:
                role = entry.get("role", "unknown").upper()
                content = entry.get("content", "")
                lines.append(f"{role}: {content}")
            return "\n".join(lines)
        except Exception as exc:
            logger.error("Failed to build transcript for call %s: %s", call_id, exc)
            return ""
