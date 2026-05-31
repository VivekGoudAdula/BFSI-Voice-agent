"""Admin portal API endpoints."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_admin_service
from app.models.admin import (
    ActiveCallResponse,
    DashboardSummary,
    PlatformSettingsResponse,
    PlatformSettingsUpdate,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


@router.get(
    "/dashboard",
    response_model=DashboardSummary,
    summary="Unified admin dashboard metrics",
)
def get_dashboard(
    service: AdminService = Depends(get_admin_service),
) -> DashboardSummary:
    return service.get_dashboard_summary()


@router.get(
    "/settings",
    response_model=PlatformSettingsResponse,
    summary="Get platform settings",
)
def get_settings(
    service: AdminService = Depends(get_admin_service),
) -> PlatformSettingsResponse:
    return service.get_settings()


@router.put(
    "/settings",
    response_model=PlatformSettingsResponse,
    summary="Update mutable platform settings",
)
def update_settings(
    payload: PlatformSettingsUpdate,
    service: AdminService = Depends(get_admin_service),
) -> PlatformSettingsResponse:
    return service.update_settings(payload)
