"""Configuration-based CRM field mapping engine."""

import json
import logging
from pathlib import Path
from typing import Any

from app.models.crm import ProcessedCallData

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent / "config"


class CRMMappingEngine:
    """Maps internal call data to CRM-specific field structures."""

    def __init__(self, provider: str) -> None:
        self._provider = provider
        self._mapping = self._load_mapping(provider)

    @staticmethod
    def _load_mapping(provider: str) -> dict[str, Any]:
        mapping_file = CONFIG_DIR / f"{provider}_mapping.json"
        if not mapping_file.exists():
            logger.warning("CRM mapping file not found: %s", mapping_file)
            return {}
        try:
            return json.loads(mapping_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Invalid CRM mapping JSON for %s: %s", provider, exc)
            return {}

    def map_lead_status(self, internal_status: str) -> str:
        """Map internal lead status to CRM-specific status value."""
        status_map = self._mapping.get("lead_status", {})
        return status_map.get(internal_status, internal_status)

    def map_contact(self, call_data: ProcessedCallData) -> dict[str, Any]:
        """Map internal customer fields to CRM contact fields."""
        internal = {
            "customer_id": call_data.customer_id,
            "name": call_data.customer_name,
            "phone": call_data.customer_phone,
            "loan_id": call_data.loan_id or call_data.agent_context.get("loan_account", ""),
        }
        return self._apply_mapping("contact", internal)

    def map_note(self, call_data: ProcessedCallData) -> dict[str, Any]:
        """Map call summary and transcript to CRM note fields."""
        internal = {
            "summary": call_data.summary,
            "transcript": call_data.transcript[:8000],
            "call_outcome": call_data.call_outcome.value,
        }
        return self._apply_mapping("note", internal)

    def map_activity(self, call_data: ProcessedCallData) -> dict[str, Any]:
        """Map call interaction to CRM activity fields."""
        duration_minutes = ""
        if call_data.duration_seconds is not None:
            duration_minutes = str(round(call_data.duration_seconds / 60, 1))

        internal = {
            "summary": f"Voice Call - {call_data.call_outcome.value}",
            "call_outcome": call_data.call_outcome.value,
            "duration_seconds": duration_minutes,
            "call_sid": call_data.call_sid,
        }
        return self._apply_mapping("activity", internal)

    def map_task(self, call_data: ProcessedCallData) -> dict[str, Any] | None:
        """Map follow-up request to CRM task fields."""
        if not call_data.follow_up_date and not call_data.follow_up_actions:
            return None

        notes = "; ".join(call_data.follow_up_actions) if call_data.follow_up_actions else call_data.summary
        internal = {
            "summary": f"Follow-up: {call_data.customer_name}",
            "follow_up_date": call_data.follow_up_date or "",
            "follow_up_time": call_data.follow_up_time or "",
            "notes": notes,
        }
        return self._apply_mapping("task", internal)

    def build_sync_payload(
        self,
        call_data: ProcessedCallData,
        *,
        crm_contact_id: str = "",
    ) -> dict[str, Any]:
        """Build complete mapped payload for CRM sync."""
        task = self.map_task(call_data)
        payload: dict[str, Any] = {
            "crm_contact_id": crm_contact_id or call_data.customer_id,
            "customer_id": call_data.customer_id,
            "call_id": call_data.call_id,
            "call_sid": call_data.call_sid,
            "lead_status": self.map_lead_status(call_data.lead_status.value),
            "lead_status_reason": call_data.intent,
            "contact": self.map_contact(call_data),
            "note": self.map_note(call_data),
            "activity": self.map_activity(call_data),
        }
        if task:
            payload["task"] = task
        return payload

    def _apply_mapping(
        self,
        section: str,
        internal: dict[str, Any],
    ) -> dict[str, Any]:
        field_map = self._mapping.get(section, {})
        if not field_map:
            return dict(internal)

        mapped: dict[str, Any] = {}
        for internal_key, crm_key in field_map.items():
            value = internal.get(internal_key)
            if value is not None and value != "":
                mapped[crm_key] = value
        return mapped
