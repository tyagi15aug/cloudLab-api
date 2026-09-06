"""Route-level tests for the Phase 5 operation-history API — proves real
resource calls made through the app actually show up in
`/api/dev/operations`/`/metrics`/`/{id}`, not just that `OperationRecorder`
works in isolation (see tests/test_operations.py for that).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_history_starts_empty(client: TestClient) -> None:
    response = client.get("/api/dev/operations")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_metrics_start_zeroed(client: TestClient) -> None:
    response = client.get("/api/dev/operations/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 0
    assert body["error_count"] == 0
    assert body["by_operation"] == []


def test_a_real_call_is_recorded_in_history(client: TestClient) -> None:
    client.post("/api/resources/s3/buckets", json={"name": "demo-bucket"})

    items = client.get("/api/dev/operations").json()["items"]
    assert len(items) == 1
    record = items[0]
    assert record["service"] == "s3"
    assert record["operation"] == "CreateBucket"
    assert record["status"] == "success"
    assert record["resource"] == "demo-bucket"
    assert record["duration_ms"] >= 0
    assert record["error"] is None


def test_history_is_newest_first(client: TestClient) -> None:
    client.get("/api/resources/s3/buckets")
    client.post("/api/resources/s3/buckets", json={"name": "demo-bucket"})

    operations = [r["operation"] for r in client.get("/api/dev/operations").json()["items"]]
    assert operations[0] == "CreateBucket"
    assert operations[-1] == "ListBuckets"


def test_history_respects_limit_query_param(client: TestClient) -> None:
    for i in range(5):
        client.post("/api/resources/s3/buckets", json={"name": f"bucket-{i}"})

    items = client.get("/api/dev/operations", params={"limit": 2}).json()["items"]
    assert len(items) == 2


def test_an_error_is_recorded_with_its_error_code_and_retryable_flag(client: TestClient) -> None:
    client.post(
        "/api/dev/failures", json={"service": "s3", "operation": "ListBuckets", "failure": "throttle"}
    )

    client.get("/api/resources/s3/buckets")

    record = client.get("/api/dev/operations").json()["items"][0]
    assert record["status"] == "error"
    assert record["error"] == "THROTTLED"
    assert record["retryable"] is True


def test_operation_carries_the_requests_own_request_id(client: TestClient) -> None:
    response = client.post("/api/resources/s3/buckets", json={"name": "demo-bucket"})
    request_id = response.headers["x-request-id"]

    record = client.get("/api/dev/operations").json()["items"][0]
    assert record["request_id"] == request_id


def test_get_operation_detail_by_id(client: TestClient) -> None:
    client.post("/api/resources/s3/buckets", json={"name": "demo-bucket"})
    operation_id = client.get("/api/dev/operations").json()["items"][0]["id"]

    response = client.get(f"/api/dev/operations/{operation_id}")
    assert response.status_code == 200
    assert response.json()["id"] == operation_id
    assert response.json()["operation"] == "CreateBucket"


def test_get_operation_detail_404s_for_an_unknown_id(client: TestClient) -> None:
    response = client.get("/api/dev/operations/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_metrics_reflect_real_calls_across_services(client: TestClient) -> None:
    client.post("/api/resources/s3/buckets", json={"name": "demo-bucket"})
    client.get("/api/resources/s3/buckets")
    client.get("/api/resources/sqs/queues")

    metrics = client.get("/api/dev/operations/metrics").json()
    assert metrics["total_count"] == 3
    assert metrics["error_count"] == 0

    by_operation = {(e["service"], e["operation"]) for e in metrics["by_operation"]}
    assert ("s3", "CreateBucket") in by_operation
    assert ("s3", "ListBuckets") in by_operation
    assert ("sqs", "ListQueues") in by_operation


def test_clear_empties_history_and_resets_metrics(client: TestClient) -> None:
    client.post("/api/resources/s3/buckets", json={"name": "demo-bucket"})

    cleared = client.delete("/api/dev/operations")
    assert cleared.status_code == 204

    assert client.get("/api/dev/operations").json() == {"items": []}
    assert client.get("/api/dev/operations/metrics").json()["total_count"] == 0


def test_failed_and_successful_calls_on_the_same_operation_both_count(client: TestClient) -> None:
    client.post(
        "/api/dev/failures", json={"service": "s3", "operation": "CreateBucket", "failure": "http_500"}
    )
    client.post("/api/resources/s3/buckets", json={"name": "will-fail"})
    client.delete("/api/dev/failures")
    client.post("/api/resources/s3/buckets", json={"name": "will-succeed"})

    metrics = client.get("/api/dev/operations/metrics").json()
    create_bucket = next(e for e in metrics["by_operation"] if e["operation"] == "CreateBucket")
    assert create_bucket["count"] == 2
    assert create_bucket["error_count"] == 1
