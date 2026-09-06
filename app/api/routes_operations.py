"""Developer-only operation-history and metrics API.

Namespaced under `/api/dev/` for the same reason as `/api/dev/failures` —
this exposes internal process state for diagnostics, it isn't a cloud
resource. Same unauthenticated-for-now situation too.

One ordering gotcha: `/metrics` has to be declared before `/{operation_id}`
below, or a request for it would get swallowed by the parameterized route.
FastAPI tries routes in the order they're declared, and `/metrics` failing
the `int` conversion `{operation_id}` expects doesn't save you if that
route came first.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.core.errors import AppError, ErrorCode
from app.core.operations import OperationMetricsSnapshot, OperationRecord, operation_recorder
from app.models.operations import (
    OperationList,
    OperationMetrics,
    OperationMetricsByOperation,
    OperationResource,
)

router = APIRouter(prefix="/api/dev/operations", tags=["dev"])


def _to_resource(record: OperationRecord) -> OperationResource:
    return OperationResource(
        id=record.id,
        service=record.service,
        operation=record.operation,
        provider=record.provider,
        status=record.status,
        duration_ms=record.duration_ms,
        request_id=record.request_id,
        resource=record.resource,
        error=record.error,
        retryable=record.retryable,
        timestamp=record.timestamp,
    )


def _to_metrics_resource(snapshot: OperationMetricsSnapshot) -> OperationMetrics:
    return OperationMetrics(
        total_count=snapshot.total_count,
        error_count=snapshot.error_count,
        error_rate=snapshot.error_rate,
        avg_duration_ms=snapshot.avg_duration_ms,
        by_operation=[
            OperationMetricsByOperation(
                service=entry.service,
                operation=entry.operation,
                count=entry.count,
                error_count=entry.error_count,
                avg_duration_ms=entry.avg_duration_ms,
            )
            for entry in snapshot.by_operation
        ],
    )


@router.get("", response_model=OperationList)
def list_operations(limit: int = Query(default=50, ge=1, le=200)) -> OperationList:
    return OperationList(items=[_to_resource(r) for r in operation_recorder.list_recent(limit=limit)])


@router.get("/metrics", response_model=OperationMetrics)
def get_metrics() -> OperationMetrics:
    return _to_metrics_resource(operation_recorder.metrics())


@router.get("/{operation_id}", response_model=OperationResource)
def get_operation(operation_id: int) -> OperationResource:
    record = operation_recorder.get(operation_id)
    if record is None:
        raise AppError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"No operation with id '{operation_id}' — it may have aged out of history.",
            status_code=404,
            retryable=False,
        )
    return _to_resource(record)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def clear_operations() -> None:
    operation_recorder.clear()
