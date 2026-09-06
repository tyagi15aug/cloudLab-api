"""Phase 5: in-process operation history and metrics.

The plan's observability model (Sections 5 and 15) asks for every
significant operation to carry a request_id/operation/service/resource/
provider/duration/status/error tuple. `app/core/logging.py`'s
`log_operation` already builds and emits exactly that shape as a structured
JSON log line — this module keeps the same event in an in-memory, queryable
form too, so a developer (or an E2E test) can read "what just happened"
back out over HTTP instead of grepping stdout.

Recorded the same way failure injection is applied: `ProviderService._call()`
calls `operation_recorder.record(...)` right alongside `log_operation(...)`,
so every resource service gets operation history for free with zero
per-service code — and any operation that Phase 4's failure injector hit
shows up here too (status="error", the injected AppError's code), since
`_call()` can't tell the difference between a real boto3 failure and an
injected one by the time it's logging the outcome. This is deliberately the
same data Phase 6's CI log analyzer is meant to eventually correlate
against, so the shape matches `log_operation`'s fields exactly rather than
inventing a second, slightly different one.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass, field

#: How many recent operations to keep in memory. This is a developer/demo
#: panel, not a production metrics store — enough to browse a demo session
#: without unbounded memory growth. Cumulative counters below (`_totals`,
#: `_by_operation`) intentionally outlive eviction from this buffer, so
#: `metrics()` stays accurate for the process's whole lifetime even once
#: more than MAX_HISTORY operations have happened.
MAX_HISTORY = 200


@dataclass
class OperationRecord:
    id: int
    service: str
    operation: str
    provider: str
    status: str  # "success" | "error"
    duration_ms: float
    request_id: str | None = None
    resource: str | None = None
    error: str | None = None
    retryable: bool | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class _OperationStats:
    count: int = 0
    error_count: int = 0
    duration_sum_ms: float = 0.0


class OperationRecorder:
    """Process-wide ring buffer of recent operations, plus cumulative
    per-operation counters.

    Guarded by the same `threading.Lock()` pattern as `FailureInjector`
    (app/core/failure_injection.py) — FastAPI's sync route handlers run in
    a thread pool, so concurrent resource calls recording at the same
    moment are a real race, not a theoretical one.
    """

    def __init__(self, max_history: int = MAX_HISTORY) -> None:
        self._history: deque[OperationRecord] = deque(maxlen=max_history)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._totals = _OperationStats()
        self._by_operation: dict[tuple[str, str], _OperationStats] = {}

    def record(
        self,
        *,
        service: str,
        operation: str,
        provider: str,
        status: str,
        duration_ms: float,
        request_id: str | None = None,
        resource: str | None = None,
        error: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        duration_ms = round(duration_ms, 2)
        with self._lock:
            record = OperationRecord(
                id=next(self._ids),
                service=service,
                operation=operation,
                provider=provider,
                status=status,
                duration_ms=duration_ms,
                request_id=request_id,
                resource=resource,
                error=error,
                retryable=retryable,
            )
            self._history.append(record)

            self._totals.count += 1
            self._totals.duration_sum_ms += duration_ms
            if status == "error":
                self._totals.error_count += 1

            bucket = self._by_operation.setdefault((service, operation), _OperationStats())
            bucket.count += 1
            bucket.duration_sum_ms += duration_ms
            if status == "error":
                bucket.error_count += 1

    def list_recent(self, limit: int = 50) -> list[OperationRecord]:
        with self._lock:
            items = list(self._history)
        items.reverse()  # newest first
        return items[: max(0, limit)]

    def get(self, operation_id: int) -> OperationRecord | None:
        with self._lock:
            for record in self._history:
                if record.id == operation_id:
                    return record
        return None

    def metrics(self) -> dict[str, object]:
        with self._lock:
            total = self._totals.count
            errors = self._totals.error_count
            duration_sum = self._totals.duration_sum_ms
            by_operation: list[dict[str, str | int | float]] = [
                {
                    "service": service,
                    "operation": operation,
                    "count": stats.count,
                    "error_count": stats.error_count,
                    "avg_duration_ms": (
                        round(stats.duration_sum_ms / stats.count, 2) if stats.count else 0.0
                    ),
                }
                for (service, operation), stats in self._by_operation.items()
            ]
        by_operation.sort(key=lambda entry: int(entry["count"]), reverse=True)
        return {
            "total_count": total,
            "error_count": errors,
            "error_rate": round(errors / total, 4) if total else 0.0,
            "avg_duration_ms": round(duration_sum / total, 2) if total else 0.0,
            "by_operation": by_operation,
        }

    def clear(self) -> None:
        with self._lock:
            self._history.clear()
            self._totals = _OperationStats()
            self._by_operation.clear()


#: One process-wide instance, mirroring `failure_injector` — every
#: ProviderService subclass shares it.
operation_recorder = OperationRecorder()
