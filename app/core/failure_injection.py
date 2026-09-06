"""Phase 4: failure injection layer.

The plan (Phase 4.1) calls for a layer between the application provider and
LocalStack:

    Application -> Provider -> Failure Injection Layer -> LocalStack

In this codebase that seam already exists: every provider call, for every
resource service, already funnels through `ProviderService._call()`
(app/services/base.py) — that's exactly the "every operation goes through
one instrumented helper" pattern Phase 3 generalized off of S3. So rather
than adding a second wrapper layer, `_call()` consults this module before
invoking the real boto3 call, and every service gets failure injection for
free with zero per-service code.

This is a deliberately in-process, in-memory registry — not persisted, not
distributed, not authenticated beyond "this is a local dev tool" (see the
plan's Phase 9.2 note that failure-injection endpoints should eventually be
protected; that's future work, not required for the MVP of this
capability). It resets on process restart, same as `docker compose down`
would reset everything else about the dev environment.
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
    """Process-wide registry of active failure rules, plus the evaluator
    `ProviderService._call()` consults before every real provider call.

    A `threading.Lock` guards the rule dict because FastAPI runs sync route
    handlers (every route in this app) in a thread pool — a dev-tools
    request adding a rule and a resource request evaluating rules can
    genuinely race on separate threads.
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
        """Consulted by `ProviderService._call()` before the real provider
        call. Either returns normally (no matching rule, or a probability
        roll that didn't hit), sleeps and returns (a LATENCY rule — the real
        call still happens, just slower), or sleeps (if configured) and
        raises an `AppError` that short-circuits the real call entirely
        (every other failure type).
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


#: One process-wide instance — every ProviderService subclass shares it, the
#: same way they'd share a single real failure-injection sidecar in a
#: multi-process deployment.
failure_injector = FailureInjector()
