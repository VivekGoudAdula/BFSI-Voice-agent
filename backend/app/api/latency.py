"""Latency diagnostics endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/latency", tags=["Latency"])


@router.get("/health")
def latency_health() -> dict[str, str]:
    """Simple health probe for latency subsystem."""
    return {"status": "ok"}
