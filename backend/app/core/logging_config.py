"""Structured logging configuration."""

import logging
import sys
from typing import Any

from app.core.config import get_settings


class StructuredFormatter(logging.Formatter):
    """Formatter that produces consistent, parseable log lines."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras: list[str] = []
        for key in (
            "customer_id",
            "call_id",
            "phone",
            "twilio_call_sid",
            "stream_sid",
            "event",
            "stt_ms",
            "groq_ms",
            "elevenlabs_ms",
            "total_ms",
        ):
            if hasattr(record, key):
                extras.append(f"{key}={getattr(record, key)}")
        if extras:
            return f"{base} | {' '.join(extras)}"
        return base


def setup_logging() -> None:
    """Configure root logger with structured formatting."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        StructuredFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **context: Any,
) -> None:
    """Emit a log record with optional structured context fields."""
    extra = {k: v for k, v in context.items() if v is not None}
    logger.log(level, message, extra=extra)
