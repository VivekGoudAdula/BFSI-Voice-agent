"""Agent configuration and analytics endpoints."""

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_agent_analytics_service, get_agent_config_service
from app.core.exceptions import AgentNotFoundError
from app.models.agent import (
    AgentConfig,
    AgentConfigCreate,
    AnalyticsSummary,
    ConversationAnalytics,
)
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.agent_config_service import AgentConfigService

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get(
    "",
    response_model=list[AgentConfig],
    summary="List all agent configurations",
)
def list_agents(
    service: AgentConfigService = Depends(get_agent_config_service),
) -> list[AgentConfig]:
    return service.list_agents()


@router.get(
    "/default",
    response_model=AgentConfig,
    summary="Get the default active agent",
)
def get_default_agent(
    service: AgentConfigService = Depends(get_agent_config_service),
) -> AgentConfig:
    agent = service.get_default_agent()
    if not agent:
        raise AgentNotFoundError("default")
    return agent


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
    response_model=AgentConfig,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent configuration",
)
def create_agent(
    payload: AgentConfigCreate,
    service: AgentConfigService = Depends(get_agent_config_service),
) -> AgentConfig:
    return service.create_agent(payload)


@router.get(
    "/{agent_id}",
    response_model=AgentConfig,
    summary="Get agent configuration by ID",
)
def get_agent(
    agent_id: str,
    service: AgentConfigService = Depends(get_agent_config_service),
) -> AgentConfig:
    agent = service.get_agent_by_id(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    return agent


@router.put(
    "/{agent_id}",
    response_model=AgentConfig,
    summary="Update an agent configuration (increments version)",
)
def update_agent(
    agent_id: str,
    payload: AgentConfigCreate,
    service: AgentConfigService = Depends(get_agent_config_service),
) -> AgentConfig:
    agent = service.update_agent(agent_id, payload)
    if not agent:
        raise AgentNotFoundError(agent_id)
    return agent
