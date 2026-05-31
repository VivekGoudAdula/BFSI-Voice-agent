"""FastAPI dependency injection providers."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.agent_config_service import AgentConfigService
from app.services.banking_service import BankingService
from app.services.callback_service import CallbackService
from app.services.call_service import CallService
from app.services.call_session_manager import CallSessionManager
from app.services.conversation_service import ConversationService
from app.services.customer_service import CustomerService
from app.services.elevenlabs_service import ElevenLabsService
from app.services.groq_service import GroqService
from app.services.tool_execution_service import ToolExecutionService
from app.services.twilio_service import TwilioService
from app.tools.registry import ToolRegistry


def settings_dep() -> Settings:
    return get_settings()


@lru_cache
def get_elevenlabs_service() -> ElevenLabsService:
    return ElevenLabsService(get_settings())


@lru_cache
def get_twilio_service() -> TwilioService:
    return TwilioService(get_settings())


@lru_cache
def get_customer_service() -> CustomerService:
    return CustomerService()


@lru_cache
def get_groq_service() -> GroqService:
    return GroqService(get_settings())


@lru_cache
def get_call_session_manager() -> CallSessionManager:
    return CallSessionManager(get_settings())


@lru_cache
def get_agent_config_service() -> AgentConfigService:
    return AgentConfigService(get_settings())


@lru_cache
def get_agent_analytics_service() -> AgentAnalyticsService:
    return AgentAnalyticsService()


@lru_cache
def get_banking_service() -> BankingService:
    return BankingService()


@lru_cache
def get_callback_service() -> CallbackService:
    return CallbackService()


@lru_cache
def get_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        banking_service=get_banking_service(),
        callback_service=get_callback_service(),
        customer_service=get_customer_service(),
    )


@lru_cache
def get_tool_execution_service() -> ToolExecutionService:
    return ToolExecutionService(registry=get_tool_registry())


def get_conversation_service() -> ConversationService:
    return ConversationService(
        session_manager=get_call_session_manager(),
        groq_service=get_groq_service(),
        elevenlabs_service=get_elevenlabs_service(),
        agent_config_service=get_agent_config_service(),
        agent_analytics_service=get_agent_analytics_service(),
        tool_registry=get_tool_registry(),
        tool_execution_service=get_tool_execution_service(),
    )


def get_call_service() -> CallService:
    return CallService(
        customer_service=get_customer_service(),
        elevenlabs_service=get_elevenlabs_service(),
        twilio_service=get_twilio_service(),
        session_manager=get_call_session_manager(),
        agent_config_service=get_agent_config_service(),
    )
