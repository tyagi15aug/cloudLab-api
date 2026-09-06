"""HTTP client for cloudctl.

Talks to the real Cloud Control Plane API over plain HTTP using only the
standard library (`urllib`) — see cli/README.md's "Why stdlib-only" note.

This is the half of Phase 7.2's design principle ("call the same
application APIs/services where practical") that's actually about the
API: `resources`, `failure`, and `/health` have no existing script or
implementation to reuse, so this client is a thin, honest peer of the
React console — same endpoints, same error envelope, no shortcuts through
app internals.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

Method = Literal["GET", "POST", "DELETE"]

DEFAULT_API_URL = "http://localhost:8000"

#: Friendly aliases for FailureType values, so `cloudctl failure inject s3
#: CreateBucket 500` (the plan's own Section 7.1 example) works verbatim
#: alongside the API's real enum values (app/core/failure_injection.py).
FAILURE_ALIASES: dict[str, str] = {"500": "http_500", "403": "http_403"}


class CloudctlAPIError(Exception):
    """Raised for a non-2xx response or an unreachable API.

    Wraps the app's `{"error": {code, message, ...}}` envelope (see
    app/models/resource.py's `ErrorResponse`) when one is present, so the
    person running the CLI sees the same message the React console would
    show — not a raw urllib traceback.
    """

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass
class ApiClient:
    base_url: str = DEFAULT_API_URL
    timeout: float = 10.0

    def _request(self, method: Method, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            message, status_code, code = _describe_http_error(exc)
            raise CloudctlAPIError(message, status_code=status_code, code=code) from exc
        except urllib.error.URLError as exc:
            raise CloudctlAPIError(
                f"Could not reach the API at {self.base_url} ({exc.reason}). "
                "Is the stack up? Try `cloudctl status` or `cloudctl up`.",
            ) from exc

    # -- health -----------------------------------------------------------
    def health(self) -> Any:
        return self._request("GET", "/health")

    # -- resources ----------------------------------------------------------
    # First page only (default page_size), matching this project's demo
    # scale (see scripts/seed.sh) rather than adding pagination the CLI's
    # own commands don't yet need.
    def list_buckets(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/resources/s3/buckets")["items"]

    def list_queues(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/resources/sqs/queues")["items"]

    def list_tables(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/resources/dynamodb/tables")["items"]

    # -- failure injection ----------------------------------------------------
    def list_failures(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/dev/failures")["items"]

    def create_failure(
        self,
        *,
        service: str,
        operation: str,
        failure: str,
        delay_ms: int = 0,
        probability: float = 1.0,
    ) -> dict[str, Any]:
        failure = FAILURE_ALIASES.get(failure, failure)
        return self._request(
            "POST",
            "/api/dev/failures",
            json_body={
                "service": service,
                "operation": operation,
                "failure": failure,
                "delay_ms": delay_ms,
                "probability": probability,
            },
        )

    def clear_failures(self) -> None:
        self._request("DELETE", "/api/dev/failures")

    def delete_failure(self, rule_id: str) -> None:
        self._request("DELETE", f"/api/dev/failures/{rule_id}")

    # -- operations (Phase 5) ------------------------------------------------
    # Not wired to a command yet — `cloudctl status` uses /health only —
    # but exposed here since a future `cloudctl operations` or the Phase 6
    # CI analyzer is a natural client of this same method.
    def operation_metrics(self) -> dict[str, Any]:
        return self._request("GET", "/api/dev/operations/metrics")


def _describe_http_error(exc: urllib.error.HTTPError) -> tuple[str, int, str | None]:
    raw = exc.read()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return error["message"], exc.code, error.get("code")
    detail = raw.decode("utf-8", errors="replace").strip()
    message = f"HTTP {exc.code}" + (f": {detail}" if detail else "")
    return message, exc.code, None
