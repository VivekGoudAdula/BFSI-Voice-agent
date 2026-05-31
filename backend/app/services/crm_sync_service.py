"""CRM synchronization service with retry mechanism."""

import asyncio
import logging
from typing import Any

from app.core.config import Settings
from app.core.logging_config import log_with_context
from app.integrations.crm.base import CRMProvider
from app.integrations.crm.factory import create_crm_provider
from app.integrations.crm.mapping import CRMMappingEngine
from app.models.crm import CRMSyncStatus, ProcessedCallData
from app.services.crm_data_service import CRMDataService

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = [60, 300, 900]


class CRMSyncService:
    """Pushes processed call data to CRM with retries and audit logging."""

    def __init__(
        self,
        settings: Settings,
        crm_data_service: CRMDataService,
        crm_provider: CRMProvider | None = None,
    ) -> None:
        self._settings = settings
        self._crm_data = crm_data_service
        self._provider = crm_provider or create_crm_provider(settings)
        self._mapping_engine = CRMMappingEngine(self._provider.provider_name)

    async def sync_call(self, call_data: ProcessedCallData) -> dict[str, Any]:
        """
        Sync call data to CRM with retry on failure.

        Never loses updates — failures are logged and retried.
        """
        if not self._settings.crm_enabled:
            log_with_context(
                logger,
                logging.INFO,
                "CRM sync skipped (disabled)",
                call_id=call_data.call_id,
                event="crm_sync_skipped",
            )
            return {"success": True, "skipped": True}

        log_id = self._crm_data.create_sync_log(
            call_id=call_data.call_id,
            call_sid=call_data.call_sid,
            provider=self._provider.provider_name,
            status=CRMSyncStatus.PENDING,
        )

        mapped_payload = self._mapping_engine.build_sync_payload(call_data)
        return await self._execute_with_retries(log_id, call_data.call_id, mapped_payload)

    async def retry_pending_sync(
        self,
        log_id: str,
        call_data: ProcessedCallData,
    ) -> dict[str, Any]:
        """Manually retry a failed CRM sync."""
        mapped_payload = self._mapping_engine.build_sync_payload(call_data)
        return await self._execute_with_retries(log_id, call_data.call_id, mapped_payload)

    async def _execute_with_retries(
        self,
        log_id: str,
        call_id: str,
        mapped_payload: dict[str, Any],
    ) -> dict[str, Any]:
        max_attempts = len(RETRY_DELAYS_SECONDS) + 1
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            try:
                result = await self._provider.sync_call_data(mapped_payload)
                if result.get("success"):
                    self._crm_data.update_sync_log(
                        log_id,
                        status=CRMSyncStatus.SUCCESS,
                        attempts=attempt,
                    )
                    log_with_context(
                        logger,
                        logging.INFO,
                        "CRM sync successful",
                        call_id=call_id,
                        provider=self._provider.provider_name,
                        attempts=attempt,
                        event="crm_sync_success",
                    )
                    return {"success": True, "attempts": attempt, "result": result}

                last_error = str(result.get("error", "CRM sync returned failure"))
            except Exception as exc:
                last_error = str(exc)
                log_with_context(
                    logger,
                    logging.WARNING,
                    f"CRM sync attempt {attempt} failed: {exc}",
                    call_id=call_id,
                    event="crm_sync_retry",
                )

            if attempt < max_attempts:
                self._crm_data.update_sync_log(
                    log_id,
                    status=CRMSyncStatus.RETRY,
                    attempts=attempt,
                    error_message=last_error,
                )
                delay = RETRY_DELAYS_SECONDS[attempt - 1]
                log_with_context(
                    logger,
                    logging.INFO,
                    f"Scheduling CRM retry in {delay}s",
                    call_id=call_id,
                    attempt=attempt,
                    event="crm_sync_scheduled",
                )
                await asyncio.sleep(delay)
            else:
                self._crm_data.update_sync_log(
                    log_id,
                    status=CRMSyncStatus.FAILED,
                    attempts=attempt,
                    error_message=last_error,
                )
                log_with_context(
                    logger,
                    logging.ERROR,
                    f"CRM sync failed after {attempt} attempts: {last_error}",
                    call_id=call_id,
                    event="crm_sync_failed",
                )

        return {"success": False, "attempts": max_attempts, "error": last_error}

    def schedule_background_sync(self, call_data: ProcessedCallData) -> None:
        """Fire-and-forget CRM sync so call teardown is not blocked."""
        asyncio.create_task(self._background_sync(call_data))

    async def _background_sync(self, call_data: ProcessedCallData) -> None:
        try:
            await self.sync_call(call_data)
        except Exception as exc:
            log_with_context(
                logger,
                logging.ERROR,
                f"Background CRM sync error: {exc}",
                call_id=call_data.call_id,
                event="crm_sync_background_error",
            )
