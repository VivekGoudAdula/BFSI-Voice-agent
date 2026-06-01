"""Twilio Media Streams WebSocket endpoint."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.dependencies import (
    get_agent_analytics_service,
    get_agent_manager,
    get_call_service,
    get_call_session_manager,
    get_conversation_service,
    get_language_manager,
)
from app.core.logging_config import log_with_context
from app.services.speech_recognition_service import SpeechRecognitionService
from app.utils.audio import decode_twilio_payload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Media Streams"])


@router.websocket("/ws/media-stream")
async def media_stream_handler(websocket: WebSocket) -> None:
    """
    Handle Twilio bidirectional Media Streams.

    Receives inbound audio, routes to Deepgram STT, processes through
    the agent engine (Groq + validation), and streams TTS back.
    """
    await websocket.accept()

    call_id = websocket.query_params.get("call_id", "")
    settings = get_settings()
    call_service = get_call_service()
    session_manager = get_call_session_manager()
    conversation_service = get_conversation_service()
    analytics_service = get_agent_analytics_service()
    language_manager = get_language_manager()
    agent_manager = get_agent_manager()

    stt: SpeechRecognitionService | None = None
    session = None
    stream_sid = ""

    try:
        async for raw_message in websocket.iter_text():
            message: dict[str, Any] = json.loads(raw_message)
            event = message.get("event")

            if event == "connected":
                logger.debug("Twilio media stream connected")

            elif event == "start":
                stream_sid, session, resolved_call_id = await _handle_start(
                    message=message,
                    call_id=call_id,
                    call_service=call_service,
                    session_manager=session_manager,
                    analytics_service=analytics_service,
                    language_manager=language_manager,
                    agent_manager=agent_manager,
                    websocket=websocket,
                )
                if resolved_call_id:
                    call_id = resolved_call_id
                if not session:
                    break

                conversation_service.preload_emi_for_session(session)

                stt = SpeechRecognitionService(settings)
                session.stt = stt
                from app.services.language_manager import LanguageManager

                stt_language = settings.deepgram_language
                if session.agent_config:
                    supported = getattr(
                        session.agent_config, "supported_languages", None
                    ) or ["en", "hi"]
                    if "hi" in supported and "en" in supported:
                        if LanguageManager.is_india_phone(session.customer_phone):
                            # Hindi-first STT for +91 — better Devanagari on first reply
                            stt_language = "hi"
                        else:
                            stt_language = "multi"

                async def on_final(transcript: str, stt_ms: float) -> None:
                    if not session:
                        return
                    text = transcript.strip()
                    if len(text) < 2:
                        return

                    # Preempt in-flight turn (TTS playback, Groq, etc.) — do not drop speech
                    prior = session.processing_task
                    if prior and not prior.done():
                        prior.cancel()
                        try:
                            await prior
                        except asyncio.CancelledError:
                            pass
                        except Exception as exc:
                            logger.debug(
                                "Prior turn ended with error after cancel: %s", exc
                            )
                    session.is_processing = False
                    session.playback_cancelled = False

                    async def _run_turn() -> None:
                        try:
                            await conversation_service.handle_user_transcript(
                                session, text, stt_ms
                            )
                        finally:
                            if session.processing_task is asyncio.current_task():
                                session.processing_task = None

                    session.processing_task = asyncio.create_task(_run_turn())

                async def on_speech_started() -> None:
                    if session:
                        await conversation_service.handle_speech_started(session)

                # Start speaking immediately; connect STT in parallel (saves ~2–3s)
                greeting_task = asyncio.create_task(
                    conversation_service.play_greeting(session)
                )
                await stt.connect(
                    on_final_transcript=on_final,
                    on_speech_started=on_speech_started,
                    language=stt_language,
                )
                if greeting_task.done() and greeting_task.exception():
                    greeting_task.result()

            elif event == "media" and stt and session:
                track = message.get("media", {}).get("track", "inbound")
                if track and track != "inbound":
                    continue
                payload = message.get("media", {}).get("payload", "")
                if payload:
                    audio = decode_twilio_payload(payload)
                    await stt.send_audio(audio)

            elif event == "stop":
                log_with_context(
                    logger,
                    logging.INFO,
                    "Media stream stopped",
                    call_id=call_id,
                    stream_sid=stream_sid,
                    event="media_stream_stopped",
                )
                break

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected | call_id=%s", call_id)
    except Exception as exc:
        log_with_context(
            logger,
            logging.ERROR,
            f"Media stream error: {exc}",
            call_id=call_id,
            event="media_stream_error",
        )
    finally:
        if stt:
            await stt.close()
        if stream_sid:
            ended_session = session_manager.end_session(stream_sid)
            if ended_session:
                await conversation_service.finalize_session(ended_session)
        try:
            await websocket.close()
        except Exception:
            pass


async def _handle_start(
    message: dict[str, Any],
    call_id: str,
    call_service: Any,
    session_manager: Any,
    analytics_service: Any,
    language_manager: Any,
    agent_manager: Any,
    websocket: WebSocket,
) -> tuple[str, Any, str]:
    """Initialize session on Twilio stream start event."""
    start_data = message.get("start", {})
    stream_sid = start_data.get("streamSid", "")
    call_sid = start_data.get("callSid", "")

    custom = start_data.get("customParameters", {})
    if not call_id:
        call_id = custom.get("call_id", "")

    call = call_service.get_call_by_id(call_id) if call_id else None
    if not call and call_sid:
        call = call_service.get_call_by_twilio_sid(call_sid)
        if call:
            call_id = str(call["_id"])

    if not call_id or not call:
        logger.error(
            "Media stream start missing call_id | call_sid=%s custom=%s",
            call_sid,
            custom,
        )
        return stream_sid, None, ""

    context = call_service.get_call_context(call_id)
    if not context:
        logger.error("Customer not found for call | call_id=%s", call_id)
        return stream_sid, None, call_id

    customer_id = context["customer_id"]
    customer_name = context["customer_name"]
    customer_phone = call.get("phone", "") if call else ""
    agent_id = context.get("agent_id", "")
    agent_config = context.get("agent_config")
    agent_context = context.get("agent_context", {})
    greeting = context.get("greeting", "")

    agent_name = agent_config.agent_name if agent_config else "Unknown Agent"
    if not agent_id and agent_config:
        agent_id = agent_config.agent_id
    try:
        agent_doc = agent_manager.get_agent_document_raw(agent_id) if agent_id else {}
    except Exception:
        agent_doc = {}
    initial_language = (
        language_manager.resolve_initial_language(agent_doc, customer_id)
        if agent_doc
        else "en"
    )

    analytics_id = analytics_service.start_conversation(
        call_id=call_id,
        agent_id=agent_id,
        agent_name=agent_name,
        customer_id=customer_id,
        language=initial_language,
    )

    session = session_manager.create_session(
        call_id=call_id,
        call_sid=call_sid,
        stream_sid=stream_sid,
        customer_id=customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        agent_id=agent_id,
        agent_config=agent_config,
        greeting=greeting,
        agent_context=agent_context,
        analytics_id=analytics_id,
    )
    session.websocket = websocket

    if agent_doc:
        language_manager.initialize_call_session(
            session,
            agent_doc,
            customer_name=customer_name,
            agent_context=agent_context,
        )
        analytics_service.update_call_language(analytics_id, session.active_language)
        from app.services.language_analytics_service import LanguageAnalyticsService

        LanguageAnalyticsService().record_call_language(agent_id, session.active_language)

    log_with_context(
        logger,
        logging.INFO,
        "Media stream started",
        call_id=call_id,
        twilio_call_sid=call_sid,
        stream_sid=stream_sid,
        agent_id=agent_id,
        event="media_stream_started",
    )

    return stream_sid, session, call_id
