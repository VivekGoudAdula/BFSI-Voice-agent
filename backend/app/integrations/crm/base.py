"""Abstract CRM provider interface."""

from abc import ABC, abstractmethod
from typing import Any


class CRMProvider(ABC):
    """Common interface for CRM system integrations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g. salesforce)."""

    @abstractmethod
    async def create_contact(self, contact_data: dict[str, Any]) -> dict[str, Any]:
        """Create a contact or lead in the CRM."""

    @abstractmethod
    async def update_contact(
        self,
        contact_id: str,
        contact_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing contact or lead."""

    @abstractmethod
    async def create_activity(self, activity_data: dict[str, Any]) -> dict[str, Any]:
        """Log a customer interaction activity."""

    @abstractmethod
    async def create_note(self, note_data: dict[str, Any]) -> dict[str, Any]:
        """Attach a note to a contact or lead."""

    @abstractmethod
    async def update_lead_status(
        self,
        lead_id: str,
        status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Update lead status or stage."""

    @abstractmethod
    async def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Create a follow-up task."""

    async def sync_call_data(self, mapped_data: dict[str, Any]) -> dict[str, Any]:
        """
        Orchestrate full call sync to CRM.

        Default implementation performs standard BFSI post-call sync:
        upsert contact, update status, create note, activity, and optional task.
        """
        contact_id = mapped_data.get("crm_contact_id") or mapped_data.get("customer_id", "")
        contact_fields = mapped_data.get("contact", {})
        results: dict[str, Any] = {"provider": self.provider_name, "steps": []}

        if contact_id and contact_fields:
            update_result = await self.update_contact(contact_id, contact_fields)
            results["steps"].append({"action": "update_contact", "result": update_result})
        elif contact_fields:
            create_result = await self.create_contact(contact_fields)
            results["steps"].append({"action": "create_contact", "result": create_result})
            contact_id = create_result.get("id", contact_id)

        lead_status = mapped_data.get("lead_status")
        if lead_status and contact_id:
            status_result = await self.update_lead_status(
                contact_id,
                lead_status,
                mapped_data.get("lead_status_reason", ""),
            )
            results["steps"].append({"action": "update_lead_status", "result": status_result})

        note_fields = mapped_data.get("note", {})
        if note_fields:
            note_fields.setdefault("contact_id", contact_id)
            note_result = await self.create_note(note_fields)
            results["steps"].append({"action": "create_note", "result": note_result})

        activity_fields = mapped_data.get("activity", {})
        if activity_fields:
            activity_fields.setdefault("contact_id", contact_id)
            activity_result = await self.create_activity(activity_fields)
            results["steps"].append({"action": "create_activity", "result": activity_result})

        task_fields = mapped_data.get("task")
        if task_fields:
            task_fields.setdefault("contact_id", contact_id)
            task_result = await self.create_task(task_fields)
            results["steps"].append({"action": "create_task", "result": task_result})

        results["success"] = all(
            step["result"].get("success", False) for step in results["steps"]
        ) if results["steps"] else True

        return results
