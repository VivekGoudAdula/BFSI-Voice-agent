"""ElevenLabs utility endpoints."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_elevenlabs_service
from app.services.elevenlabs_service import ElevenLabsService

router = APIRouter(prefix="/elevenlabs", tags=["ElevenLabs"])


@router.get(
    "/voices",
    summary="List ElevenLabs voices",
    description=(
        "Lists voices on your ElevenLabs account. "
        "Free-tier API users must use voices where api_usable_on_free is true "
        "(premade defaults or your own cloned/generated voices)."
    ),
)
async def list_voices(
    service: ElevenLabsService = Depends(get_elevenlabs_service),
) -> list[dict]:
    return await service.list_voices()
