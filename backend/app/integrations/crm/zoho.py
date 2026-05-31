"""Zoho CRM integration."""

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.crm.base import CRMProvider

logger = logging.getLogger(__name__)


class ZohoCRMProvider(CRMProvider):
    """Zoho CRM provider using OAuth refresh token flow."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._access_token: str | None = None

    @property
    def provider_name(self) -> str:
        return "zoho"

    @property
    def _mock_mode(self) -> bool:
        return self._settings.crm_mock_mode or not self._settings.zoho_client_id

    @property
    def _api_base(self) -> str:
        domain = self._settings.zoho_api_domain or "https://www.zohoapis.com"
        return f"{domain.rstrip('/')}/crm/v6"

    async def _authenticate(self) -> str:
        if self._access_token:
            return self._access_token

        if self._mock_mode:
            self._access_token = "mock_zoho_token"
            return self._access_token

        token_url = "https://accounts.zoho.com/oauth/v2/token"
        payload = {
            "refresh_token": self._settings.zoho_refresh_token,
            "client_id": self._settings.zoho_client_id,
            "client_secret": self._settings.zoho_client_secret,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            return self._access_token

    async def _api_request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._mock_mode:
            return {"success": True, "id": f"zoho_mock_{path.replace('/', '_')}"}

        token = await self._authenticate()
        url = f"{self._api_base}{path}"
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, json=json_data, headers=headers)
            response.raise_for_status()
            return {"success": True, **response.json()}

    async def create_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self._api_request(
                "POST",
                "/Contacts",
                {"data": [contact_data]},
            )
            record_id = self._extract_record_id(result)
            return {"success": True, "id": record_id, "data": result}
        except Exception as exc:
            logger.error("Zoho create_contact failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def update_contact(
        self,
        contact_id: str,
        contact_data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            contact_data["id"] = contact_id
            result = await self._api_request(
                "PUT",
                "/Contacts",
                {"data": [contact_data]},
            )
            return {"success": True, "id": contact_id, "data": result}
        except Exception as exc:
            logger.error("Zoho update_contact failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_activity(self, activity_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "Subject": activity_data.get("Subject", "Voice Call"),
            "Call_Result": activity_data.get("Call_Result", ""),
            "Call_Duration": activity_data.get("Call_Duration", ""),
            "Call_Reference": activity_data.get("Call_Reference", ""),
        }
        contact_id = activity_data.get("contact_id")
        if contact_id:
            payload["Who_Id"] = {"id": contact_id}

        try:
            result = await self._api_request(
                "POST",
                "/Calls",
                {"data": [payload]},
            )
            record_id = self._extract_record_id(result)
            return {"success": True, "id": record_id, "data": result}
        except Exception as exc:
            logger.error("Zoho create_activity failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_note(self, note_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "Note_Title": note_data.get("Note_Title", "Call Summary"),
            "Note_Content": note_data.get("Note_Content", ""),
            "Parent_Id": note_data.get("contact_id", ""),
            "$se_module": "Contacts",
        }

        try:
            result = await self._api_request(
                "POST",
                "/Notes",
                {"data": [payload]},
            )
            record_id = self._extract_record_id(result)
            return {"success": True, "id": record_id, "data": result}
        except Exception as exc:
            logger.error("Zoho create_note failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def update_lead_status(
        self,
        lead_id: str,
        status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": lead_id, "Lead_Status": status}
        if reason:
            payload["Description"] = reason

        try:
            result = await self._api_request(
                "PUT",
                "/Leads",
                {"data": [payload]},
            )
            return {"success": True, "id": lead_id, "status": status, "data": result}
        except Exception as exc:
            logger.error("Zoho update_lead_status failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "Subject": task_data.get("Subject", "Follow-up Call"),
            "Due_Date": task_data.get("Due_Date", ""),
            "Due_Time": task_data.get("Due_Time", ""),
            "Description": task_data.get("Description", ""),
            "Status": "Not Started",
        }
        contact_id = task_data.get("contact_id")
        if contact_id:
            payload["Who_Id"] = {"id": contact_id}

        try:
            result = await self._api_request(
                "POST",
                "/Tasks",
                {"data": [payload]},
            )
            record_id = self._extract_record_id(result)
            return {"success": True, "id": record_id, "data": result}
        except Exception as exc:
            logger.error("Zoho create_task failed: %s", exc)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _extract_record_id(result: dict[str, Any]) -> str:
        data = result.get("data", [])
        if data and isinstance(data, list):
            details = data[0].get("details", {})
            return details.get("id", "")
        return result.get("id", "")
