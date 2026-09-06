"""Developer-only failure-injection API.

Namespaced under `/api/dev/` instead of `/api/resources/` on purpose —
this isn't a cloud resource, it's a testing capability that controls how
the *other* routes behave. It's unauthenticated for now; locking it down
(or dropping it from a public build) is on the list, just not done yet.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.errors import AppError, ErrorCode
from app.core.failure_injection import failure_injector
from app.models.failure_injection import (
    CreateFailureRuleRequest,
    FailureRuleList,
    FailureRuleResource,
)

router = APIRouter(prefix="/api/dev/failures", tags=["dev"])


def _to_resource(rule) -> FailureRuleResource:  # noqa: ANN001 - FailureRule is a plain dataclass
    return FailureRuleResource(
        id=rule.id,
        service=rule.service,
        operation=rule.operation,
        failure=rule.failure,
        delay_ms=rule.delay_ms,
        probability=rule.probability,
        hit_count=rule.hit_count,
    )


@router.get("", response_model=FailureRuleList)
def list_failures() -> FailureRuleList:
    return FailureRuleList(items=[_to_resource(r) for r in failure_injector.list_rules()])


@router.post("", response_model=FailureRuleResource, status_code=status.HTTP_201_CREATED)
def create_failure(body: CreateFailureRuleRequest) -> FailureRuleResource:
    rule = failure_injector.add_rule(
        service=body.service,
        operation=body.operation,
        failure=body.failure,
        delay_ms=body.delay_ms,
        probability=body.probability,
    )
    return _to_resource(rule)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def clear_failures() -> None:
    failure_injector.clear()


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_failure(rule_id: str) -> None:
    if not failure_injector.delete_rule(rule_id):
        raise AppError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"No failure rule with id '{rule_id}'.",
            status_code=404,
            retryable=False,
        )
