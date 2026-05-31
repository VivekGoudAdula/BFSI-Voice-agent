"""Orchestrates STT → Agent Engine → Groq Tools → TTS conversation turns."""

import asyncio
import json
import logging
import time

from app.agents.engine import AgentEngine, MAX_REGENERATION_ATTEMPTS
from app.agents.states import ConversationState
from app.core.logging_config import log_with_context
from app.models.agent import AgentConfig, AgentTurnContext
from app.agents.manager import AgentManager
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.agent_config_service import AgentConfigService
from app.services.call_session_manager import ActiveCallSession, CallSessionManager
from app.services.compliance_middleware import ComplianceMiddleware
from app.services.elevenlabs_service import ElevenLabsService
from app.services.groq_service import GroqService
from app.services.post_call_service import PostCallService
from app.services.tool_execution_service import ToolExecutionService
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from app.utils.audio import stream_mulaw_to_twilio

logger = logging.getLogger(__name__)


class ConversationService:
    """Handles multi-turn conversation with tool-calling agent pipeline."""

    def __init__(
        self,
        session_manager: CallSessionManager,
        groq_service: GroqService,
        elevenlabs_service: ElevenLabsService,
        agent_config_service: AgentConfigService,
        agent_manager: AgentManager,
        agent_analytics_service: AgentAnalyticsService,
        tool_registry: ToolRegistry,
        tool_execution_service: ToolExecutionService,
        post_call_service: PostCallService,
        compliance_middleware: ComplianceMiddleware | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._groq = groq_service
        self._elevenlabs = elevenlabs_service
        self._agent_configs = agent_config_service
        self._agent_manager = agent_manager
        self._analytics = agent_analytics_service
        self._tool_registry = tool_registry
        self._tool_executor = tool_execution_service
        self._post_call = post_call_service
        self._compliance = compliance_middleware
        self._engine = AgentEngine()

    async def play_greeting(self, session: ActiveCallSession) -> None:
        """Play compliance disclosure + consent, or the standard greeting."""
        if self._compliance and self._compliance.enabled:
            self._compliance.on_call_started(session)
            await self._compliance.run_pre_call_compliance(session, self)
            return

        greeting = session.pending_greeting or session.messages[-1]["content"]
        await self._speak(session, greeting)

    async def handle_user_transcript(
        self,
        session: ActiveCallSession,
        transcript: str,
        stt_latency_ms: float,
    ) -> None:
        """Process a final user utterance through the agent + tool pipeline."""
        if session.is_processing or session.handoff_initiated:
            return

        text = transcript.strip()
        if len(text) < 2:
            return

        session.is_processing = True
        turn_start = time.perf_counter()

        try:
            if session.is_ai_speaking:
                await self._handle_barge_in(session)

            if self._compliance and session.awaiting_consent:
                continue_call = await self._compliance.handle_consent_response(
                    session, text, self
                )
                if not continue_call:
                    if session.consent_denied:
                        session.handoff_initiated = True
                    return

            self._session_manager.add_user_message(session, text)

            if session.skip_next_agent_turn:
                session.skip_next_agent_turn = False
                return

            agent_config = self._get_agent_config(session)
            turn_context = self._build_turn_context(session)
            turn_result = self._engine.process_user_turn(agent_config, turn_context, text)

            session.current_state = turn_result["updated_context"].current_state
            session.identity_verified = turn_result["updated_context"].identity_verified
            session.objections_raised = turn_result["updated_context"].objections_raised

            escalation = turn_result["escalation"]
            if escalation and escalation.escalate:
                session.escalation_reason = turn_result.get(
                    "transfer_reason", escalation.reason
                )
                session.escalation_category = turn_result.get("escalation_category", "")

            updated = turn_result["updated_context"]
            session.sentiment_history = list(updated.sentiment_history)

            response_text, tools_used = await self._generate_response(
                session,
                agent_config,
                turn_result,
            )
            session.tools_used.extend(tools_used)

            self._session_manager.add_assistant_message(session, response_text)
            self._session_manager.update_conversation_state(session)

            if session.analytics_id:
                self._analytics.update_turn(
                    session.analytics_id,
                    current_state=session.current_state,
                    identity_verified=session.identity_verified,
                    objections_raised=session.objections_raised,
                    escalation_triggered=escalation.escalate if escalation else False,
                    escalation_reason=escalation.reason if escalation else "",
                )

            elevenlabs_start = time.perf_counter()
            await self._speak(session, response_text)
            elevenlabs_ms = (time.perf_counter() - elevenlabs_start) * 1000

            total_ms = (time.perf_counter() - turn_start) * 1000

            log_with_context(
                logger,
                logging.INFO,
                "Conversation turn completed",
                call_id=session.call_id,
                state=session.current_state.value,
                tools_used=tools_used,
                stt_ms=round(stt_latency_ms, 1),
                groq_ms=round(getattr(session, "_last_groq_ms", 0), 1),
                elevenlabs_ms=round(elevenlabs_ms, 1),
                total_ms=round(total_ms, 1),
                event="turn_completed",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Conversation turn failed: {exc}",
                call_id=session.call_id,
                event="turn_error",
            )
        finally:
            session.is_processing = False

    async def _generate_response(
        self,
        session: ActiveCallSession,
        agent_config: AgentConfig,
        turn_result: dict,
    ) -> tuple[str, list[str]]:
        """Generate response via Groq tool calling pipeline with validation."""
        if turn_result.get("use_objection_response"):
            return turn_result["objection_response"], []

        turn_context = turn_result["updated_context"]
        system_prompt = self._engine.build_system_prompt(agent_config, turn_context)
        groq_messages = [
            m for m in session.messages if m["role"] in ("user", "assistant")
        ]
        tools = self._tool_registry.get_openai_schemas(agent_config.tools or None)
        tool_context = ToolContext(
            customer_id=session.customer_id,
            call_id=session.call_id,
            call_sid=session.call_sid,
            customer_name=session.customer_name,
            agent_id=session.agent_id,
            identity_verified=session.identity_verified,
            messages=list(session.messages),
            tools_used=list(session.tools_used),
            sentiment_history=list(session.sentiment_history),
            handoff_initiated=session.handoff_initiated,
            extra={
                "escalation_category": turn_result.get("escalation_category", ""),
                "escalation_reason": turn_result.get("transfer_reason", ""),
                "agent_purpose": agent_config.purpose,
            },
        )

        forced_tool = None
        forced_args = None
        if turn_result.get("trigger_transfer"):
            forced_tool = "transfer_to_human"
            forced_args = {
                "call_sid": session.call_sid,
                "reason": turn_result.get("transfer_reason", "Escalation required"),
                "category": turn_result.get(
                    "escalation_category", "CUSTOMER_REQUESTED_HUMAN"
                ),
            }

        regeneration_hint = ""
        tools_used: list[str] = []

        for attempt in range(MAX_REGENERATION_ATTEMPTS + 1):
            response_text, groq_ms, tools_used = await self._groq.generate_with_tools(
                groq_messages,
                system_prompt + (f"\n\n{regeneration_hint}" if regeneration_hint else ""),
                tools,
                self._tool_executor,
                tool_context,
                forced_tool=forced_tool if attempt == 0 else None,
                forced_tool_args=forced_args if attempt == 0 else None,
            )
            session._last_groq_ms = groq_ms
            forced_tool = None  # only force on first attempt

            turn_context.tools_used = tools_used
            validation = self._engine.validate_response(
                response_text, agent_config, turn_context, tools_used=tools_used
            )
            if "transfer_to_human" in tools_used:
                session.handoff_initiated = True
                tool_context.handoff_initiated = True
                transfer_msg = turn_result.get("transfer_message")
                if transfer_msg:
                    response_text = transfer_msg

            if validation.is_valid:
                return response_text, tools_used

            log_with_context(
                logger,
                logging.WARNING,
                f"Response validation failed (attempt {attempt + 1}): {validation.violations}",
                call_id=session.call_id,
                event="response_validation_failed",
            )
            regeneration_hint = self._engine.get_regeneration_hint(validation.violations)

        return self._engine.get_fallback_response(agent_config), tools_used

    def _get_agent_config(self, session: ActiveCallSession) -> AgentConfig:
        if session.agent_config:
            return session.agent_config
        if session.agent_id:
            runtime = self._agent_manager.load_agent(session.agent_id)
            session.agent_config = runtime.to_agent_config()
            return session.agent_config
        runtime = self._agent_manager.get_default_agent()
        session.agent_config = runtime.to_agent_config()
        return session.agent_config

    def _build_turn_context(self, session: ActiveCallSession) -> AgentTurnContext:
        return AgentTurnContext(
            customer_name=session.customer_name,
            customer_id=session.customer_id,
            call_id=session.call_id,
            call_sid=session.call_sid,
            current_state=session.current_state,
            identity_verified=session.identity_verified,
            agent_context=session.agent_context,
            objections_raised=list(session.objections_raised),
            tools_used=list(session.tools_used),
            sentiment_history=list(session.sentiment_history),
        )

    async def handle_speech_started(self, session: ActiveCallSession) -> None:
        """Trigger barge-in when the customer starts speaking during AI playback."""
        if session.is_ai_speaking:
            await self._handle_barge_in(session)

    async def finalize_session(self, session: ActiveCallSession) -> None:
        """Finalize analytics, analyze conversation, and persist to internal CRM."""
        await self._post_call.process_call_end(session)

    async def _handle_barge_in(self, session: ActiveCallSession) -> None:
        await self._session_manager.cancel_playback(session)
        await self._send_clear(session)

    async def _send_clear(self, session: ActiveCallSession) -> None:
        if not session.websocket:
            return
        message = {"event": "clear", "streamSid": session.stream_sid}
        try:
            await session.websocket.send_text(json.dumps(message))
        except Exception as exc:
            logger.warning("Failed to send clear event: %s", exc)

    async def _speak(self, session: ActiveCallSession, text: str) -> None:
        """Generate TTS and stream mulaw audio to Twilio."""
        session.playback_cancelled = False
        session.is_ai_speaking = True

        agent_config = self._get_agent_config(session)
        voice_id = agent_config.voice or None
        audio_bytes = await self._elevenlabs.generate_response_audio(text, voice_id=voice_id)

        if session.playback_cancelled:
            session.is_ai_speaking = False
            return

        session.playback_task = asyncio.create_task(
            self._stream_audio_to_twilio(session, audio_bytes)
        )
        try:
            await session.playback_task
        except asyncio.CancelledError:
            pass
        finally:
            session.is_ai_speaking = False
            session.playback_task = None

    async def _stream_audio_to_twilio(
        self,
        session: ActiveCallSession,
        audio_bytes: bytes,
    ) -> None:
        if not session.websocket:
            return

        await stream_mulaw_to_twilio(
            websocket=session.websocket,
            stream_sid=session.stream_sid,
            audio=audio_bytes,
            is_cancelled=lambda: session.playback_cancelled,
        )

        if not session.playback_cancelled:
            mark_name = f"done-{int(time.time() * 1000)}"
            await session.websocket.send_text(
                json.dumps(
                    {
                        "event": "mark",
                        "streamSid": session.stream_sid,
                        "mark": {"name": mark_name},
                    },
                    separators=(",", ":"),
                )
            )
