"""LeadSquared CRM integration."""

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.crm.base import CRMProvider

logger = logging.getLogger(__name__)


class LeadSquaredCRMProvider(CRMProvider):
    """LeadSquared CRM provider."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def provider_name(self) -> str:
        return "leadsquared"

    @property
    def _mock_mode(self) -> bool:
        return self._settings.crm_mock_mode or not self._settings.leadsquared_access_key

    @property
    def _api_base(self) -> str:
        host = self._settings.leadsquared_host or "https://api-in21.leadsquared.com"
        return host.rstrip("/")

    async def _api_request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._mock_mode:
            return {"success": True, "id": f"lsq_mock_{path.replace('/', '_')}"}

        url = f"{self._api_base}{path}"
        params = {
            "accessKey": self._settings.leadsquared_access_key,
            "secretKey": self._settings.leadsquared_secret_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, params=params, json=json_data)
            response.raise_for_status()
            data = response.json()
            return {"success": True, **data}

    async def create_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        payload = [
            {"Attribute": key, "Value": value}
            for key, value in contact_data.items()
        ]

        try:
            result = await self._api_request(
                "POST",
                "/v2/LeadManagement.svc/Lead.Create",
                payload,
            )
            return {"success": True, "id": result.get("Message", {}).get("Id", ""), "data": result}
        except Exception as exc:
            logger.error("LeadSquared create_contact failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def update_contact(
        self,
        contact_id: str,
        contact_data: dict[str, Any],
    ) -> dict[str, Any]:
        payload = [
            {"Attribute": key, "Value": value}
            for key, value in contact_data.items()
        ]

        try:
            result = await self._api_request(
                "POST",
                f"/v2/LeadManagement.svc/Lead.Update?leadId={contact_id}",
                payload,
            )
            return {"success": True, "id": contact_id, "data": result}
        except Exception as exc:
            logger.error("LeadSquared update_contact failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_activity(self, activity_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "RelatedProspectId": activity_data.get("contact_id", ""),
            "ActivityEvent": 210,
            "ActivityEventName": activity_data.get("ActivityEventName", "Voice Call"),
            "ActivityNote": activity_data.get("Status", ""),
            "Fields": [
                {"SchemaName": "mx_Call_SID", "Value": activity_data.get("mx_Call_SID", "")},
                {"SchemaName": "Duration", "Value": activity_data.get("Duration", "")},
            ],
        }

        try:
            result = await self._api_request(
                "POST",
                "/v2/ProspectActivity.svc/Create",
                payload,
            )
            return {"success": True, "id": result.get("Message", {}).get("Id", ""), "data": result}
        except Exception as exc:
            logger.error("LeadSquared create_activity failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_note(self, note_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "RelatedProspectId": note_data.get("contact_id", ""),
            "Note": note_data.get("Note", "Call Summary"),
            "NotText": note_data.get("NotText", ""),
        }

        try:
            result = await self._api_request(
                "POST",
                "/v2/LeadManagement.svc/CreateNote",
                payload,
            )
            return {"success": True, "id": result.get("Message", {}).get("Id", ""), "data": result}
        except Exception as exc:
            logger.error("LeadSquared create_note failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def update_lead_status(
        self,
        lead_id: str,
        status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        payload = [
            {"Attribute": "ProspectStage", "Value": status},
        ]
        if reason:
            payload.append({"Attribute": "Notes", "Value": reason})

        try:
            result = await self._api_request(
                "POST",
                f"/v2/LeadManagement.svc/Lead.Update?leadId={lead_id}",
                payload,
            )
            return {"success": True, "id": lead_id, "status": status, "data": result}
        except Exception as exc:
            logger.error("LeadSquared update_lead_status failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "Name": task_data.get("Name", "Follow-up Call"),
            "RelatedEntity": 1,
            "RelatedEntityId": task_data.get("contact_id", ""),
            "DueDate": task_data.get("DueDate", ""),
            "EndTime": task_data.get("EndTime", ""),
            "Description": task_data.get("Description", ""),
        }

        try:
            result = await self._api_request(
                "POST",
                "/v2/Task.svc/Create",
                payload,
            )
            return {"success": True, "id": result.get("Message", {}).get("Id", ""), "data": result}
        except Exception as exc:
            logger.error("LeadSquared create_task failed: %s", exc)
            return {"success": False, "error": str(exc)}
