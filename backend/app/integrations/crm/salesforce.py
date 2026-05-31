"""Salesforce CRM integration."""

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.crm.base import CRMProvider

logger = logging.getLogger(__name__)


class SalesforceCRMProvider(CRMProvider):
    """Salesforce CRM provider with OAuth password flow."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._access_token: str | None = None
        self._instance_url: str = settings.salesforce_instance_url

    @property
    def provider_name(self) -> str:
        return "salesforce"

    @property
    def _mock_mode(self) -> bool:
        return self._settings.crm_mock_mode or not self._settings.salesforce_client_id

    async def _authenticate(self) -> str:
        if self._access_token:
            return self._access_token

        if self._mock_mode:
            self._access_token = "mock_salesforce_token"
            return self._access_token

        token_url = f"{self._instance_url}/services/oauth2/token"
        payload = {
            "grant_type": "password",
            "client_id": self._settings.salesforce_client_id,
            "client_secret": self._settings.salesforce_client_secret,
            "username": self._settings.salesforce_username,
            "password": (
                f"{self._settings.salesforce_password}"
                f"{self._settings.salesforce_security_token}"
            ),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            self._instance_url = data.get("instance_url", self._instance_url)
            return self._access_token

    async def _api_request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._mock_mode:
            return {"success": True, "id": f"sf_mock_{path.replace('/', '_')}"}

        token = await self._authenticate()
        url = f"{self._instance_url}{path}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, json=json_data, headers=headers)
            response.raise_for_status()
            if response.status_code == 204:
                return {"success": True}
            return {"success": True, **response.json()}

    async def create_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self._api_request(
                "POST",
                "/services/data/v58.0/sobjects/Lead",
                contact_data,
            )
            return {"success": True, "id": result.get("id", ""), "data": result}
        except Exception as exc:
            logger.error("Salesforce create_contact failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def update_contact(
        self,
        contact_id: str,
        contact_data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            await self._api_request(
                "PATCH",
                f"/services/data/v58.0/sobjects/Lead/{contact_id}",
                contact_data,
            )
            return {"success": True, "id": contact_id}
        except Exception as exc:
            logger.error("Salesforce update_contact failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_activity(self, activity_data: dict[str, Any]) -> dict[str, Any]:
        task_payload = {
            "Subject": activity_data.get("Subject", "Voice Call"),
            "Status": activity_data.get("Status", "Completed"),
            "Priority": "Normal",
            "ActivityDate": activity_data.get("ActivityDate", ""),
            "Description": activity_data.get("Description", ""),
        }
        who_id = activity_data.get("contact_id") or activity_data.get("WhoId")
        if who_id:
            task_payload["WhoId"] = who_id

        try:
            result = await self._api_request(
                "POST",
                "/services/data/v58.0/sobjects/Task",
                task_payload,
            )
            return {"success": True, "id": result.get("id", ""), "data": result}
        except Exception as exc:
            logger.error("Salesforce create_activity failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_note(self, note_data: dict[str, Any]) -> dict[str, Any]:
        content = note_data.get("Body") or note_data.get("Title", "")
        title = note_data.get("Title", "Call Summary")
        parent_id = note_data.get("contact_id") or note_data.get("ParentId", "")

        note_payload = {
            "Title": title,
            "Body": content,
            "ParentId": parent_id,
        }

        try:
            result = await self._api_request(
                "POST",
                "/services/data/v58.0/sobjects/ContentNote",
                note_payload,
            )
            return {"success": True, "id": result.get("id", ""), "data": result}
        except Exception as exc:
            logger.error("Salesforce create_note failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def update_lead_status(
        self,
        lead_id: str,
        status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"Status": status}
        if reason:
            payload["Description"] = reason

        try:
            await self._api_request(
                "PATCH",
                f"/services/data/v58.0/sobjects/Lead/{lead_id}",
                payload,
            )
            return {"success": True, "id": lead_id, "status": status}
        except Exception as exc:
            logger.error("Salesforce update_lead_status failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "Subject": task_data.get("Subject", "Follow-up Call"),
            "Status": "Not Started",
            "Priority": "Normal",
            "ActivityDate": task_data.get("ActivityDate", ""),
            "Description": task_data.get("Description", ""),
        }
        who_id = task_data.get("contact_id")
        if who_id:
            payload["WhoId"] = who_id

        try:
            result = await self._api_request(
                "POST",
                "/services/data/v58.0/sobjects/Task",
                payload,
            )
            return {"success": True, "id": result.get("id", ""), "data": result}
        except Exception as exc:
            logger.error("Salesforce create_task failed: %s", exc)
            return {"success": False, "error": str(exc)}
