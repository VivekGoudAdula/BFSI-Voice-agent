"""FastAPI dependency injection providers."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.repositories.agent_repository import AgentRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.compliance_repository import ComplianceRepository
from app.repositories.handoff_repository import HandoffRepository
from app.agents.loader import AgentLoader
from app.agents.manager import AgentManager
from app.services.agent_analytics_service import AgentAnalyticsService
from app.services.agent_config_service import AgentConfigService
from app.services.audit_service import AuditService
from app.services.banking_service import BankingService
from app.services.callback_service import CallbackService
from app.services.call_analysis_service import CallAnalysisService
from app.services.call_service import CallService
from app.services.call_session_manager import CallSessionManager
from app.services.campaign_queue_service import CampaignQueueService
from app.services.campaign_service import CampaignService
from app.services.compliance_middleware import ComplianceMiddleware
from app.services.compliance_service import ComplianceService
from app.services.escalation_service import EscalationService
from app.services.handoff_analytics_service import HandoffAnalyticsService
from app.services.handoff_service import HandoffService
from app.services.human_handoff_service import HumanHandoffService
from app.services.sentiment_service import SentimentService
from app.repositories.language_repository import LanguageRepository
from app.services.conversation_service import ConversationService
from app.services.language_analytics_service import LanguageAnalyticsService
from app.services.language_detection_service import LanguageDetectionService
from app.services.language_manager import LanguageManager
from app.services.crm_data_service import CRMDataService
from app.services.admin_service import AdminService
from app.services.customer_service import CustomerService
from app.services.elevenlabs_service import ElevenLabsService
from app.services.groq_service import GroqService
from app.services.post_call_service import PostCallService
from app.services.tool_execution_service import ToolExecutionService
from app.services.twilio_service import TwilioService
from app.services.sms_service import SMSService
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
def get_sms_service() -> SMSService:
    return SMSService(get_settings())


@lru_cache
def get_admin_service() -> AdminService:
    return AdminService(
        settings=get_settings(),
        session_manager=get_call_session_manager(),
    )


@lru_cache
def get_customer_service() -> CustomerService:
    return CustomerService()


@lru_cache
def get_groq_service() -> GroqService:
    return GroqService(get_settings())


@lru_cache
def get_compliance_repository() -> ComplianceRepository:
    return ComplianceRepository()


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService(
        repository=get_compliance_repository(),
        settings=get_settings(),
    )


@lru_cache
def get_compliance_middleware() -> ComplianceMiddleware:
    return ComplianceMiddleware(audit_service=get_audit_service())


@lru_cache
def get_compliance_service() -> ComplianceService:
    return ComplianceService(
        repository=get_compliance_repository(),
        crm_data_service=get_crm_data_service(),
    )


@lru_cache
def get_call_session_manager() -> CallSessionManager:
    return CallSessionManager(get_settings(), audit_service=get_audit_service())


@lru_cache
def get_agent_repository() -> AgentRepository:
    return AgentRepository()


@lru_cache
def get_agent_config_service() -> AgentConfigService:
    return AgentConfigService(get_settings())


@lru_cache
def get_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        banking_service=get_banking_service(),
        callback_service=get_callback_service(),
        customer_service=get_customer_service(),
        human_handoff_service=get_human_handoff_service(),
        sms_service=get_sms_service(),
    )


@lru_cache
def get_agent_loader() -> AgentLoader:
    return AgentLoader(tool_registry=get_tool_registry())


@lru_cache
def get_agent_manager() -> AgentManager:
    return AgentManager(
        repository=get_agent_repository(),
        loader=get_agent_loader(),
        tool_registry=get_tool_registry(),
        settings=get_settings(),
    )


@lru_cache
def get_agent_analytics_service() -> AgentAnalyticsService:
    return AgentAnalyticsService()


@lru_cache
def get_language_repository() -> LanguageRepository:
    return LanguageRepository()


@lru_cache
def get_language_detection_service() -> LanguageDetectionService:
    return LanguageDetectionService(get_language_repository())


@lru_cache
def get_language_manager() -> LanguageManager:
    return LanguageManager(
        repository=get_language_repository(),
        detection_service=get_language_detection_service(),
        agent_loader=get_agent_loader(),
    )


@lru_cache
def get_language_analytics_service() -> LanguageAnalyticsService:
    return LanguageAnalyticsService()


@lru_cache
def get_banking_service() -> BankingService:
    return BankingService()


@lru_cache
def get_callback_service() -> CallbackService:
    return CallbackService(audit_service=get_audit_service())


@lru_cache
def get_handoff_repository() -> HandoffRepository:
    return HandoffRepository()


@lru_cache
def get_sentiment_service() -> SentimentService:
    return SentimentService()


@lru_cache
def get_escalation_service() -> EscalationService:
    return EscalationService(sentiment_service=get_sentiment_service())


@lru_cache
def get_human_handoff_service() -> HumanHandoffService:
    return HumanHandoffService(
        repository=get_handoff_repository(),
        twilio_service=get_twilio_service(),
        sentiment_service=get_sentiment_service(),
        audit_service=get_audit_service(),
    )


@lru_cache
def get_handoff_analytics_service() -> HandoffAnalyticsService:
    return HandoffAnalyticsService(repository=get_handoff_repository())


@lru_cache
def get_handoff_service() -> HandoffService:
    return HandoffService(
        repository=get_handoff_repository(),
        analytics_service=get_handoff_analytics_service(),
    )


@lru_cache
def get_tool_execution_service() -> ToolExecutionService:
    return ToolExecutionService(
        registry=get_tool_registry(),
        audit_service=get_audit_service(),
    )


@lru_cache
def get_crm_data_service() -> CRMDataService:
    return CRMDataService(audit_service=get_audit_service())


@lru_cache
def get_call_analysis_service() -> CallAnalysisService:
    return CallAnalysisService(get_settings(), get_groq_service())


@lru_cache
def get_campaign_repository() -> CampaignRepository:
    return CampaignRepository()


@lru_cache
def get_campaign_queue_service() -> CampaignQueueService:
    return CampaignQueueService(
        repository=get_campaign_repository(),
        settings=get_settings(),
        call_service_factory=get_call_service,
        customer_service=get_customer_service(),
    )


@lru_cache
def get_campaign_service() -> CampaignService:
    service = CampaignService(
        repository=get_campaign_repository(),
        settings=get_settings(),
        agent_manager=get_agent_manager(),
    )
    service.set_queue_service(get_campaign_queue_service())
    return service


@lru_cache
def get_post_call_service() -> PostCallService:
    service = PostCallService(
        settings=get_settings(),
        analytics_service=get_agent_analytics_service(),
        call_analysis_service=get_call_analysis_service(),
        crm_data_service=get_crm_data_service(),
        customer_service=get_customer_service(),
        tool_execution_service=get_tool_execution_service(),
        callback_service=get_callback_service(),
        audit_service=get_audit_service(),
    )
    service.set_campaign_queue_service(get_campaign_queue_service())
    return service


def get_conversation_service() -> ConversationService:
    return ConversationService(
        session_manager=get_call_session_manager(),
        groq_service=get_groq_service(),
        elevenlabs_service=get_elevenlabs_service(),
        agent_config_service=get_agent_config_service(),
        agent_manager=get_agent_manager(),
        agent_analytics_service=get_agent_analytics_service(),
        tool_registry=get_tool_registry(),
        tool_execution_service=get_tool_execution_service(),
        post_call_service=get_post_call_service(),
        language_manager=get_language_manager(),
        compliance_middleware=get_compliance_middleware(),
    )


def get_call_service() -> CallService:
    return CallService(
        customer_service=get_customer_service(),
        elevenlabs_service=get_elevenlabs_service(),
        twilio_service=get_twilio_service(),
        session_manager=get_call_session_manager(),
        agent_config_service=get_agent_config_service(),
        agent_manager=get_agent_manager(),
    )
