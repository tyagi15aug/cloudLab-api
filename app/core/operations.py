"""In-process operation history and metrics.

`log_operation` (app/core/logging.py) already builds a
request_id/operation/service/resource/provider/duration/status/error
event and writes it to stdout as JSON. This module keeps the same event
in memory too, so a developer — or an E2E test — can ask "what just
happened" over HTTP instead of grepping logs.

Wired in the same spot as failure injection: `ProviderService._call()`
calls `operation_recorder.record(...)` right next to `log_operation(...)`,
so every service gets this for free. Anything the failure injector hit
shows up here too, with status="error" and the injected error's code —
by the time `_call()` is logging the outcome, it genuinely can't tell an
injected failure from a real one, and that's fine; it's what actually
happened to the request.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass, field

#: How many recent operations to keep in memory. This is a dev/demo panel,
#: not a production metrics store, so this just needs to cover a browsing
#: session without growing forever. The cumulative counters below
#: (`_totals`, `_by_operation`) don't get evicted along with old history,
#: so `metrics()` stays accurate for the process's whole life even past
#: MAX_HISTORY operations.
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
    """A ring buffer of recent operations for the whole process, plus
    running totals per operation.

    Locked the same way `FailureInjector` is — route handlers run in a
    thread pool, so two resource calls recording at the same instant is a
    real thing that happens, not just a theoretical race.
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


#: One instance for the whole process, same as `failure_injector` — every
#: ProviderService subclass shares it.
operation_recorder = OperationRecorder()
