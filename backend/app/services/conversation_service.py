"""Orchestrates STT → Agent Engine → Groq Tools → TTS conversation turns."""

import asyncio
import json
import logging
import time
import uuid

from app.agents.engine import AgentEngine, MAX_REGENERATION_ATTEMPTS
from app.agents.seed.default_agents import DEFAULT_AGENT_ID
from app.agents.states import ConversationState
from app.core.config import get_settings
from app.core.logging_config import log_with_context
from app.models.agent import AgentConfig, AgentTurnContext
from app.agents.manager import AgentManager
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.agent_config_service import AgentConfigService
from app.services.call_session_manager import ActiveCallSession, CallSessionManager
from app.services.compliance_middleware import ComplianceMiddleware
from app.services.tts_service import TextToSpeechService
from app.services.groq_service import GroqService
from app.services.language_manager import LanguageManager
from app.services.post_call_service import PostCallService
from app.services.tool_execution_service import ToolExecutionService
from app.services.barge_in_service import BargeInService
from app.services.conversation_behavior_engine import ConversationBehaviorEngine
from app.services.speech_pacing_manager import SpeechPacingManager
from app.services.turn_manager import TurnManager
from app.services.voice_activity_service import VoiceActivityService
from app.services.sentiment_aware_response_engine import SentimentAwareResponseEngine
from app.services.conversation_quality_service import ConversationQualityService
from app.services.banking_service import BankingService
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
        tts_service: TextToSpeechService,
        agent_config_service: AgentConfigService,
        agent_manager: AgentManager,
        agent_analytics_service: AgentAnalyticsService,
        tool_registry: ToolRegistry,
        tool_execution_service: ToolExecutionService,
        post_call_service: PostCallService,
        language_manager: LanguageManager | None = None,
        compliance_middleware: ComplianceMiddleware | None = None,
        barge_in_service: BargeInService | None = None,
        voice_activity_service: VoiceActivityService | None = None,
        turn_manager: TurnManager | None = None,
        speech_pacing_manager: SpeechPacingManager | None = None,
        behavior_engine: ConversationBehaviorEngine | None = None,
        sentiment_aware_engine: SentimentAwareResponseEngine | None = None,
        conversation_quality_service: ConversationQualityService | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._groq = groq_service
        self._tts = tts_service
        self._agent_configs = agent_config_service
        self._agent_manager = agent_manager
        self._analytics = agent_analytics_service
        self._tool_registry = tool_registry
        self._tool_executor = tool_execution_service
        self._post_call = post_call_service
        self._language = language_manager
        self._compliance = compliance_middleware
        self._engine = AgentEngine()
        self._barge_in = barge_in_service or BargeInService(session_manager)
        self._vad = voice_activity_service or VoiceActivityService()
        self._turns = turn_manager or TurnManager()
        self._pacing = speech_pacing_manager or SpeechPacingManager()
        self._behavior = behavior_engine or ConversationBehaviorEngine()
        self._sentiment_aware = sentiment_aware_engine or SentimentAwareResponseEngine()
        self._quality = conversation_quality_service or ConversationQualityService()
        self._banking = BankingService()

    def preload_emi_for_session(self, session: ActiveCallSession) -> None:
        """Load EMI details from banking service into session context (no user input needed)."""
        if not session.customer_id:
            return
        if session.agent_context.get("emi_amount") and session.agent_context.get("due_date"):
            return
        try:
            data = self._banking.check_emi_due(session.customer_id)
            amount = data.get("emi_amount")
            session.agent_context.update(
                {
                    "emi_amount": amount,
                    "due_date": data.get("due_date", ""),
                    "payment_status": data.get("status", ""),
                    "loan_account": data.get("loan_id", ""),
                }
            )
            self._session_manager.update_conversation_state(session)
            log_with_context(
                logger,
                logging.INFO,
                "EMI context preloaded from database",
                call_id=session.call_id,
                event="emi_context_preloaded",
            )
        except Exception as exc:
            logger.warning(
                "Failed to preload EMI context | call_id=%s error=%s",
                session.call_id,
                exc,
            )

    async def play_greeting(self, session: ActiveCallSession) -> None:
        """Play opening: Hello + language detect, legacy consent, or standard greeting."""
        if self._compliance and self._compliance.enabled:
            self._compliance.on_call_started(session)
            if self._compliance.use_language_first_flow:
                await self._compliance.run_initial_hello(session, self)
                return
            await self._compliance.run_pre_call_compliance(session, self)
            return

        greeting = session.pending_greeting or session.messages[-1]["content"]
        await self._speak(session, greeting)

    @staticmethod
    def _is_echo_greeting_only(text: str) -> bool:
        """Ignore STT picking up the agent's own Hello or a bare greeting echo."""
        words = [w.strip(".,?!") for w in text.lower().split() if w.strip(".,?!")]
        if not words or len(words) > 3:
            return False
        greetings = {"hello", "hi", "hey", "hola", "namaste", "haan", "ji", "yes", "yeah"}
        return all(w in greetings for w in words)

    async def _handle_initial_language_turn(
        self, session: ActiveCallSession, text: str
    ) -> None:
        """Detect language from first customer utterance and play localized intro."""
        settings = get_settings()

        if self._is_echo_greeting_only(text):
            log_with_context(
                logger,
                logging.INFO,
                "Ignoring echo greeting — still awaiting customer language",
                call_id=session.call_id,
                event="initial_language_echo_ignored",
            )
            return

        session.awaiting_initial_language = False

        if not self._language:
            intro = session.pending_greeting or "How may I help you today?"
            self._session_manager.add_user_message(session, text)
            self._session_manager.add_assistant_message(session, intro)
            await self._speak(session, intro)
            return

        agent_doc = self._get_agent_doc(session)
        lang, new_config = self._language.resolve_language_from_first_utterance(
            text,
            agent_doc,
            session.active_language,
            customer_phone=session.customer_phone,
        )
        session.agent_config = new_config
        session.active_language = lang
        session.language_confidence = 0.9
        self._language.store_customer_language(session.customer_id, lang)

        if session.analytics_id:
            self._analytics.update_call_language(session.analytics_id, lang)

        intro = self._language.build_intro_after_hello(
            lang,
            new_config,
            settings.bank_name,
            customer_name=session.customer_name,
            agent_context=session.agent_context,
            user_first_utterance=text,
        )

        self._session_manager.add_user_message(session, text)
        self._session_manager.add_assistant_message(session, intro)

        if self._compliance:
            self._compliance.record_opening_consent(
                session, language=lang, customer_response=text
            )

        session.ignore_barge_in = True
        try:
            await self._speak(session, intro)
        finally:
            session.ignore_barge_in = False

        stt = getattr(session, "stt", None)
        if stt is not None and lang == "hi":
            stt.schedule_language_change("hi")

        opening_msg = (
            "भाषा-प्रथम परिचय पूर्ण (हिंदी)"
            if lang == "hi"
            else f"Language-first opening completed in {lang}"
        )
        log_with_context(
            logger,
            logging.INFO,
            opening_msg,
            call_id=session.call_id,
            event="language_first_opening_completed",
            active_language=lang,
        )

    async def handle_user_transcript(
        self,
        session: ActiveCallSession,
        transcript: str,
        stt_latency_ms: float,
    ) -> None:
        """Process a final user utterance through the agent + tool pipeline."""
        if session.handoff_initiated:
            return

        text = transcript.strip()
        if len(text) < 2:
            return
        self._vad.on_speech_stopped(session)

        session.is_processing = True
        self._turns.set_processing(session)
        turn_start = time.perf_counter()

        try:
            if session.is_ai_speaking:
                await self._handle_barge_in(session)

            if session.awaiting_initial_language:
                await self._handle_initial_language_turn(session, text)
                return

            if self._compliance and session.awaiting_consent:
                continue_call = await self._compliance.handle_consent_response(
                    session, text, self
                )
                if not continue_call:
                    if session.consent_denied:
                        session.handoff_initiated = True
                    return

            self._session_manager.add_user_message(session, text)

            switch_ack: str | None = None
            if self._language:
                agent_doc = self._get_agent_doc(session)
                detection, new_config, switch_ack = self._language.process_transcript(
                    text=text,
                    agent_doc=agent_doc,
                    customer_id=session.customer_id,
                    call_id=session.call_id,
                    call_sid=session.call_sid,
                    current_language=session.active_language,
                )
                session.language_confidence = detection.confidence
                if new_config:
                    session.agent_config = new_config
                    session.active_language = detection.language
                    session.language_switches += 1
                    stt = getattr(session, "stt", None)
                    if stt is not None and detection.language == "hi":
                        stt.schedule_language_change(detection.language)
                    if session.analytics_id:
                        self._analytics.record_language_switch(session.analytics_id)
                        self._analytics.update_call_language(
                            session.analytics_id, detection.language
                        )

            if switch_ack:
                self._session_manager.add_assistant_message(session, switch_ack)
                await self._speak(session, switch_ack)
                if detection.switch_requested and len(text.split()) <= 12:
                    self._session_manager.update_conversation_state(session)
                    return

            if session.skip_next_agent_turn:
                session.skip_next_agent_turn = False
                return

            agent_config = self._get_agent_config(session)
            turn_context = self._build_turn_context(session)
            was_identity_verified = session.identity_verified
            turn_result = self._engine.process_user_turn(agent_config, turn_context, text)

            session.current_state = turn_result["updated_context"].current_state
            session.identity_verified = turn_result["updated_context"].identity_verified
            identity_just_confirmed = (
                not was_identity_verified and session.identity_verified
            )
            if session.identity_verified:
                self.preload_emi_for_session(session)
                turn_result["updated_context"].agent_context = dict(
                    session.agent_context
                )
            session.objections_raised = turn_result["updated_context"].objections_raised

            escalation = turn_result["escalation"]
            if escalation and escalation.escalate:
                session.escalation_reason = turn_result.get(
                    "transfer_reason", escalation.reason
                )
                session.escalation_category = turn_result.get("escalation_category", "")

            updated = turn_result["updated_context"]
            session.sentiment_history = list(updated.sentiment_history)

            try:
                response_text, tools_used = await self._generate_response(
                    session,
                    agent_config,
                    turn_result,
                )
            except Exception as exc:
                log_with_context(
                    logger,
                    logging.ERROR,
                    f"Response generation failed: {exc}",
                    call_id=session.call_id,
                    event="response_generation_failed",
                )
                response_text, tools_used = await self._recover_from_llm_failure(
                    session,
                    agent_config,
                    identity_just_confirmed=identity_just_confirmed,
                )
            response_text, detected_sentiment = self._sentiment_aware.adapt_response(
                text, response_text
            )
            session.last_customer_sentiment = detected_sentiment
            response_text = self._behavior.shape_response(
                response_text,
                session.active_language,
                sentiment=detected_sentiment,
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

            delay_ms = self._pacing.next_delay_ms()
            await asyncio.sleep(delay_ms / 1000)
            session.response_latency_ms_sum += delay_ms
            session.response_latency_count += 1
            tts_start = time.perf_counter()
            await self._speak(session, response_text)
            tts_ms = (time.perf_counter() - tts_start) * 1000

            total_ms = (time.perf_counter() - turn_start) * 1000
            session.turn_count += 1
            session.total_turn_duration_ms += total_ms

            log_with_context(
                logger,
                logging.INFO,
                "Conversation turn completed",
                call_id=session.call_id,
                state=session.current_state.value,
                tools_used=tools_used,
                stt_ms=round(stt_latency_ms, 1),
                groq_ms=round(getattr(session, "_last_groq_ms", 0), 1),
                tts_ms=round(tts_ms, 1),
                tts_provider=self._tts.provider_name,
                total_ms=round(total_ms, 1),
                event="turn_completed",
            )
        except asyncio.CancelledError:
            logger.debug("Conversation turn cancelled | call_id=%s", session.call_id)
            raise
        except Exception as exc:
            if not session.websocket:
                logger.debug(
                    "Skipping turn error handling — call already ended | call_id=%s",
                    session.call_id,
                )
                return
            log_with_context(
                logger,
                logging.ERROR,
                f"Conversation turn failed: {exc}",
                call_id=session.call_id,
                event="turn_error",
            )
            try:
                await self._speak(
                    session,
                    self._engine.get_api_failure_response(
                        customer_name=session.customer_name,
                    ),
                )
            except Exception:
                pass
        finally:
            session.is_processing = False
            if not session.is_ai_speaking:
                self._turns.set_customer_turn(session)

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
        turn_context.agent_context = dict(session.agent_context)
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
                "payment_link_sent": session.payment_link_sent,
                "payment_link_result": dict(session.payment_link_result),
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
                enable_tools=(attempt == 0),
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
                if tool_context.extra.get("payment_link_sent"):
                    session.payment_link_sent = True
                    session.payment_link_result = dict(
                        tool_context.extra.get("payment_link_result") or {}
                    )
                return response_text, tools_used

            log_with_context(
                logger,
                logging.WARNING,
                f"Response validation failed (attempt {attempt + 1}): {validation.violations}",
                call_id=session.call_id,
                event="response_validation_failed",
            )
            regeneration_hint = self._engine.get_regeneration_hint(validation.violations)

        if tool_context.extra.get("payment_link_sent"):
            session.payment_link_sent = True
            session.payment_link_result = dict(
                tool_context.extra.get("payment_link_result") or {}
            )
        return self._engine.get_fallback_response(agent_config), tools_used

    async def _recover_from_llm_failure(
        self,
        session: ActiveCallSession,
        agent_config: AgentConfig,
        *,
        identity_just_confirmed: bool = False,
    ) -> tuple[str, list[str]]:
        """
        Produce a sensible spoken response when Groq is unavailable.

        After identity confirmation, runs check_emi_due directly so the call
        can continue without the primary LLM.
        """
        if identity_just_confirmed and session.identity_verified:
            tool_context = ToolContext(
                customer_id=session.customer_id,
                call_id=session.call_id,
                call_sid=session.call_sid,
                customer_name=session.customer_name,
                agent_id=session.agent_id,
                identity_verified=True,
                messages=list(session.messages),
                tools_used=list(session.tools_used),
                extra={
                    "payment_link_sent": session.payment_link_sent,
                    "payment_link_result": dict(session.payment_link_result),
                },
            )
            try:
                result, _ = await self._tool_executor.execute_and_log(
                    "check_emi_due",
                    {"customer_id": session.customer_id},
                    tool_context,
                )
                if result.success:
                    return (
                        self._engine.build_emi_summary_response(
                            session.customer_name,
                            result.data,
                            language=session.active_language or "en",
                        ),
                        ["check_emi_due"],
                    )
            except Exception as exc:
                logger.warning("EMI recovery tool failed: %s", exc)

        return (
            self._engine.get_api_failure_response(
                customer_name=session.customer_name,
                identity_just_confirmed=identity_just_confirmed,
            ),
            [],
        )

    def _get_agent_doc(self, session: ActiveCallSession) -> dict:
        agent_id = session.agent_id or (
            session.agent_config.agent_id if session.agent_config else ""
        )
        if not agent_id and session.agent_config:
            agent_id = session.agent_config.agent_id or DEFAULT_AGENT_ID
        if not agent_id:
            runtime = self._agent_manager.get_default_agent()
            agent_id = runtime.agent_id
        return self._agent_manager.get_agent_document_raw(agent_id)

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
        """Trigger barge-in when the customer speaks over the agent or during processing."""
        if session.ignore_barge_in:
            return
        self._vad.on_speech_started(session)
        self._turns.set_customer_turn(session)
        if session.is_ai_speaking or session.is_processing:
            await self._handle_barge_in(session)

    async def finalize_session(self, session: ActiveCallSession) -> None:
        """Finalize analytics, analyze conversation, and persist to internal CRM."""
        await self._post_call.process_call_end(session)
        self._quality.finalize_metrics(session)

    async def _handle_barge_in(self, session: ActiveCallSession) -> None:
        await self._barge_in.handle_interrupt(session)

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
        if not session.websocket:
            return
        session.playback_cancelled = False
        session.is_ai_speaking = True
        self._turns.set_ai_turn(session)

        agent_config = self._get_agent_config(session)
        voice_id = agent_config.voice or None
        language_code = getattr(session, "active_language", None) or agent_config.language_code or "en"
        audio_bytes = await self._tts.generate_response_audio(
            text,
            voice_id=voice_id,
            language_code=language_code,
        )

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
            self._turns.set_customer_turn(session)

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
