"""The failure injection layer — lets you make any resource call fail on
demand, for testing how the UI handles it.

Every service already funnels its provider calls through one place
(`ProviderService._call()` in app/services/base.py), so instead of
building a whole new wrapper layer for this, `_call()` just checks in
with this module before making the real boto3 call. Every service gets
failure injection for free, no per-service code needed.

This is a plain in-memory registry — no persistence, no auth beyond "this
is a local dev tool." It resets on restart, same as everything else about
the dev environment does when you bring the stack down.
"""

from __future__ import annotations

import itertools
import logging
import random
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import AppError, ErrorCode

logger = logging.getLogger("app.failure_injection")

#: Sentinel service/operation value meaning "match anything".
WILDCARD = "*"

#: Hard cap so a mistyped probability=1.0, delay_ms=30000 rule can't wedge
#: the whole API indefinitely — this is a test tool, not a network simulator.
MAX_DELAY_MS = 30_000


class FailureType(StrEnum):
    HTTP_500 = "http_500"
    HTTP_403 = "http_403"
    TIMEOUT = "timeout"
    LATENCY = "latency"
    THROTTLE = "throttle"
    CONNECTION_FAILURE = "connection_failure"


# failure type -> (AppError code, HTTP status, retryable, message). LATENCY
# has no entry here on purpose: it delays the call and then lets the real
# provider call proceed, rather than failing it (see FailureInjector.apply).
_FAILURE_ERRORS: dict[FailureType, tuple[ErrorCode, int, bool, str]] = {
    FailureType.HTTP_500: (
        ErrorCode.INTERNAL_ERROR,
        500,
        False,
        "Injected failure: internal server error.",
    ),
    FailureType.HTTP_403: (
        ErrorCode.ACCESS_DENIED,
        403,
        False,
        "Injected failure: access denied.",
    ),
    FailureType.TIMEOUT: (
        ErrorCode.PROVIDER_UNAVAILABLE,
        503,
        True,
        "Injected failure: operation timed out.",
    ),
    FailureType.THROTTLE: (
        ErrorCode.THROTTLED,
        429,
        True,
        "Injected failure: request throttled.",
    ),
    FailureType.CONNECTION_FAILURE: (
        ErrorCode.PROVIDER_UNAVAILABLE,
        503,
        True,
        "Injected failure: could not reach the provider.",
    ),
}


@dataclass
class FailureRule:
    id: str
    service: str
    operation: str
    failure: FailureType
    delay_ms: int = 0
    probability: float = 1.0
    hit_count: int = 0

    def matches(self, service: str, operation: str) -> bool:
        return self.service in (service, WILDCARD) and self.operation in (operation, WILDCARD)


class FailureInjector:
    """Process-wide registry of active failure rules, plus the check
    `ProviderService._call()` runs before every real provider call.

    Guarded by a lock because FastAPI runs its (sync) route handlers in a
    thread pool — someone adding a rule through the dev-tools API and a
    resource call checking the rules can genuinely land on different
    threads at the same time.
    """

    def __init__(self) -> None:
        self._rules: dict[str, FailureRule] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def list_rules(self) -> list[FailureRule]:
        with self._lock:
            return list(self._rules.values())

    def add_rule(
        self,
        *,
        service: str,
        operation: str,
        failure: FailureType,
        delay_ms: int = 0,
        probability: float = 1.0,
    ) -> FailureRule:
        delay_ms = min(max(delay_ms, 0), MAX_DELAY_MS)
        probability = min(max(probability, 0.0), 1.0)
        with self._lock:
            rule = FailureRule(
                id=f"fr-{next(self._ids)}",
                service=service,
                operation=operation,
                failure=failure,
                delay_ms=delay_ms,
                probability=probability,
            )
            self._rules[rule.id] = rule
            return rule

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            return self._rules.pop(rule_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._rules.clear()

    def apply(self, *, service: str, operation: str) -> None:
        """Called by `ProviderService._call()` right before the real
        provider call. Three things can happen: nothing (no matching rule,
        or a probability roll that missed), a delay and then nothing (a
        LATENCY rule — the real call still goes through, just slower), or
        a delay and then an `AppError` that stops the real call from
        happening at all (every other failure type).
        """
        with self._lock:
            matching = [r for r in self._rules.values() if r.matches(service, operation)]

        for rule in matching:
            if rule.probability < 1.0 and random.random() > rule.probability:  # noqa: S311
                continue

            with self._lock:
                # The rule may have been deleted or cleared between the
                # match check above and here; only count/apply it if it's
                # still registered.
                if rule.id not in self._rules:
                    continue
                rule.hit_count += 1

            if rule.delay_ms:
                time.sleep(rule.delay_ms / 1000)

            if rule.failure == FailureType.LATENCY:
                return

            code, status_code, retryable, message = _FAILURE_ERRORS[rule.failure]
            logger.warning(
                "Injected failure applied",
                extra={
                    "service": service,
                    "operation": operation,
                    "failure": rule.failure.value,
                    "rule_id": rule.id,
                },
            )
            raise AppError(code, message, status_code=status_code, retryable=retryable)


#: One instance for the whole process — every ProviderService subclass
#: shares it.
failure_injector = FailureInjector()
