"""Admin portal aggregation and platform settings."""

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.admin import (
    ActiveCallResponse,
    DashboardSummary,
    PlatformSettingsResponse,
    PlatformSettingsUpdate,
    RecentActivityItem,
)
from app.services.call_session_manager import CallSessionManager
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)

COMPLETED_STATUSES = {"completed", "in-progress"}
SETTINGS_DOC_ID = "platform_settings"


class AdminService:
    """Aggregates metrics and manages platform settings for the admin portal."""

    def __init__(
        self,
        settings: Settings,
        session_manager: CallSessionManager,
    ) -> None:
        self._settings = settings
        self._session_manager = session_manager

    def get_dashboard_summary(self) -> DashboardSummary:
        try:
            total_calls = MongoDB.calls().count_documents({})
            completed_calls = MongoDB.calls().count_documents(
                {"status": {"$in": list(COMPLETED_STATUSES)}}
            )
            active_campaigns = MongoDB.campaigns().count_documents(
                {"status": {"$in": ["running", "paused"]}}
            )
            escalations = MongoDB.escalations().count_documents({})
            callbacks = MongoDB.callbacks().count_documents({})
            agents = MongoDB.agents().count_documents({"status": "ACTIVE"})
            customers = MongoDB.customers().count_documents({})
            live_calls = len(self._session_manager.list_active_sessions())

            successful = MongoDB.conversation_analytics().count_documents(
                {"completed": True}
            )
            total_analytics = MongoDB.conversation_analytics().count_documents({})
            success_rate = (
                round(successful / total_analytics * 100, 1)
                if total_analytics
                else 0.0
            )

            recent_activity = self._build_recent_activity()

            return DashboardSummary(
                total_calls=total_calls,
                active_campaigns=active_campaigns,
                completed_calls=completed_calls,
                escalations=escalations,
                callbacks=callbacks,
                agents=agents,
                customers=customers,
                live_calls=live_calls,
                call_success_rate=success_rate,
                recent_activity=recent_activity,
            )
        except PyMongoError as exc:
            logger.error("Failed to build dashboard summary: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def _build_recent_activity(self) -> list[RecentActivityItem]:
        items: list[RecentActivityItem] = []

        for doc in find_sorted(
            MongoDB.calls(), sort_field="created_at", sort_direction=-1, limit=8
        ):
            items.append(
                RecentActivityItem(
                    id=str(doc["_id"]),
                    type="call",
                    title=f"Call to {doc.get('phone', 'unknown')}",
                    description=f"Status: {doc.get('status', 'unknown')}",
                    timestamp=doc["created_at"],
                )
            )

        for doc in find_sorted(
            MongoDB.escalations(), sort_field="created_at", sort_direction=-1, limit=5
        ):
            items.append(
                RecentActivityItem(
                    id=str(doc["_id"]),
                    type="escalation",
                    title="Escalation triggered",
                    description=doc.get("reason", doc.get("escalation_type", "")),
                    timestamp=doc["created_at"],
                )
            )

        items.sort(key=lambda x: x.timestamp, reverse=True)
        return items[:12]

    def get_active_calls(self) -> list[ActiveCallResponse]:
        now = datetime.now(timezone.utc)
        results: list[ActiveCallResponse] = []

        for session in self._session_manager.list_active_sessions():
            duration = 0.0
            if session.started_at:
                started = session.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                duration = (now - started).total_seconds()

            agent_name = ""
            if session.agent_config:
                agent_name = session.agent_config.agent_name

            results.append(
                ActiveCallResponse(
                    call_id=session.call_id,
                    call_sid=session.call_sid,
                    customer_id=session.customer_id,
                    customer_name=session.customer_name,
                    agent_id=session.agent_id,
                    agent_name=agent_name,
                    current_state=session.current_state.value
                    if hasattr(session.current_state, "value")
                    else str(session.current_state),
                    duration_seconds=round(duration, 1),
                    started_at=session.started_at,
                )
            )

        return results

    def get_settings(self) -> PlatformSettingsResponse:
        overrides = self._load_settings_overrides()
        s = self._settings

        return PlatformSettingsResponse(
            bank_name=overrides.get("bank_name", s.bank_name),
            twilio_configured=bool(s.twilio_account_sid and s.twilio_auth_token),
            twilio_phone_number=s.twilio_phone_number,
            groq_configured=bool(s.groq_api_key),
            groq_model=overrides.get("groq_model", s.groq_model),
            elevenlabs_configured=bool(s.elevenlabs_api_key),
            elevenlabs_voice_id=overrides.get(
                "elevenlabs_voice_id", s.elevenlabs_voice_id
            ),
            elevenlabs_model_id=s.elevenlabs_model_id,
            deepgram_configured=bool(s.deepgram_api_key),
            campaign_batch_size=overrides.get(
                "campaign_batch_size", s.campaign_batch_size
            ),
            campaign_call_interval_seconds=overrides.get(
                "campaign_call_interval_seconds", s.campaign_call_interval_seconds
            ),
            campaign_max_concurrent_calls=overrides.get(
                "campaign_max_concurrent_calls", s.campaign_max_concurrent_calls
            ),
            handoff_enabled=overrides.get("handoff_enabled", s.handoff_enabled),
            human_agent_phone=overrides.get(
                "human_agent_phone", s.human_agent_phone
            ),
            compliance_enabled=overrides.get(
                "compliance_enabled", s.compliance_enabled
            ),
            compliance_disclosure_template=overrides.get(
                "compliance_disclosure_template", s.compliance_disclosure_template
            ),
            compliance_consent_prompt=overrides.get(
                "compliance_consent_prompt", s.compliance_consent_prompt
            ),
            base_url=s.base_url,
        )

    def update_settings(self, payload: PlatformSettingsUpdate) -> PlatformSettingsResponse:
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not updates:
            return self.get_settings()

        try:
            MongoDB.get_db()["platform_settings"].update_one(
                {"_id": SETTINGS_DOC_ID},
                {"$set": {**updates, "updated_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("Failed to update platform settings: %s", exc)
            raise DatabaseError(str(exc)) from exc

        for key, value in updates.items():
            if hasattr(self._settings, key):
                object.__setattr__(self._settings, key, value)

        return self.get_settings()

    def _load_settings_overrides(self) -> dict[str, Any]:
        try:
            doc = MongoDB.get_db()["platform_settings"].find_one(
                {"_id": SETTINGS_DOC_ID}
            )
            if doc:
                return {k: v for k, v in doc.items() if k not in ("_id", "updated_at")}
        except PyMongoError:
            pass
        return {}
