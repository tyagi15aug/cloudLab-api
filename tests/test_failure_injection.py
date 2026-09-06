"""Unit tests for the Phase 4 failure-injection registry/evaluator itself,
independent of HTTP or any real provider — see tests/test_routes_dev.py for
the route-level tests that prove it actually short-circuits a real
provider call end to end.
"""

from __future__ import annotations

import time

import pytest

from app.core.errors import AppError, ErrorCode
from app.core.failure_injection import FailureInjector, FailureType


@pytest.fixture
def injector() -> FailureInjector:
    return FailureInjector()


def test_no_rules_means_apply_is_a_no_op(injector: FailureInjector) -> None:
    injector.apply(service="s3", operation="CreateBucket")  # must not raise


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_status", "expected_retryable"),
    [
        (FailureType.HTTP_500, ErrorCode.INTERNAL_ERROR, 500, False),
        (FailureType.HTTP_403, ErrorCode.ACCESS_DENIED, 403, False),
        (FailureType.TIMEOUT, ErrorCode.PROVIDER_UNAVAILABLE, 503, True),
        (FailureType.THROTTLE, ErrorCode.THROTTLED, 429, True),
        (FailureType.CONNECTION_FAILURE, ErrorCode.PROVIDER_UNAVAILABLE, 503, True),
    ],
)
def test_each_failure_type_raises_the_right_app_error(
    injector: FailureInjector,
    failure: FailureType,
    expected_code: ErrorCode,
    expected_status: int,
    expected_retryable: bool,
) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=failure)

    with pytest.raises(AppError) as excinfo:
        injector.apply(service="s3", operation="CreateBucket")

    assert excinfo.value.code == expected_code
    assert excinfo.value.status_code == expected_status
    assert excinfo.value.retryable is expected_retryable


def test_latency_delays_but_does_not_raise(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.LATENCY, delay_ms=50)

    start = time.perf_counter()
    injector.apply(service="s3", operation="CreateBucket")  # must not raise
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms >= 50


def test_timeout_also_delays_before_raising(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.TIMEOUT, delay_ms=50)

    start = time.perf_counter()
    with pytest.raises(AppError):
        injector.apply(service="s3", operation="CreateBucket")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms >= 50


def test_rule_only_matches_its_own_service_and_operation(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.HTTP_500)

    injector.apply(service="sqs", operation="CreateBucket")  # different service
    injector.apply(service="s3", operation="DeleteBucket")  # different operation

    with pytest.raises(AppError):
        injector.apply(service="s3", operation="CreateBucket")


def test_wildcard_service_matches_every_service(injector: FailureInjector) -> None:
    injector.add_rule(service="*", operation="CreateBucket", failure=FailureType.HTTP_500)

    with pytest.raises(AppError):
        injector.apply(service="s3", operation="CreateBucket")
    with pytest.raises(AppError):
        injector.apply(service="sqs", operation="CreateBucket")


def test_wildcard_operation_matches_every_operation_on_the_service(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="*", failure=FailureType.HTTP_500)

    with pytest.raises(AppError):
        injector.apply(service="s3", operation="CreateBucket")
    with pytest.raises(AppError):
        injector.apply(service="s3", operation="ListBuckets")


def test_probability_zero_never_fires(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.HTTP_500, probability=0.0)

    for _ in range(20):
        injector.apply(service="s3", operation="CreateBucket")  # must never raise


def test_probability_one_always_fires(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.HTTP_500, probability=1.0)

    for _ in range(20):
        with pytest.raises(AppError):
            injector.apply(service="s3", operation="CreateBucket")


def test_hit_count_increments_only_when_the_rule_actually_fires(injector: FailureInjector) -> None:
    rule = injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.HTTP_500)

    assert rule.hit_count == 0
    with pytest.raises(AppError):
        injector.apply(service="s3", operation="CreateBucket")
    assert rule.hit_count == 1

    injector.apply(service="s3", operation="DeleteBucket")  # doesn't match; no increment
    assert rule.hit_count == 1


def test_delete_rule_removes_it(injector: FailureInjector) -> None:
    rule = injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.HTTP_500)

    assert injector.delete_rule(rule.id) is True
    injector.apply(service="s3", operation="CreateBucket")  # must not raise

    assert injector.delete_rule(rule.id) is False  # already gone


def test_clear_removes_every_rule(injector: FailureInjector) -> None:
    injector.add_rule(service="s3", operation="CreateBucket", failure=FailureType.HTTP_500)
    injector.add_rule(service="sqs", operation="*", failure=FailureType.HTTP_403)

    injector.clear()

    assert injector.list_rules() == []
    injector.apply(service="s3", operation="CreateBucket")
    injector.apply(service="sqs", operation="SendMessage")


def test_delay_ms_and_probability_are_clamped_to_sane_ranges(injector: FailureInjector) -> None:
    rule = injector.add_rule(
        service="s3", operation="CreateBucket", failure=FailureType.LATENCY, delay_ms=999_999, probability=5.0
    )

    assert rule.delay_ms == 30_000
    assert rule.probability == 1.0

    rule2 = injector.add_rule(
        service="s3", operation="DeleteBucket", failure=FailureType.LATENCY, delay_ms=-10, probability=-1.0
    )
    assert rule2.delay_ms == 0
    assert rule2.probability == 0.0
