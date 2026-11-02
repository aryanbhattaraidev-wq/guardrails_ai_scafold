"""Structured logging helpers.

The library only creates the ``ai_guardrails`` logger; it never configures the
root logger. Applications (or the CLI/API entry points) call
``configure_logging`` once at startup.

Raw prompts and outputs are never logged unless ``runtime.log_content`` is set,
which is rejected in production by the config schema.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from ai_guardrails.core.types import ValidationResult

LOGGER_NAME = "ai_guardrails"

logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())


class JsonFormatter(logging.Formatter):
    """One JSON object per line; structured fields come from ``extra={'fields': ...}``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Attach a JSON stderr handler to the package logger (idempotent)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    # Avoid duplicate lines when the host application also configures the root logger.
    logger.propagate = False
    if not any(getattr(h, "_ai_guardrails", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        handler._ai_guardrails = True  # type: ignore[attr-defined]
        logger.addHandler(handler)


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    logging.getLogger(LOGGER_NAME).log(level, event, extra={"fields": fields})


def log_result(result: ValidationResult, *, log_content: bool = False) -> None:
    """Log one validation outcome without content (unless explicitly enabled)."""
    fields: dict[str, Any] = {
        "request_id": result.request_id,
        "stage": result.stage.value,
        "policy": result.profile,
        "status": result.status.value,
        "failed_validators": list(result.failed_validators),
        "reason_code": result.reason_code.value if result.reason_code else None,
        "duration_ms": round(result.duration_ms, 2),
    }
    fields.update(result.diagnostics)
    if log_content:
        fields["content"] = result.content
    level = logging.WARNING if result.status.value in {"blocked", "error"} else logging.INFO
    log_event("validation", level, **fields)
