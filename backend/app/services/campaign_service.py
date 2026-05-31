"""Campaign management: CSV import, lifecycle, and progress tracking."""

import csv
import io
import logging
from typing import TYPE_CHECKING, Any, Optional

from app.core.config import Settings
from app.core.exceptions import CampaignNotFoundError, CampaignStateError
from app.core.logging_config import log_with_context
from app.models.campaign import (
    CSVImportResult,
    CampaignAnalyticsResponse,
    CampaignCreateRequest,
    CampaignCustomerResponse,
    CampaignResponse,
    CampaignResultItem,
    CampaignStartResponse,
    CampaignStatus,
)
from app.models.customer import CustomerCreate
from app.repositories.campaign_repository import CampaignRepository
from app.utils.mongo_query import find_sorted

if TYPE_CHECKING:
    from app.services.campaign_queue_service import CampaignQueueService
    from app.agents.manager import AgentManager

logger = logging.getLogger(__name__)

REQUIRED_CSV_COLUMNS = {"name", "phone", "loanid"}


class CampaignService:
    """Orchestrates campaign creation, CSV import, and lifecycle control."""

    def __init__(
        self,
        repository: CampaignRepository,
        settings: Settings,
        queue_service: Optional["CampaignQueueService"] = None,
        agent_manager: Optional["AgentManager"] = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._queue = queue_service
        self._agent_manager = agent_manager

    def set_queue_service(self, queue_service: "CampaignQueueService") -> None:
        """Late-bind queue service to avoid circular imports."""
        self._queue = queue_service

    def set_agent_manager(self, agent_manager: "AgentManager") -> None:
        self._agent_manager = agent_manager

    def create_campaign(self, data: CampaignCreateRequest) -> CampaignResponse:
        campaign_id = self._repo.create_campaign(
            data.name, data.description, data.agent_id
        )
        doc = self._repo.get_campaign(campaign_id)
        if not doc:
            raise CampaignNotFoundError(campaign_id)

        if self._agent_manager:
            self._agent_manager.map_campaign_agent(campaign_id, data.agent_id)

        log_with_context(
            logger,
            logging.INFO,
            "Campaign created",
            campaign_id=campaign_id,
            name=data.name,
            event="campaign_created",
        )
        return self._repo.serialize_campaign(doc)

    def import_csv(
        self, campaign_id: str, file_content: bytes
    ) -> CSVImportResult:
        self._require_campaign(campaign_id)

        text = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            return CSVImportResult(
                total_rows=0, imported=0, failed=0, errors=["Empty CSV file"]
            )

        headers = {h.strip().lower() for h in reader.fieldnames}
        if not REQUIRED_CSV_COLUMNS.issubset(headers):
            missing = REQUIRED_CSV_COLUMNS - headers
            return CSVImportResult(
                total_rows=0,
                imported=0,
                failed=0,
                errors=[f"Missing required columns: {', '.join(sorted(missing))}"],
            )

        valid_customers: list[dict[str, Any]] = []
        errors: list[str] = []
        total_rows = 0

        for row_num, row in enumerate(reader, start=2):
            total_rows += 1
            name = self._get_field(row, "name")
            phone_raw = self._get_field(row, "phone")
            loan_id = self._get_field(row, "loanid")

            if not name:
                errors.append(f"Row {row_num}: missing Name")
                continue
            if not phone_raw:
                errors.append(f"Row {row_num}: missing Phone")
                continue
            if not loan_id:
                errors.append(f"Row {row_num}: missing LoanID")
                continue

            try:
                phone = validate_phone(phone_raw)
            except Exception:
                errors.append(f"Row {row_num}: invalid phone '{phone_raw}'")
                continue

            valid_customers.append(
                {
                    "customer_name": name.strip(),
                    "phone": phone,
                    "loan_id": loan_id.strip(),
                }
            )

        imported = self._repo.insert_campaign_customers(campaign_id, valid_customers)
        total = self._repo.count_campaign_customers(campaign_id)
        self._repo.init_analytics(campaign_id, total)

        log_with_context(
            logger,
            logging.INFO,
            "CSV import completed",
            campaign_id=campaign_id,
            total_rows=total_rows,
            imported=imported,
            failed=len(errors),
            event="campaign_csv_imported",
        )

        return CSVImportResult(
            total_rows=total_rows,
            imported=imported,
            failed=len(errors),
            errors=errors[:50],
        )

    async def start_campaign(self, campaign_id: str) -> CampaignStartResponse:
        campaign = self._require_campaign(campaign_id)
        status = CampaignStatus(campaign["status"])

        if status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED, CampaignStatus.STOPPED):
            raise CampaignStateError(
                campaign_id, f"Cannot start campaign in '{status.value}' status"
            )

        customer_count = self._repo.count_campaign_customers(campaign_id)
        if customer_count == 0:
            raise CampaignStateError(
                campaign_id, "Campaign has no customers. Upload a CSV first."
            )

        from datetime import datetime, timezone

        self._repo.update_campaign_status(
            campaign_id,
            CampaignStatus.RUNNING,
            started_at=campaign.get("started_at") or datetime.now(timezone.utc),
        )
        run_id = self._repo.create_run(campaign_id)
        self._repo.init_analytics(campaign_id, customer_count)

        if self._queue:
            await self._queue.start_campaign(campaign_id, run_id)

        log_with_context(
            logger,
            logging.INFO,
            "Campaign started",
            campaign_id=campaign_id,
            run_id=run_id,
            customers=customer_count,
            event="campaign_started",
        )

        return CampaignStartResponse(
            campaign_id=campaign_id,
            run_id=run_id,
            status=CampaignStatus.RUNNING,
            message=f"Campaign started with {customer_count} customers",
        )

    async def pause_campaign(self, campaign_id: str) -> CampaignResponse:
        campaign = self._require_campaign(campaign_id)
        if CampaignStatus(campaign["status"]) != CampaignStatus.RUNNING:
            raise CampaignStateError(campaign_id, "Campaign is not running")

        self._repo.update_campaign_status(campaign_id, CampaignStatus.PAUSED)
        if self._queue:
            await self._queue.pause_campaign(campaign_id)

        doc = self._repo.get_campaign(campaign_id)
        total = self._repo.count_campaign_customers(campaign_id)
        return self._repo.serialize_campaign(doc, total)

    async def resume_campaign(self, campaign_id: str) -> CampaignStartResponse:
        campaign = self._require_campaign(campaign_id)
        if CampaignStatus(campaign["status"]) != CampaignStatus.PAUSED:
            raise CampaignStateError(campaign_id, "Campaign is not paused")

        run = self._repo.get_active_run(campaign_id)
        run_id = str(run["_id"]) if run else self._repo.create_run(campaign_id)

        self._repo.update_campaign_status(campaign_id, CampaignStatus.RUNNING)
        if self._queue:
            await self._queue.start_campaign(campaign_id, run_id)

        return CampaignStartResponse(
            campaign_id=campaign_id,
            run_id=run_id,
            status=CampaignStatus.RUNNING,
            message="Campaign resumed",
        )

    async def stop_campaign(self, campaign_id: str) -> CampaignResponse:
        campaign = self._require_campaign(campaign_id)
        status = CampaignStatus(campaign["status"])
        if status not in (CampaignStatus.RUNNING, CampaignStatus.PAUSED):
            raise CampaignStateError(campaign_id, f"Cannot stop campaign in '{status.value}' status")

        from datetime import datetime, timezone

        self._repo.update_campaign_status(
            campaign_id,
            CampaignStatus.STOPPED,
            ended_at=datetime.now(timezone.utc),
        )

        run = self._repo.get_active_run(campaign_id)
        if run:
            from app.models.campaign import CampaignRunStatus

            self._repo.end_run(str(run["_id"]), CampaignRunStatus.STOPPED)

        if self._queue:
            await self._queue.stop_campaign(campaign_id)

        doc = self._repo.get_campaign(campaign_id)
        total = self._repo.count_campaign_customers(campaign_id)
        return self._repo.serialize_campaign(doc, total)

    def list_campaigns(self) -> list[CampaignResponse]:
        campaigns = self._repo.list_campaigns()
        results = []
        for doc in campaigns:
            total = self._repo.count_campaign_customers(str(doc["_id"]))
            results.append(self._repo.serialize_campaign(doc, total))
        return results

    def get_campaign(self, campaign_id: str) -> CampaignResponse:
        doc = self._require_campaign(campaign_id)
        total = self._repo.count_campaign_customers(campaign_id)
        return self._repo.serialize_campaign(doc, total)

    def get_analytics(self, campaign_id: str) -> CampaignAnalyticsResponse:
        self._require_campaign(campaign_id)
        doc = self._repo.get_analytics(campaign_id)
        if not doc:
            total = self._repo.count_campaign_customers(campaign_id)
            self._repo.init_analytics(campaign_id, total)
            doc = self._repo.get_analytics(campaign_id)
        return self._repo.serialize_analytics(doc)

    def get_customers(
        self,
        campaign_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CampaignCustomerResponse]:
        self._require_campaign(campaign_id)
        docs = self._repo.get_campaign_customers(
            campaign_id, skip=skip, limit=limit
        )
        return [self._repo.serialize_customer(d) for d in docs]

    def get_results(
        self,
        campaign_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CampaignResultItem]:
        from app.database.mongodb import MongoDB
        from bson import ObjectId

        self._require_campaign(campaign_id)
        docs = self._repo.get_campaign_customers(
            campaign_id, skip=skip, limit=limit
        )
        results: list[CampaignResultItem] = []

        for doc in docs:
            customer = self._repo.serialize_customer(doc)
            call_id = doc.get("call_id")
            summary = lead_status = call_outcome = follow_up_date = None
            call_status = None
            duration = None

            if call_id:
                try:
                    call = MongoDB.calls().find_one({"_id": ObjectId(call_id)})
                except Exception:
                    call = None

                if call:
                    call_status = call.get("status")
                    call_id_str = str(call["_id"])

                    summary_doc = MongoDB.conversation_summaries().find_one(
                        {"call_id": call_id_str}
                    )
                    if summary_doc:
                        summary = summary_doc.get("summary")
                        follow_up_date = summary_doc.get("follow_up_date")

                    status_docs = find_sorted(
                        MongoDB.lead_status_updates(),
                        {"call_id": call_id_str},
                        sort_field="created_at",
                        sort_direction=-1,
                        limit=1,
                    )
                    if status_docs:
                        lead_status = status_docs[0].get("status")

                    outcome_doc = MongoDB.call_outcomes().find_one(
                        {"call_id": call_id_str}
                    )
                    if outcome_doc:
                        call_outcome = outcome_doc.get("outcome")

                    analytics = MongoDB.conversation_analytics().find_one(
                        {"call_id": call_id_str}
                    )
                    if analytics:
                        duration = analytics.get("duration_seconds")

            results.append(
                CampaignResultItem(
                    customer=customer,
                    summary=summary,
                    lead_status=lead_status,
                    call_outcome=call_outcome,
                    follow_up_date=follow_up_date,
                    call_status=call_status,
                    duration_seconds=duration,
                )
            )

        return results

    def _require_campaign(self, campaign_id: str) -> dict[str, Any]:
        doc = self._repo.get_campaign(campaign_id)
        if not doc:
            raise CampaignNotFoundError(campaign_id)
        return doc

    @staticmethod
    def _get_field(row: dict[str, str], field: str) -> str:
        for key, value in row.items():
            if key.strip().lower() == field:
                return (value or "").strip()
        return ""
