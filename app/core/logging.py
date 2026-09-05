"""Structured logging.

Every log line is emitted as a single JSON object so it can be grepped,
shipped, and (later, in Phase 5/6) correlated by request_id without a log
parser. The request_id contextvar is set once per HTTP request by
RequestIDMiddleware and picked up automatically by every log record emitted
during that request — including ones logged deep inside a service or
provider that has no direct handle on the request.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id

        # Anything passed via `extra={...}` on the log call rides along too,
        # e.g. operation, service, provider, duration_ms, status, error.
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS:
                continue
            payload.setdefault(key, value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


_RESERVED_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
}


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload.
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet the noisy libraries down to WARNING; app logs stay at `level`.
    for noisy_logger in ("botocore", "boto3", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def log_operation(
    logger: logging.Logger,
    *,
    operation: str,
    service: str,
    provider: str,
    duration_ms: float,
    status: str,
    resource: str | None = None,
    error: str | None = None,
) -> None:
    """Emit one structured event for a completed provider operation.

    This is the shape referenced in Phase 5's observability model
    (request_id/operation/service/resource/provider/duration/status/error) —
    building it now, even though the operation-history *UI* doesn't exist
    yet, means every operation already has a consistent event to read from.
    """
    level = logging.ERROR if error else logging.INFO
    logger.log(
        level,
        "%s %s", service, operation,
        extra={
            "operation": operation,
            "service": service,
            "provider": provider,
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "resource": resource,
            "error": error,
        },
    )


def timed_ms() -> Any:
    """Return a monotonic start marker for measuring operation duration."""
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
