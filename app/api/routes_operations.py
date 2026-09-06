"""Phase 5: developer-only operation-history and metrics API.

Namespaced under `/api/dev/` for the same reason as `/api/dev/failures`
(plan Section 13, "Developer endpoints can be separated") — this exposes
internal process state for diagnostics, not a cloud resource. Same
unauthenticated-for-now posture as the failure-injection API; see that
module's docstring for why that's acceptable at this stage (Phase 9
follow-up).

`/metrics` is declared before `/{operation_id}` so a request for it can
never be swallowed by the parameterized route — FastAPI/Starlette tries
routes in declaration order, and `/metrics` failing `operation_id`'s `int`
conversion would otherwise fall through in the wrong direction if the
order were reversed.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.core.errors import AppError, ErrorCode
from app.core.operations import OperationRecord, operation_recorder
from app.models.operations import OperationList, OperationMetrics, OperationResource

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


@router.get("", response_model=OperationList)
def list_operations(limit: int = Query(default=50, ge=1, le=200)) -> OperationList:
    return OperationList(items=[_to_resource(r) for r in operation_recorder.list_recent(limit=limit)])


@router.get("/metrics", response_model=OperationMetrics)
def get_metrics() -> OperationMetrics:
    return OperationMetrics(**operation_recorder.metrics())


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
