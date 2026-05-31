"""Outbound call orchestration."""

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.agents.engine import AgentEngine
from app.core.config import get_settings
from app.core.exceptions import (
    AgentNotFoundError,
    CallNotFoundError,
    ConversationNotFoundError,
    CustomerNotFoundError,
    DatabaseError,
)
from app.core.logging_config import log_with_context
from app.database.mongodb import MongoDB
from app.models.call import AgentCallContext, CallResponse
from app.models.conversation import ConversationSessionResponse, TranscriptResponse
from app.services.agent_config_service import AgentConfigService
from app.services.call_session_manager import CallSessionManager
from app.services.customer_service import CustomerService
from app.services.elevenlabs_service import ElevenLabsService
from app.services.twilio_service import TwilioService
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


def _serialize_call(doc: dict[str, Any]) -> CallResponse:
    return CallResponse(
        id=str(doc["_id"]),
        customer_id=str(doc["customer_id"]),
        phone=doc["phone"],
        status=doc["status"],
        message=doc["message"],
        twilio_call_sid=doc.get("twilio_call_sid", ""),
        audio_file=doc.get("audio_file"),
        agent_id=doc.get("agent_id", ""),
        agent_name=doc.get("agent_name", ""),
        created_at=doc["created_at"],
    )


class CallService:
    """
    Orchestrates call initiation: customer lookup, agent selection, Twilio dial.

    Phase 3: uses configurable BFSI agent engine for EMI and future agents.
    """

    def __init__(
        self,
        customer_service: CustomerService,
        elevenlabs_service: ElevenLabsService,
        twilio_service: TwilioService,
        session_manager: CallSessionManager,
        agent_config_service: AgentConfigService,
    ) -> None:
        self._customer_service = customer_service
        self._elevenlabs = elevenlabs_service
        self._twilio = twilio_service
        self._session_manager = session_manager
        self._agent_configs = agent_config_service
        self._engine = AgentEngine()
        self._settings = get_settings()

    async def initiate_call(
        self,
        customer_id: str,
        agent_id: str = "",
        agent_context: AgentCallContext | None = None,
        campaign_id: str = "",
        campaign_customer_id: str = "",
    ) -> CallResponse:
        customer = self._customer_service.get_customer_by_id(customer_id)
        if not customer:
            raise CustomerNotFoundError(customer_id)

        agent_config = self._resolve_agent(agent_id)
        ctx = agent_context or AgentCallContext()
        ctx_dict = {k: v for k, v in ctx.model_dump().items() if v}

        customer_name = customer["name"]
        phone = customer["phone"]
        greeting = self._engine.build_greeting(agent_config, customer_name, ctx_dict)

        log_with_context(
            logger,
            logging.INFO,
            "Initiating agent call for customer",
            customer_id=customer_id,
            phone=phone,
            agent_id=agent_config.id,
            agent_name=agent_config.agent_name,
            event="call_flow_started",
        )

        call_doc: dict[str, Any] = {
            "customer_id": customer["_id"],
            "phone": phone,
            "status": "initiated",
            "message": greeting,
            "twilio_call_sid": "",
            "audio_file": None,
            "mode": "conversational",
            "agent_id": agent_config.id or "",
            "agent_name": agent_config.agent_name,
            "agent_context": ctx_dict,
            "campaign_id": campaign_id or None,
            "campaign_customer_id": campaign_customer_id or None,
            "created_at": datetime.now(timezone.utc),
        }

        try:
            insert_result = MongoDB.calls().insert_one(call_doc)
            call_doc["_id"] = insert_result.inserted_id
        except PyMongoError as exc:
            logger.error("Failed to persist call record: %s", exc)
            raise DatabaseError(str(exc)) from exc

        call_id = str(insert_result.inserted_id)

        twiml_url = (
            f"{self._settings.base_url.rstrip('/')}/webhooks/twilio/voice/{call_id}"
        )
        status_callback_url = self._twilio.build_status_callback_url(call_id)

        try:
            twilio_sid = self._twilio.place_call(
                to_phone=phone,
                twiml_url=twiml_url,
                status_callback_url=status_callback_url,
            )
        except Exception:
            MongoDB.calls().update_one(
                {"_id": insert_result.inserted_id},
                {"$set": {"status": "failed"}},
            )
            raise

        try:
            MongoDB.calls().update_one(
                {"_id": insert_result.inserted_id},
                {"$set": {"twilio_call_sid": twilio_sid}},
            )
        except PyMongoError as exc:
            logger.error("Failed to update call with Twilio SID: %s", exc)
            raise DatabaseError(str(exc)) from exc

        call_doc["twilio_call_sid"] = twilio_sid

        log_with_context(
            logger,
            logging.INFO,
            "Call initiated successfully",
            call_id=call_id,
            customer_id=customer_id,
            twilio_call_sid=twilio_sid,
            agent_name=agent_config.agent_name,
            event="call_initiated",
        )

        return _serialize_call(call_doc)

    def _resolve_agent(self, agent_id: str):
        if agent_id:
            agent = self._agent_configs.get_agent_by_id(agent_id)
            if not agent:
                raise AgentNotFoundError(agent_id)
            return agent

        agent = self._agent_configs.get_default_agent()
        if not agent:
            raise AgentNotFoundError("default")
        return agent

    def get_calls(self) -> list[CallResponse]:
        try:
            docs = find_sorted(MongoDB.calls(), sort_field="created_at", sort_direction=-1)
            return [_serialize_call(doc) for doc in docs]
        except PyMongoError as exc:
            logger.error("Failed to fetch calls: %s", exc)
            raise DatabaseError(str(exc)) from exc

    def get_call_by_id(self, call_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(call_id)
        except Exception:
            return None

        try:
            return MongoDB.calls().find_one({"_id": oid})
        except PyMongoError as exc:
            logger.error("Failed to fetch call %s: %s", call_id, exc)
            raise DatabaseError(str(exc)) from exc

    def get_call_by_twilio_sid(self, twilio_call_sid: str) -> dict[str, Any] | None:
        """Look up a call record by Twilio Call SID."""
        if not twilio_call_sid:
            return None
        try:
            return MongoDB.calls().find_one({"twilio_call_sid": twilio_call_sid})
        except PyMongoError as exc:
            logger.error("Failed to fetch call by Twilio SID %s: %s", twilio_call_sid, exc)
            raise DatabaseError(str(exc)) from exc

    def update_call_status(self, call_id: str, status: str) -> None:
        try:
            oid = ObjectId(call_id)
        except Exception:
            return

        try:
            MongoDB.calls().update_one({"_id": oid}, {"$set": {"status": status}})
            log_with_context(
                logger,
                logging.INFO,
                f"Call status updated to {status}",
                call_id=call_id,
                event="call_status_updated",
            )
        except PyMongoError as exc:
            logger.error("Failed to update call status: %s", exc)

    def get_call_context(self, call_id: str) -> dict[str, Any] | None:
        """Return customer, agent, and call context for an active call."""
        call = self.get_call_by_id(call_id)
        if not call:
            return None

        customer = self._customer_service.get_customer_by_id(str(call["customer_id"]))
        if not customer:
            return None

        agent_id = call.get("agent_id", "")
        agent_config = None
        if agent_id:
            agent_config = self._agent_configs.get_agent_by_id(agent_id)
        if not agent_config:
            agent_config = self._agent_configs.get_default_agent()

        greeting = ""
        if agent_config:
            ctx = call.get("agent_context", {})
            greeting = self._engine.build_greeting(
                agent_config, customer["name"], ctx
            )

        return {
            "customer_id": str(call["customer_id"]),
            "customer_name": customer["name"],
            "agent_id": agent_config.id if agent_config else "",
            "agent_config": agent_config,
            "agent_context": call.get("agent_context", {}),
            "greeting": greeting,
        }

    def get_transcript(self, call_id: str) -> TranscriptResponse:
        if not self.get_call_by_id(call_id):
            raise CallNotFoundError(call_id)

        result = self._session_manager.get_transcript_by_call_id(call_id)
        if not result:
            raise ConversationNotFoundError(call_id)
        return result

    def get_conversation(self, call_id: str) -> ConversationSessionResponse:
        if not self.get_call_by_id(call_id):
            raise CallNotFoundError(call_id)

        result = self._session_manager.get_conversation_by_call_id(call_id)
        if not result:
            raise ConversationNotFoundError(call_id)
        return result
