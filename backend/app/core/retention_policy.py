"""Configurable retention policy framework for compliance data (Phase 8).

Deletion is not implemented — this module defines retention windows only.
"""

from dataclasses import dataclass
from datetime import timedelta

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention windows per data category (days)."""

    transcripts_days: int = 2555  # ~7 years
    audit_logs_days: int = 2555
    call_recordings_days: int = 2555
    consent_records_days: int = 2555
    disclosure_records_days: int = 2555
    tool_audit_days: int = 2555
    crm_audit_days: int = 2555
    escalation_audit_days: int = 2555
    compliance_events_days: int = 2555

    def as_dict(self) -> dict[str, int]:
        return {
            "transcripts_days": self.transcripts_days,
            "audit_logs_days": self.audit_logs_days,
            "call_recordings_days": self.call_recordings_days,
            "consent_records_days": self.consent_records_days,
            "disclosure_records_days": self.disclosure_records_days,
            "tool_audit_days": self.tool_audit_days,
            "crm_audit_days": self.crm_audit_days,
            "escalation_audit_days": self.escalation_audit_days,
            "compliance_events_days": self.compliance_events_days,
        }

    def retention_delta(self, category: str) -> timedelta:
        days_map = self.as_dict()
        days = days_map.get(f"{category}_days", self.audit_logs_days)
        return timedelta(days=days)


def get_retention_policy(settings: Settings | None = None) -> RetentionPolicy:
    """Build retention policy from application settings."""
    settings = settings or get_settings()
    return RetentionPolicy(
        transcripts_days=settings.compliance_retention_transcripts_days,
        audit_logs_days=settings.compliance_retention_audit_logs_days,
        call_recordings_days=settings.compliance_retention_recordings_days,
        consent_records_days=settings.compliance_retention_consent_days,
        disclosure_records_days=settings.compliance_retention_disclosure_days,
        tool_audit_days=settings.compliance_retention_tool_audit_days,
        crm_audit_days=settings.compliance_retention_crm_audit_days,
        escalation_audit_days=settings.compliance_retention_escalation_days,
        compliance_events_days=settings.compliance_retention_events_days,
    )
