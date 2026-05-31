"""Call management endpoints."""

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_call_service
from app.models.call import CallInitiateRequest, CallResponse
from app.models.conversation import ConversationSessionResponse, TranscriptResponse
from app.services.call_service import CallService

router = APIRouter(prefix="/calls", tags=["Calls"])


@router.post(
    "/initiate",
    response_model=CallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate outbound call",
    description=(
        "Fetch customer, place Twilio conversational call with Media Streams, "
        "and persist call record."
    ),
)
async def initiate_call(
    payload: CallInitiateRequest,
    service: CallService = Depends(get_call_service),
) -> CallResponse:
    return await service.initiate_call(
        customer_id=payload.customer_id,
        agent_id=payload.agent_id,
        agent_context=payload.agent_context,
    )


@router.get(
    "",
    response_model=list[CallResponse],
    summary="List call logs",
    description="Retrieve all call records ordered by creation date.",
)
def get_calls(
    service: CallService = Depends(get_call_service),
) -> list[CallResponse]:
    return service.get_calls()


@router.get(
    "/{call_id}/transcript",
    response_model=TranscriptResponse,
    summary="Get call transcript",
    description="Returns the full transcript of user and assistant utterances.",
)
def get_call_transcript(
    call_id: str,
    service: CallService = Depends(get_call_service),
) -> TranscriptResponse:
    return service.get_transcript(call_id)


@router.get(
    "/{call_id}/conversation",
    response_model=ConversationSessionResponse,
    summary="Get conversation history",
    description="Returns the full conversation session including system messages.",
)
def get_call_conversation(
    call_id: str,
    service: CallService = Depends(get_call_service),
) -> ConversationSessionResponse:
    return service.get_conversation(call_id)
