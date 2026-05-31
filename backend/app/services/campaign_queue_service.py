"""Background campaign call queue with configurable batch processing."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import Settings
from app.core.logging_config import log_with_context
from app.models.call import AgentCallContext
from app.models.campaign import CampaignCustomerStatus, CampaignRunStatus, CampaignStatus
from app.models.crm import LeadStatus
from app.repositories.campaign_repository import CampaignRepository

logger = logging.getLogger(__name__)


class CampaignQueueService:
    """
    Manages outbound call queues for campaigns.

    Uses asyncio background tasks (Redis/Celery-ready design):
    - Decoupled from API request lifecycle
    - Configurable batch size and call interval
    - Tracks active calls per campaign
    """

    def __init__(
        self,
        repository: CampaignRepository,
        settings: Settings,
        call_service_factory: Any,
        customer_service: Any,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._call_service_factory = call_service_factory
        self._customer_service = customer_service
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_ids: dict[str, str] = {}
        self._paused: set[str] = set()
        self._lock = asyncio.Lock()

    async def start_campaign(self, campaign_id: str, run_id: str) -> None:
        async with self._lock:
            self._paused.discard(campaign_id)
            self._run_ids[campaign_id] = run_id
            existing = self._tasks.get(campaign_id)
            if existing and not existing.done():
                return
            self._tasks[campaign_id] = asyncio.create_task(
                self._process_campaign(campaign_id, run_id)
            )

    async def pause_campaign(self, campaign_id: str) -> None:
        self._paused.add(campaign_id)

    async def stop_campaign(self, campaign_id: str) -> None:
        self._paused.add(campaign_id)
        task = self._tasks.pop(campaign_id, None)
        if task and not task.done():
            task.cancel()

    async def on_call_finished(
        self,
        campaign_id: str,
        campaign_customer_id: str,
        *,
        success: bool = True,
        lead_status: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Called when a campaign call completes to update status and fill queue."""
        customer_status = self._map_lead_to_customer_status(lead_status, success)

        self._repo.update_campaign_customer(
            campaign_customer_id,
            {"status": customer_status.value},
        )

        increments: dict[str, Any] = {}
        if success:
            if customer_status == CampaignCustomerStatus.FAILED:
                increments["failed_calls"] = 1
            else:
                increments["completed_calls"] = 1
        else:
            increments["failed_calls"] = 1

        if lead_status == LeadStatus.CALLBACK_REQUESTED.value:
            increments["callbacks"] = 1
        elif lead_status == LeadStatus.ESCALATED.value:
            increments["escalations"] = 1
        elif lead_status == LeadStatus.INTERESTED.value:
            increments["interested_customers"] = 1
        elif lead_status == LeadStatus.PAYMENT_PROMISED.value:
            increments["payment_promises"] = 1

        if duration_seconds:
            increments["duration_seconds"] = duration_seconds

        if increments:
            self._repo.increment_analytics(campaign_id, increments)

        await self._try_fill_queue(campaign_id)

    async def on_call_failed(
        self, campaign_id: str, campaign_customer_id: str
    ) -> None:
        await self.on_call_finished(
            campaign_id,
            campaign_customer_id,
            success=False,
        )

    async def _try_fill_queue(self, campaign_id: str) -> None:
        """Signal the campaign processor to pick up more customers."""
        if campaign_id in self._paused:
            return
        campaign = self._repo.get_campaign(campaign_id)
        if not campaign or campaign["status"] != CampaignStatus.RUNNING.value:
            return
        task = self._tasks.get(campaign_id)
        if not task or task.done():
            run_id = self._run_ids.get(campaign_id, "")
            if not run_id:
                run = self._repo.get_active_run(campaign_id)
                run_id = str(run["_id"]) if run else ""
            if run_id:
                async with self._lock:
                    self._tasks[campaign_id] = asyncio.create_task(
                        self._process_campaign(campaign_id, run_id)
                    )

    async def _process_campaign(self, campaign_id: str, run_id: str) -> None:
        batch_size = self._settings.campaign_batch_size
        interval = self._settings.campaign_call_interval_seconds

        log_with_context(
            logger,
            logging.INFO,
            "Campaign queue processor started",
            campaign_id=campaign_id,
            run_id=run_id,
            batch_size=batch_size,
            event="campaign_queue_started",
        )

        try:
            while True:
                if campaign_id in self._paused:
                    break

                campaign = self._repo.get_campaign(campaign_id)
                if not campaign or campaign["status"] != CampaignStatus.RUNNING.value:
                    break

                active = self._repo.count_campaign_customers(
                    campaign_id, CampaignCustomerStatus.CALLING
                )
                slots = batch_size - active

                if slots <= 0:
                    await asyncio.sleep(interval)
                    if self._is_campaign_done(campaign_id):
                        await self._complete_campaign(campaign_id, run_id)
                        break
                    continue

                pending = self._repo.claim_pending_customers(campaign_id, slots)
                if not pending:
                    if active == 0:
                        await self._complete_campaign(campaign_id, run_id)
                        break
                    await asyncio.sleep(interval)
                    continue

                for customer_doc in pending:
                    if campaign_id in self._paused:
                        self._repo.update_campaign_customer(
                            str(customer_doc["_id"]),
                            {"status": CampaignCustomerStatus.PENDING.value},
                        )
                        continue

                    await self._initiate_campaign_call(campaign_id, customer_doc)

                await asyncio.sleep(interval)

        except asyncio.CancelledError:
            log_with_context(
                logger,
                logging.INFO,
                "Campaign queue cancelled",
                campaign_id=campaign_id,
                event="campaign_queue_cancelled",
            )
        except Exception as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Campaign queue error: {exc}",
                campaign_id=campaign_id,
                event="campaign_queue_error",
            )

    async def _initiate_campaign_call(
        self, campaign_id: str, customer_doc: dict[str, Any]
    ) -> None:
        customer_id_str = str(customer_doc["_id"])
        campaign_customer_id = customer_id_str

        try:
            from app.models.customer import CustomerCreate

            customer = self._customer_service.get_or_create(
                CustomerCreate(
                    name=customer_doc["customer_name"],
                    phone=customer_doc["phone"],
                )
            )

            call_service = self._call_service_factory()
            agent_context = AgentCallContext(loan_account=customer_doc["loan_id"])

            call = await call_service.initiate_call(
                customer_id=customer.id,
                agent_context=agent_context,
                campaign_id=campaign_id,
                campaign_customer_id=campaign_customer_id,
            )

            self._repo.update_campaign_customer(
                campaign_customer_id,
                {
                    "call_id": call.id,
                    "customer_id": customer.id,
                },
            )
            self._repo.increment_analytics(
                campaign_id, {"calls_initiated": 1}
            )

            log_with_context(
                logger,
                logging.INFO,
                "Campaign call initiated",
                campaign_id=campaign_id,
                campaign_customer_id=campaign_customer_id,
                call_id=call.id,
                event="campaign_call_initiated",
            )

        except Exception as exc:
            logger.error(
                "Failed to initiate campaign call for %s: %s",
                campaign_customer_id,
                exc,
            )
            self._repo.update_campaign_customer(
                campaign_customer_id,
                {"status": CampaignCustomerStatus.FAILED.value},
            )
            self._repo.increment_analytics(
                campaign_id, {"failed_calls": 1, "calls_initiated": 1}
            )

    async def _complete_campaign(self, campaign_id: str, run_id: str) -> None:
        self._repo.update_campaign_status(
            campaign_id,
            CampaignStatus.COMPLETED,
            ended_at=datetime.now(timezone.utc),
        )
        self._repo.end_run(run_id, CampaignRunStatus.COMPLETED)
        self._tasks.pop(campaign_id, None)

        log_with_context(
            logger,
            logging.INFO,
            "Campaign completed",
            campaign_id=campaign_id,
            run_id=run_id,
            event="campaign_completed",
        )

    def _is_campaign_done(self, campaign_id: str) -> bool:
        pending = self._repo.count_campaign_customers(
            campaign_id, CampaignCustomerStatus.PENDING
        )
        calling = self._repo.count_campaign_customers(
            campaign_id, CampaignCustomerStatus.CALLING
        )
        return pending == 0 and calling == 0

    @staticmethod
    def _map_lead_to_customer_status(
        lead_status: Optional[str], success: bool
    ) -> CampaignCustomerStatus:
        if not success:
            return CampaignCustomerStatus.FAILED
        if lead_status == LeadStatus.CALLBACK_REQUESTED.value:
            return CampaignCustomerStatus.CALLBACK_REQUESTED
        if lead_status == LeadStatus.ESCALATED.value:
            return CampaignCustomerStatus.ESCALATED
        return CampaignCustomerStatus.COMPLETED
