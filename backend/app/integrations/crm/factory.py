"""CRM provider factory."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.crm.base import CRMProvider
from app.integrations.crm.leadsquared import LeadSquaredCRMProvider
from app.integrations.crm.salesforce import SalesforceCRMProvider
from app.integrations.crm.zoho import ZohoCRMProvider
from app.models.crm import CRMProviderType


def create_crm_provider(settings: Settings | None = None) -> CRMProvider:
    """Instantiate the configured CRM provider."""
    settings = settings or get_settings()
    provider = settings.crm_provider.lower()

    providers: dict[str, type[CRMProvider]] = {
        CRMProviderType.SALESFORCE.value: SalesforceCRMProvider,
        CRMProviderType.ZOHO.value: ZohoCRMProvider,
        CRMProviderType.LEADSQUARED.value: LeadSquaredCRMProvider,
    }

    provider_class = providers.get(provider)
    if not provider_class:
        raise ValueError(f"Unsupported CRM provider: {provider}")

    return provider_class(settings)


@lru_cache
def get_crm_provider() -> CRMProvider:
    """Cached CRM provider instance."""
    return create_crm_provider(get_settings())
