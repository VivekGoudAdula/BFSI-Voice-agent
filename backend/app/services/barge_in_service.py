"""Realtime barge-in orchestration for Twilio Media Streams."""

import json
import logging

from app.core.logging_config import log_with_context
from app.services.call_session_manager import ActiveCallSession, CallSessionManager
from app.services.turn_manager import TurnManager

logger = logging.getLogger(__name__)


class BargeInService:
    """Detect and handle customer interruption while AI is speaking/processing."""

    def __init__(
        self,
        session_manager: CallSessionManager,
        turn_manager: TurnManager | None = None,
    ) -> None:
        self._sessions = session_manager
        self._turns = turn_manager or TurnManager()

    async def handle_interrupt(self, session: ActiveCallSession) -> None:
        self._turns.mark_interruption(session)
        session.is_processing = False
        await self._sessions.cancel_playback(session)
        await self._send_clear(session)
        await self._cancel_processing(session)
        log_with_context(
            logger,
            logging.INFO,
            "Barge-in handled",
            call_id=session.call_id,
            interruptions_handled=session.interruption_count,
            event="barge_in_handled",
        )

    async def _send_clear(self, session: ActiveCallSession) -> None:
        if not session.websocket:
            return
        message = {"event": "clear", "streamSid": session.stream_sid}
        try:
            await session.websocket.send_text(json.dumps(message))
        except Exception as exc:
            logger.warning("Failed to send clear event: %s", exc)

    async def _cancel_processing(self, session: ActiveCallSession) -> None:
        task = session.processing_task
        if not task or task.done():
            return
        task.cancel()
        try:
            await task
        except Exception:
            pass
        finally:
            session.processing_task = None
