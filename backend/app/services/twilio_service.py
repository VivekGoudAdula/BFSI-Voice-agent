"""Twilio Voice API integration."""

import logging

from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from app.core.config import Settings
from app.core.exceptions import TwilioServiceError
from app.core.logging_config import log_with_context

logger = logging.getLogger(__name__)


class TwilioService:
    """Places outbound calls and provides TwiML for audio playback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._from_number = settings.twilio_phone_number
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            if not self._settings.twilio_account_sid or not self._settings.twilio_auth_token:
                raise TwilioServiceError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured")
            self._client = Client(
                self._settings.twilio_account_sid,
                self._settings.twilio_auth_token,
            )
        return self._client

    def build_twiml_play_url(self, audio_filename: str) -> str:
        """Public URL Twilio will fetch to play generated audio."""
        base = self._settings.base_url.rstrip("/")
        return f"{base}/webhooks/twilio/play/{audio_filename}"

    def build_status_callback_url(self, call_id: str) -> str:
        """Webhook URL for Twilio call status updates."""
        base = self._settings.base_url.rstrip("/")
        return f"{base}/webhooks/twilio/status/{call_id}"

    def place_call(self, to_phone: str, twiml_url: str, status_callback_url: str) -> str:
        """
        Initiate an outbound call via Twilio.

        Returns:
            Twilio Call SID.
        """
        if not self._from_number:
            raise TwilioServiceError("TWILIO_PHONE_NUMBER must be configured")

        log_with_context(
            logger,
            logging.INFO,
            "Placing outbound call via Twilio",
            phone=to_phone,
            event="call_initiation_started",
        )

        try:
            call = self.client.calls.create(
                to=to_phone,
                from_=self._from_number,
                url=twiml_url,
                method="GET",
                status_callback=status_callback_url,
                status_callback_method="POST",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
            )
        except TwilioException as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Twilio call failed: {exc}",
                phone=to_phone,
                event="call_initiation_failed",
            )
            raise TwilioServiceError(str(exc)) from exc

        log_with_context(
            logger,
            logging.INFO,
            "Twilio call created",
            phone=to_phone,
            twilio_call_sid=call.sid,
            event="twilio_response_received",
        )

        return call.sid

    @staticmethod
    def generate_play_twiml(audio_url: str) -> str:
        """TwiML instructing Twilio to play the generated audio file."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
</Response>"""

    def build_media_stream_url(self) -> str:
        """WebSocket URL for Twilio bidirectional Media Streams."""
        base = self._settings.websocket_base_url.rstrip("/")
        return f"{base}/ws/media-stream"

    def mock_transfer_call(
        self,
        call_sid: str,
        destination: str = "",
        category: str = "",
    ) -> dict[str, str | bool]:
        """
        Mock live call transfer for Phase 7.

        Future: Twilio calls.update(url=...) with <Dial> TwiML, SIP transfer,
        or contact-center queue integration.
        """
        dest = destination or self._settings.human_agent_phone or "human-agent-queue"
        log_with_context(
            logger,
            logging.INFO,
            "Mock call transfer initiated",
            twilio_call_sid=call_sid,
            destination=dest,
            category=category,
            event="mock_transfer",
        )
        return {
            "transferred": True,
            "mode": "mock",
            "call_sid": call_sid,
            "destination": dest,
        }

    def build_transfer_twiml(self, destination: str) -> str:
        """
        TwiML for live transfer — ready for Phase 7+ Twilio integration.

        Usage: update active call URL to webhook returning this TwiML.
        """
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Please hold while we connect you to a banking representative.</Say>
    <Dial>{destination}</Dial>
</Response>"""

    @staticmethod
    def generate_media_stream_twiml(stream_url: str, call_id: str) -> str:
        """
        TwiML that connects the call to a bidirectional Media Stream.

        call_id is passed as a Stream Parameter because Twilio does not
        forward query strings on the WebSocket URL.
        """
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}">
            <Parameter name="call_id" value="{call_id}"/>
            <Parameter name="mode" value="conversational"/>
        </Stream>
    </Connect>
</Response>"""
