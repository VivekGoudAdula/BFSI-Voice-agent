"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import agents, calls, campaigns, crm, customers, elevenlabs, handoff, media_stream, tools, webhooks
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import setup_logging
from app.core.dependencies import get_agent_config_service
from app.database.mongodb import MongoDB

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    setup_logging()
    settings = get_settings()
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    MongoDB.connect(settings)
    get_agent_config_service().seed_default_agents()
    logger.info("AI Voice Agent Platform started | base_url=%s", settings.base_url)
    yield
    MongoDB.disconnect()
    logger.info("AI Voice Agent Platform shut down")


app = FastAPI(
    title="AI Voice Agent Platform",
    description=(
        "Production-grade outbound voice platform for Banking and Financial Services. "
        "Phase 7: Human handoff with escalation engine and transfer queue."
    ),
    version="7.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers.router)
app.include_router(calls.router)
app.include_router(campaigns.router)
app.include_router(handoff.router_escalations)
app.include_router(handoff.router_queue)
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(crm.router)
app.include_router(elevenlabs.router)
app.include_router(webhooks.router)
app.include_router(media_stream.router)


@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["Health"], summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "ai-voice-agent-platform"}
