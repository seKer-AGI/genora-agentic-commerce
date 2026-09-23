"""Structured JSON logging with automatic redaction of sensitive fields."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)

SENSITIVE_KEYS = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|card|cvv|ssn|refresh)", re.IGNORECASE
)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_SK = re.compile(r"\b(sk|pk|rk)_(live|test)?_?[A-Za-z0-9]{12,}\b")


def redact(value: Any, _depth: int = 0) -> Any:
    """Recursively redact secrets from log payloads."""
    if _depth > 6:
        return "<max-depth>"
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if SENSITIVE_KEYS.search(str(k)) else redact(v, _depth + 1)) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v, _depth + 1) for v in value]
    if isinstance(value, str):
        value = _BEARER.sub(r"\1<redacted>", value)
        value = _JWT.sub("<redacted-jwt>", value)
        return _SK.sub("<redacted-key>", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if rid := request_id_ctx.get():
            payload["request_id"] = rid
        if uid := user_id_ctx.get():
            payload["user_id"] = uid
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(redact(extra))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{datetime.fromtimestamp(record.created).strftime('%H:%M:%S')} {record.levelname:<7} {record.name}: "
        base += str(redact(record.getMessage()))
        extra = getattr(record, "extra_fields", None)
        if extra:
            base += " " + json.dumps(redact(extra), default=str)
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, msg: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a message with structured fields (redacted automatically)."""
    logger.log(level, msg, extra={"extra_fields": fields})
