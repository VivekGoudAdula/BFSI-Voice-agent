"""Agent configuration and analytics endpoints."""

from fastapi import APIRouter, Depends, status

from app.config.languages import SUPPORTED_LANGUAGES
from app.core.dependencies import (
    get_agent_analytics_service,
    get_agent_manager,
    get_language_analytics_service,
    get_language_manager,
)
from app.core.exceptions import AgentNotFoundError
from app.models.agent import (
    AgentAnalyticsRecord,
    AgentCreateRequest,
    AgentDocument,
    AgentUpdateRequest,
    AnalyticsSummary,
    ConversationAnalytics,
)
from app.models.language import (
    AgentLanguagesResponse,
    AgentLanguagesUpdateRequest,
    LanguageAnalyticsSummary,
)
from app.services.agent_analytics_service import AgentAnalyticsService
from app.agents.manager import AgentManager

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get(
    "",
    response_model=list[AgentDocument],
    summary="List all agent configurations",
)
def list_agents(
    manager: AgentManager = Depends(get_agent_manager),
) -> list[AgentDocument]:
    return manager.list_agents()


@router.get(
    "/languages",
    summary="List supported agent languages",
)
def list_supported_languages() -> dict[str, str]:
    return SUPPORTED_LANGUAGES


@router.get(
    "/default",
    response_model=AgentDocument,
    summary="Get the default active agent",
)
def get_default_agent(
    manager: AgentManager = Depends(get_agent_manager),
) -> AgentDocument:
    runtime = manager.get_default_agent()
    return manager.get_agent(runtime.agent_id)


@router.get(
    "/analytics/languages",
    response_model=LanguageAnalyticsSummary,
    summary="Get multilingual call analytics",
)
def get_language_analytics(
    agent_id: str | None = None,
    service=Depends(get_language_analytics_service),
) -> LanguageAnalyticsSummary:
    return service.get_summary(agent_id=agent_id)


@router.get(
    "/analytics/summary",
    response_model=AnalyticsSummary,
    summary="Get aggregated conversation analytics",
)
def get_analytics_summary(
    service: AgentAnalyticsService = Depends(get_agent_analytics_service),
) -> AnalyticsSummary:
    return service.get_summary()


@router.get(
    "/analytics/agent/{agent_id}",
    response_model=AgentAnalyticsRecord,
    summary="Get per-agent aggregated analytics",
)
def get_agent_analytics(
    agent_id: str,
    service: AgentAnalyticsService = Depends(get_agent_analytics_service),
) -> AgentAnalyticsRecord:
    record = service.get_agent_analytics(agent_id)
    if not record:
        raise AgentNotFoundError(f"analytics:{agent_id}")
    return record


@router.get(
    "/analytics/call/{call_id}",
    response_model=ConversationAnalytics,
    summary="Get analytics for a specific call",
)
def get_call_analytics(
    call_id: str,
    service: AgentAnalyticsService = Depends(get_agent_analytics_service),
) -> ConversationAnalytics:
    analytics = service.get_by_call_id(call_id)
    if not analytics:
        raise AgentNotFoundError(f"analytics:{call_id}")
    return analytics


@router.post(
    "",
    response_model=AgentDocument,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent configuration",
)
def create_agent(
    payload: AgentCreateRequest,
    manager: AgentManager = Depends(get_agent_manager),
) -> AgentDocument:
    return manager.register(payload)


@router.get(
    "/{agent_id}/languages",
    response_model=AgentLanguagesResponse,
    summary="Get agent multilingual configuration",
)
def get_agent_languages(
    agent_id: str,
    manager: AgentManager = Depends(get_agent_manager),
    language_manager=Depends(get_language_manager),
) -> AgentLanguagesResponse:
    doc = manager.get_agent_document_raw(agent_id)
    data = language_manager.get_agent_languages_response(doc)
    return AgentLanguagesResponse(**data)


@router.post(
    "/{agent_id}/languages",
    response_model=AgentLanguagesResponse,
    summary="Configure agent languages, voices, and prompt translations",
)
def configure_agent_languages(
    agent_id: str,
    payload: AgentLanguagesUpdateRequest,
    manager: AgentManager = Depends(get_agent_manager),
    language_manager=Depends(get_language_manager),
) -> AgentLanguagesResponse:
    manager.update_agent_languages(
        agent_id,
        supported_languages=payload.supported_languages,
        default_language=payload.default_language,
        voice_configs=[vc.model_dump() for vc in payload.voice_configs],
    )
    if payload.prompt_translations:
        from app.repositories.language_repository import LanguageRepository

        LanguageRepository().upsert_prompt_translations(
            manager.get_agent(agent_id).agent_id,
            payload.prompt_translations,
        )
    doc = manager.get_agent_document_raw(agent_id)
    data = language_manager.get_agent_languages_response(doc)
    return AgentLanguagesResponse(**data)


@router.get(
    "/{agent_id}",
    response_model=AgentDocument,
    summary="Get agent configuration by ID or slug",
)
def get_agent(
    agent_id: str,
    manager: AgentManager = Depends(get_agent_manager),
) -> AgentDocument:
    return manager.get_agent(agent_id)


@router.put(
    "/{agent_id}",
    response_model=AgentDocument,
    summary="Update an agent configuration (increments version)",
)
def update_agent(
    agent_id: str,
    payload: AgentUpdateRequest,
    manager: AgentManager = Depends(get_agent_manager),
) -> AgentDocument:
    return manager.update_agent(agent_id, payload)


@router.delete(
    "/{agent_id}",
    response_model=AgentDocument,
    summary="Deactivate an agent",
)
def deactivate_agent(
    agent_id: str,
    manager: AgentManager = Depends(get_agent_manager),
) -> AgentDocument:
    return manager.deactivate_agent(agent_id)


@router.post(
    "/{agent_id}/activate",
    response_model=AgentDocument,
    summary="Reactivate a deactivated agent",
)
def activate_agent(
    agent_id: str,
    manager: AgentManager = Depends(get_agent_manager),
) -> AgentDocument:
    return manager.activate_agent(agent_id)
