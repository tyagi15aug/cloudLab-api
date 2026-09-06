"""Phase 5: unit tests for `OperationRecorder` in isolation — no HTTP, no
provider, just the ring buffer and metrics math (mirrors how
test_failure_injection.py tests `FailureInjector` in isolation in Phase 4).
"""

from __future__ import annotations

from app.core.operations import MAX_HISTORY, OperationRecorder


def _record(recorder: OperationRecorder, **overrides) -> None:
    defaults = {
        "service": "s3",
        "operation": "ListBuckets",
        "provider": "test",
        "status": "success",
        "duration_ms": 10.0,
    }
    defaults.update(overrides)
    recorder.record(**defaults)


def test_empty_recorder_has_no_history_and_zeroed_metrics():
    recorder = OperationRecorder()
    assert recorder.list_recent() == []
    metrics = recorder.metrics()
    assert metrics["total_count"] == 0
    assert metrics["error_count"] == 0
    assert metrics["error_rate"] == 0.0
    assert metrics["avg_duration_ms"] == 0.0
    assert metrics["by_operation"] == []


def test_list_recent_returns_newest_first():
    recorder = OperationRecorder()
    _record(recorder, operation="ListBuckets")
    _record(recorder, operation="CreateBucket")
    _record(recorder, operation="DeleteBucket")

    ops = [r.operation for r in recorder.list_recent()]
    assert ops == ["DeleteBucket", "CreateBucket", "ListBuckets"]


def test_list_recent_respects_limit():
    recorder = OperationRecorder()
    for i in range(5):
        _record(recorder, operation=f"Op{i}")

    assert len(recorder.list_recent(limit=2)) == 2


def test_ring_buffer_evicts_oldest_beyond_max_history():
    recorder = OperationRecorder(max_history=3)
    for i in range(5):
        _record(recorder, operation=f"Op{i}")

    ops = [r.operation for r in recorder.list_recent(limit=10)]
    # Newest-first, only the last 3 survive.
    assert ops == ["Op4", "Op3", "Op2"]


def test_get_finds_a_recorded_operation_by_id():
    recorder = OperationRecorder()
    _record(recorder, operation="CreateBucket", resource="demo")

    recorded = recorder.list_recent()[0]
    found = recorder.get(recorded.id)

    assert found is not None
    assert found.operation == "CreateBucket"
    assert found.resource == "demo"


def test_get_returns_none_for_unknown_or_evicted_id():
    recorder = OperationRecorder()
    _record(recorder)

    assert recorder.get(999) is None


def test_get_returns_none_once_evicted_from_ring_buffer():
    recorder = OperationRecorder(max_history=1)
    _record(recorder, operation="First")
    first_id = recorder.list_recent()[0].id
    _record(recorder, operation="Second")

    assert recorder.get(first_id) is None


def test_metrics_counts_totals_and_error_rate():
    recorder = OperationRecorder()
    _record(recorder, status="success", duration_ms=10.0)
    _record(recorder, status="success", duration_ms=20.0)
    _record(recorder, status="error", duration_ms=30.0, error="INTERNAL_ERROR", retryable=False)

    metrics = recorder.metrics()
    assert metrics["total_count"] == 3
    assert metrics["error_count"] == 1
    assert metrics["error_rate"] == round(1 / 3, 4)
    assert metrics["avg_duration_ms"] == 20.0  # (10+20+30)/3


def test_metrics_totals_survive_ring_buffer_eviction():
    """The whole reason totals are tracked separately from the ring buffer
    — a long-running process should report accurate lifetime counts even
    after old records have aged out of `list_recent()`."""
    recorder = OperationRecorder(max_history=2)
    for _ in range(5):
        _record(recorder, status="success", duration_ms=10.0)

    assert len(recorder.list_recent(limit=10)) == 2
    assert recorder.metrics()["total_count"] == 5


def test_metrics_breaks_down_by_service_and_operation():
    recorder = OperationRecorder()
    _record(recorder, service="s3", operation="ListBuckets", duration_ms=10.0)
    _record(recorder, service="s3", operation="ListBuckets", duration_ms=30.0)
    _record(recorder, service="sqs", operation="ListQueues", duration_ms=5.0)

    by_operation = {(e["service"], e["operation"]): e for e in recorder.metrics()["by_operation"]}

    s3_list = by_operation[("s3", "ListBuckets")]
    assert s3_list["count"] == 2
    assert s3_list["avg_duration_ms"] == 20.0

    sqs_list = by_operation[("sqs", "ListQueues")]
    assert sqs_list["count"] == 1


def test_by_operation_sorted_by_count_descending():
    recorder = OperationRecorder()
    _record(recorder, service="s3", operation="ListBuckets")
    _record(recorder, service="sqs", operation="ListQueues")
    _record(recorder, service="sqs", operation="ListQueues")
    _record(recorder, service="sqs", operation="ListQueues")

    by_operation = recorder.metrics()["by_operation"]
    assert by_operation[0]["operation"] == "ListQueues"
    assert by_operation[0]["count"] == 3


def test_clear_resets_history_and_metrics():
    recorder = OperationRecorder()
    _record(recorder, status="error", error="INTERNAL_ERROR")

    recorder.clear()

    assert recorder.list_recent() == []
    metrics = recorder.metrics()
    assert metrics["total_count"] == 0
    assert metrics["by_operation"] == []


def test_default_max_history_matches_module_constant():
    recorder = OperationRecorder()
    for _ in range(MAX_HISTORY + 10):
        _record(recorder)

    assert len(recorder.list_recent(limit=MAX_HISTORY + 10)) == MAX_HISTORY
    assert recorder.metrics()["total_count"] == MAX_HISTORY + 10


def test_records_carry_request_id_and_retryable_flag_through():
    recorder = OperationRecorder()
    _record(recorder, status="error", request_id="req-abc", error="THROTTLED", retryable=True)

    recorded = recorder.list_recent()[0]
    assert recorded.request_id == "req-abc"
    assert recorded.retryable is True
