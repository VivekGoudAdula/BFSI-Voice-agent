"""Twilio webhook endpoints for call flow and status updates."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.core.dependencies import get_call_service, get_call_session_manager, get_conversation_service, get_post_call_service, get_twilio_service
from app.services.call_service import CallService
from app.services.twilio_service import TwilioService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/twilio", tags=["Twilio Webhooks"])


@router.get(
    "/voice/{call_id}",
    summary="Twilio voice webhook",
    description="Returns TwiML to connect the call to a bidirectional Media Stream.",
    response_class=Response,
)
def twilio_voice_webhook(
    call_id: str,
    call_service: CallService = Depends(get_call_service),
    twilio_service: TwilioService = Depends(get_twilio_service),
) -> Response:
    call = call_service.get_call_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    stream_url = twilio_service.build_media_stream_url()
    twiml = twilio_service.generate_media_stream_twiml(stream_url, call_id)

    return Response(content=twiml, media_type="application/xml")


@router.get(
    "/play/{audio_filename}",
    summary="Audio playback URL for Twilio",
    description="Serves generated MP3 files for Twilio <Play> verb.",
)
def serve_audio(
    audio_filename: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    # Prevent path traversal
    if ".." in audio_filename or "/" in audio_filename or "\\" in audio_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = settings.audio_dir / audio_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    content = file_path.read_bytes()
    return Response(content=content, media_type="audio/mpeg")


@router.post(
    "/status/{call_id}",
    summary="Twilio status callback",
    description="Receives call lifecycle events from Twilio and updates call status.",
)
async def twilio_status_callback(
    call_id: str,
    request: Request,
    call_service: CallService = Depends(get_call_service),
    session_manager=Depends(get_call_session_manager),
    post_call_service=Depends(get_post_call_service),
) -> dict[str, str]:
    form = await request.form()
    call_status = form.get("CallStatus", "unknown")
    call_sid = str(form.get("CallSid", ""))

    status_map = {
        "queued": "queued",
        "initiated": "initiated",
        "ringing": "ringing",
        "in-progress": "in-progress",
        "completed": "completed",
        "busy": "busy",
        "failed": "failed",
        "no-answer": "no-answer",
        "canceled": "canceled",
    }

    mapped = status_map.get(str(call_status), str(call_status))
    call_service.update_call_status(call_id, mapped)

    if mapped == "completed" and call_sid:
        session = session_manager.get_session_by_call_sid(call_sid)
        if session:
            ended_session = session_manager.end_session(session.stream_sid)
            if ended_session:
                await post_call_service.process_call_end(ended_session)

    logger.info(
        "Twilio status callback | call_id=%s status=%s",
        call_id,
        mapped,
    )

    return {"status": "received"}
