"""Persistence helper for latency tracker documents."""

from __future__ import annotations

import logging
from typing import Any

from app.database.mongodb import MongoDB

logger = logging.getLogger(__name__)


class LatencyLogService:
    """Store latency events without affecting the call flow."""

    def save(self, payload: dict[str, Any]) -> None:
        if not payload:
            return
        try:
            MongoDB.latency_logs().insert_one(payload)
        except Exception as exc:
            logger.warning("Failed to persist latency log: %s", exc)
