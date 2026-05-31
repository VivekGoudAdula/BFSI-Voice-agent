"""Campaign management API endpoints."""

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import get_campaign_service
from app.models.campaign import (
    CSVImportResult,
    CampaignAnalyticsResponse,
    CampaignCreateRequest,
    CampaignCustomerResponse,
    CampaignResponse,
    CampaignResultItem,
    CampaignStartResponse,
)
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post(
    "/upload",
    response_model=CSVImportResult,
    summary="Upload campaign customer CSV",
    description="Import customers from CSV (Name, Phone, LoanID) into a campaign.",
)
async def upload_campaign_csv(
    file: UploadFile = File(..., description="CSV file with Name, Phone, LoanID columns"),
    campaign_id: str = Form(..., description="Target campaign ID"),
    service: CampaignService = Depends(get_campaign_service),
) -> CSVImportResult:
    content = await file.read()
    return service.import_csv(campaign_id, content)


@router.post(
    "/create",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new campaign",
)
def create_campaign(
    payload: CampaignCreateRequest,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    return service.create_campaign(payload)


@router.get(
    "",
    response_model=list[CampaignResponse],
    summary="List all campaigns",
)
def list_campaigns(
    service: CampaignService = Depends(get_campaign_service),
) -> list[CampaignResponse]:
    return service.list_campaigns()


@router.get(
    "/{campaign_id}",
    response_model=CampaignResponse,
    summary="Get campaign details",
)
def get_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    return service.get_campaign(campaign_id)


@router.post(
    "/{campaign_id}/start",
    response_model=CampaignStartResponse,
    summary="Start campaign outbound calling",
)
async def start_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignStartResponse:
    return await service.start_campaign(campaign_id)


@router.post(
    "/{campaign_id}/pause",
    response_model=CampaignResponse,
    summary="Pause a running campaign",
)
async def pause_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    return await service.pause_campaign(campaign_id)


@router.post(
    "/{campaign_id}/resume",
    response_model=CampaignStartResponse,
    summary="Resume a paused campaign",
)
async def resume_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignStartResponse:
    return await service.resume_campaign(campaign_id)


@router.post(
    "/{campaign_id}/stop",
    response_model=CampaignResponse,
    summary="Stop a campaign",
)
async def stop_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignResponse:
    return await service.stop_campaign(campaign_id)


@router.get(
    "/{campaign_id}/analytics",
    response_model=CampaignAnalyticsResponse,
    summary="Get campaign analytics",
)
def get_campaign_analytics(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignAnalyticsResponse:
    return service.get_analytics(campaign_id)


@router.get(
    "/{campaign_id}/customers",
    response_model=list[CampaignCustomerResponse],
    summary="List campaign customers",
)
def get_campaign_customers(
    campaign_id: str,
    skip: int = 0,
    limit: int = 100,
    service: CampaignService = Depends(get_campaign_service),
) -> list[CampaignCustomerResponse]:
    return service.get_customers(campaign_id, skip=skip, limit=limit)


@router.get(
    "/{campaign_id}/results",
    response_model=list[CampaignResultItem],
    summary="Get campaign call results",
)
def get_campaign_results(
    campaign_id: str,
    skip: int = 0,
    limit: int = 100,
    service: CampaignService = Depends(get_campaign_service),
) -> list[CampaignResultItem]:
    return service.get_results(campaign_id, skip=skip, limit=limit)
