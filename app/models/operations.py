"""Response models for the dev-only operation-history API.

Mirrors `OperationRecord` (the dataclass in app/core/operations.py) the
same way failure_injection.py's models mirror `FailureRule` — a separate
wire model even though it looks almost identical, same reasoning as
everywhere else in app/models/.
"""

from __future__ import annotations

from pydantic import BaseModel


class OperationResource(BaseModel):
    id: int
    service: str
    operation: str
    provider: str
    status: str
    duration_ms: float
    request_id: str | None = None
    resource: str | None = None
    error: str | None = None
    retryable: bool | None = None
    timestamp: float


class OperationList(BaseModel):
    items: list[OperationResource]


class OperationMetricsByOperation(BaseModel):
    service: str
    operation: str
    count: int
    error_count: int
    avg_duration_ms: float


class OperationMetrics(BaseModel):
    total_count: int
    error_count: int
    error_rate: float
    avg_duration_ms: float
    by_operation: list[OperationMetricsByOperation]
