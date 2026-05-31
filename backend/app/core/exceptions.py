"""Application-specific exceptions mapped to HTTP responses."""

from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base exception with HTTP status and detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


class CustomerNotFoundError(AppException):
    def __init__(self, customer_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer not found: {customer_id}",
        )


class InvalidPhoneNumberError(AppException):
    def __init__(self, phone: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid phone number format: {phone}. Use E.164 format (e.g. +919876543210).",
        )


class ElevenLabsServiceError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ElevenLabs API error: {message}",
        )


class TwilioServiceError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Twilio API error: {message}",
        )


class DatabaseError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database error: {message}",
        )


class GroqServiceError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq API error: {message}",
        )


class SpeechRecognitionError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Speech recognition error: {message}",
        )


class CallNotFoundError(AppException):
    def __init__(self, call_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call not found: {call_id}",
        )


class ConversationNotFoundError(AppException):
    def __init__(self, call_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found for call: {call_id}",
        )


class AgentNotFoundError(AppException):
    def __init__(self, agent_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found: {agent_id}",
        )
class CRMRecordNotFoundError(AppException):
    def __init__(self, call_id: str, record_type: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{record_type} not found for call: {call_id}",
        )


class CampaignNotFoundError(AppException):
    def __init__(self, campaign_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign not found: {campaign_id}",
        )


class CampaignStateError(AppException):
    def __init__(self, campaign_id: str, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Campaign {campaign_id}: {message}",
        )
