"""Active call session tracking and conversation persistence."""



import asyncio

import logging

from dataclasses import dataclass, field

from datetime import datetime, timezone

from typing import Any, Optional, TYPE_CHECKING

from bson import ObjectId

from pymongo.errors import PyMongoError



from app.agents.states import ConversationState

from app.core.config import Settings

from app.core.exceptions import DatabaseError

from app.core.logging_config import log_with_context

from app.database.mongodb import MongoDB

from app.models.agent import AgentConfig
from app.utils.mongo_query import find_sorted

from app.models.conversation import (

    ConversationMessage,

    ConversationSessionResponse,

    TranscriptEntry,

    TranscriptResponse,

)



logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from app.services.audit_service import AuditService


@dataclass

class ActiveCallSession:

    """In-memory state for an active media stream call."""



    call_id: str

    call_sid: str

    stream_sid: str

    customer_id: str

    customer_name: str

    session_id: str

    agent_id: str = ""

    agent_config: Optional[AgentConfig] = None

    current_state: ConversationState = ConversationState.GREETING

    identity_verified: bool = False

    agent_context: dict[str, Any] = field(default_factory=dict)

    objections_raised: list[str] = field(default_factory=list)

    escalation_reason: str = ""

    escalation_category: str = ""

    sentiment_history: list[str] = field(default_factory=list)

    handoff_initiated: bool = False

    analytics_id: str = ""

    tools_used: list[str] = field(default_factory=list)

    started_at: Optional[datetime] = None

    # Phase 8 — Compliance
    awaiting_consent: bool = False
    consent_status: str = ""
    consent_denied: bool = False
    pending_greeting: str = ""
    compliance_disclosure_text: str = ""
    skip_next_agent_turn: bool = False

    messages: list[dict[str, str]] = field(default_factory=list)

    is_ai_speaking: bool = False

    is_processing: bool = False

    playback_task: Optional[asyncio.Task[None]] = None

    playback_cancelled: bool = False

    websocket: Any = None





class CallSessionManager:

    """

    Tracks active calls, maintains conversation memory, and persists transcripts.



    Combines in-memory session state with MongoDB persistence.

    """



    def __init__(
        self,
        settings: Settings,
        audit_service: Optional["AuditService"] = None,
    ) -> None:

        self._settings = settings

        self._audit = audit_service

        self._sessions: dict[str, ActiveCallSession] = {}



    def create_session(

        self,

        call_id: str,

        call_sid: str,

        stream_sid: str,

        customer_id: str,

        customer_name: str,

        *,

        agent_id: str = "",

        agent_config: Optional[AgentConfig] = None,

        greeting: str = "",

        agent_context: dict[str, Any] | None = None,

        analytics_id: str = "",

    ) -> ActiveCallSession:

        """Initialize a new conversation session in memory and MongoDB."""

        system_content = agent_config.system_prompt[:500] if agent_config else ""

        if not greeting:

            greeting = (

                f"Hello {customer_name}. This is {self._settings.bank_name}. "

                "How may I assist you today?"

            )



        now = datetime.now(timezone.utc)

        ctx = agent_context or {}



        messages: list[dict[str, str]] = [

            {"role": "system", "content": system_content},

            {"role": "assistant", "content": greeting},

        ]



        session_doc: dict[str, Any] = {

            "call_id": call_id,

            "call_sid": call_sid,

            "customer_id": customer_id,

            "agent_id": agent_id,

            "current_state": ConversationState.GREETING.value,

            "identity_verified": False,

            "agent_context": ctx,

            "objections_raised": [],

            "messages": messages,

            "started_at": now,

            "updated_at": now,

        }



        try:

            result = MongoDB.conversation_sessions().insert_one(session_doc)

        except PyMongoError as exc:

            raise DatabaseError(str(exc)) from exc



        session_id = str(result.inserted_id)



        self._persist_transcript(

            call_id=call_id,

            call_sid=call_sid,

            customer_id=customer_id,

            role="assistant",

            content=greeting,

        )



        session = ActiveCallSession(

            call_id=call_id,

            call_sid=call_sid,

            stream_sid=stream_sid,

            customer_id=customer_id,

            customer_name=customer_name,

            session_id=session_id,

            agent_id=agent_id,

            agent_config=agent_config,

            current_state=ConversationState.GREETING,

            agent_context=ctx,

            analytics_id=analytics_id,

            started_at=now,

            messages=messages,

            pending_greeting=greeting,

        )

        self._sessions[stream_sid] = session



        log_with_context(

            logger,

            logging.INFO,

            "Call session started",

            call_id=call_id,

            twilio_call_sid=call_sid,

            stream_sid=stream_sid,

            customer_id=customer_id,

            agent_id=agent_id,

            event="call_session_started",

        )



        return session



    def get_session(self, stream_sid: str) -> ActiveCallSession | None:

        return self._sessions.get(stream_sid)



    def get_session_by_call_sid(self, call_sid: str) -> ActiveCallSession | None:

        for session in self._sessions.values():

            if session.call_sid == call_sid:

                return session

        return None



    def add_user_message(self, session: ActiveCallSession, content: str) -> None:

        session.messages.append({"role": "user", "content": content})

        self._update_session_messages(session)

        self._persist_transcript(

            call_id=session.call_id,

            call_sid=session.call_sid,

            customer_id=session.customer_id,

            role="user",

            content=content,

        )

        if self._audit:
            self._audit.on_user_message(
                call_sid=session.call_sid,
                call_id=session.call_id,
                content=content,
            )

        log_with_context(

            logger,

            logging.INFO,

            f"User said: {content[:120]}",

            call_id=session.call_id,

            event="user_transcript",

        )



    def add_assistant_message(self, session: ActiveCallSession, content: str) -> None:

        session.messages.append({"role": "assistant", "content": content})

        self._update_session_messages(session)

        self._persist_transcript(

            call_id=session.call_id,

            call_sid=session.call_sid,

            customer_id=session.customer_id,

            role="assistant",

            content=content,

        )

        if self._audit and not session.awaiting_consent:
            self._audit.on_assistant_message(
                call_sid=session.call_sid,
                call_id=session.call_id,
                content=content,
            )

        log_with_context(

            logger,

            logging.INFO,

            f"Assistant said: {content[:120]}",

            call_id=session.call_id,

            event="assistant_response",

        )



    def update_conversation_state(self, session: ActiveCallSession) -> None:

        """Persist conversation state machine fields to MongoDB."""

        try:

            MongoDB.conversation_sessions().update_one(

                {"_id": ObjectId(session.session_id)},

                {

                    "$set": {

                        "current_state": session.current_state.value,

                        "identity_verified": session.identity_verified,

                        "objections_raised": session.objections_raised,

                        "messages": session.messages,

                        "updated_at": datetime.now(timezone.utc),

                    }

                },

            )

        except PyMongoError as exc:

            logger.error("Failed to update conversation state: %s", exc)



    def _update_session_messages(self, session: ActiveCallSession) -> None:

        try:

            MongoDB.conversation_sessions().update_one(

                {"_id": ObjectId(session.session_id)},

                {

                    "$set": {

                        "messages": session.messages,

                        "updated_at": datetime.now(timezone.utc),

                    }

                },

            )

        except PyMongoError as exc:

            logger.error("Failed to update conversation session: %s", exc)



    def _persist_transcript(

        self,

        call_id: str,

        call_sid: str,

        customer_id: str,

        role: str,

        content: str,

    ) -> None:

        try:

            MongoDB.transcripts().insert_one(

                {

                    "call_id": call_id,

                    "call_sid": call_sid,

                    "customer_id": customer_id,

                    "role": role,

                    "content": content,

                    "timestamp": datetime.now(timezone.utc),

                }

            )

        except PyMongoError as exc:

            logger.error("Failed to persist transcript: %s", exc)



    async def cancel_playback(self, session: ActiveCallSession) -> None:

        """Stop current AI audio playback (barge-in)."""

        session.playback_cancelled = True

        session.is_ai_speaking = False



        if session.playback_task and not session.playback_task.done():

            session.playback_task.cancel()

            try:

                await session.playback_task

            except asyncio.CancelledError:

                pass

            session.playback_task = None



        log_with_context(

            logger,

            logging.INFO,

            "Playback cancelled (barge-in)",

            call_id=session.call_id,

            event="barge_in",

        )



    def end_session(self, stream_sid: str) -> ActiveCallSession | None:

        """Remove active session after call ends. Returns session for finalization."""

        session = self._sessions.pop(stream_sid, None)

        if session:

            log_with_context(

                logger,

                logging.INFO,

                "Call session ended",

                call_id=session.call_id,

                twilio_call_sid=session.call_sid,

                final_state=session.current_state.value,

                event="call_session_ended",

            )

        return session



    def get_conversation_by_call_id(self, call_id: str) -> ConversationSessionResponse | None:

        try:

            doc = MongoDB.conversation_sessions().find_one({"call_id": call_id})

        except PyMongoError as exc:

            raise DatabaseError(str(exc)) from exc



        if not doc:

            return None



        return ConversationSessionResponse(

            id=str(doc["_id"]),

            call_id=doc["call_id"],

            call_sid=doc.get("call_sid", ""),

            customer_id=doc["customer_id"],

            agent_id=doc.get("agent_id", ""),

            current_state=doc.get("current_state", "GREETING"),

            identity_verified=doc.get("identity_verified", False),

            messages=[ConversationMessage(**m) for m in doc.get("messages", [])],

            started_at=doc["started_at"],

            updated_at=doc["updated_at"],

        )



    def get_transcript_by_call_id(self, call_id: str) -> TranscriptResponse | None:

        try:

            session = MongoDB.conversation_sessions().find_one({"call_id": call_id})

            entries_raw = find_sorted(
                MongoDB.transcripts(),
                {"call_id": call_id},
                sort_field="timestamp",
                sort_direction=1,
            )

            entries = entries_raw

        except PyMongoError as exc:

            raise DatabaseError(str(exc)) from exc



        if not session and not entries:

            return None



        return TranscriptResponse(

            call_id=call_id,

            call_sid=session.get("call_sid", "") if session else "",

            customer_id=session.get("customer_id", "") if session else "",

            entries=[

                TranscriptEntry(

                    role=e["role"],

                    content=e["content"],

                    timestamp=e["timestamp"],

                )

                for e in entries

            ],

            started_at=session.get("started_at") if session else None,

            updated_at=session.get("updated_at") if session else None,

        )

