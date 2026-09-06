"""Route-level tests for the Phase 4 failure-injection API — proves a rule
created through `/api/dev/failures` actually short-circuits a real resource
route (`/api/resources/...`) over real HTTP, not just that the injector
class works in isolation (see tests/test_failure_injection.py for that).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_starts_empty(client: TestClient) -> None:
    response = client.get("/api/dev/failures")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_injected_failure_short_circuits_the_real_route(client: TestClient) -> None:
    created = client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "http_500"},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert created.json()["hit_count"] == 0

    response = client.post("/api/resources/s3/buckets", json={"name": "should-not-exist"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"

    # The real CreateBucket call never happened.
    listed = client.get("/api/resources/s3/buckets")
    assert listed.json()["items"] == []

    rules = client.get("/api/dev/failures").json()["items"]
    assert rules[0]["id"] == rule_id
    assert rules[0]["hit_count"] == 1


def test_injected_failure_does_not_affect_other_operations(client: TestClient) -> None:
    client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "http_403"},
    )

    # A completely different operation on the same service is unaffected.
    listed = client.get("/api/resources/s3/buckets")
    assert listed.status_code == 200

    # A different service is unaffected.
    queues = client.get("/api/resources/sqs/queues")
    assert queues.status_code == 200


def test_deleting_the_rule_restores_normal_behavior(client: TestClient) -> None:
    created = client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "http_500"},
    )
    rule_id = created.json()["id"]

    failed = client.post("/api/resources/s3/buckets", json={"name": "retry-bucket"})
    assert failed.status_code == 500

    deleted = client.delete(f"/api/dev/failures/{rule_id}")
    assert deleted.status_code == 204

    retried = client.post("/api/resources/s3/buckets", json={"name": "retry-bucket"})
    assert retried.status_code == 201


def test_deleting_an_unknown_rule_is_a_404(client: TestClient) -> None:
    response = client.delete("/api/dev/failures/fr-does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_clear_removes_every_rule(client: TestClient) -> None:
    client.post("/api/dev/failures", json={"service": "s3", "operation": "*", "failure": "http_500"})
    client.post("/api/dev/failures", json={"service": "sqs", "operation": "*", "failure": "http_403"})

    cleared = client.delete("/api/dev/failures")
    assert cleared.status_code == 204

    assert client.get("/api/dev/failures").json() == {"items": []}
    assert client.get("/api/resources/s3/buckets").status_code == 200
    assert client.get("/api/resources/sqs/queues").status_code == 200


def test_wildcard_operation_affects_every_operation_on_the_service(client: TestClient) -> None:
    client.post("/api/dev/failures", json={"service": "sqs", "operation": "*", "failure": "http_403"})

    listed = client.get("/api/resources/sqs/queues")
    created = client.post("/api/resources/sqs/queues", json={"name": "orders"})

    assert listed.status_code == 403
    assert created.status_code == 403


def test_probability_zero_never_triggers_the_failure(client: TestClient) -> None:
    client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "http_500", "probability": 0.0},
    )

    response = client.post("/api/resources/s3/buckets", json={"name": "always-succeeds"})
    assert response.status_code == 201


def test_throttled_failure_is_marked_retryable(client: TestClient) -> None:
    client.post(
        "/api/dev/failures", json={"service": "s3", "operation": "ListBuckets", "failure": "throttle"}
    )

    response = client.get("/api/resources/s3/buckets")
    assert response.status_code == 429
    body = response.json()["error"]
    assert body["code"] == "THROTTLED"
    assert body["retryable"] is True


def test_latency_delays_but_still_succeeds(client: TestClient) -> None:
    client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "latency", "delay_ms": 50},
    )

    response = client.post("/api/resources/s3/buckets", json={"name": "slow-bucket"})
    assert response.status_code == 201


def test_create_failure_rejects_an_invalid_probability(client: TestClient) -> None:
    response = client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "http_500", "probability": 1.5},
    )
    assert response.status_code == 422


def test_create_failure_rejects_an_unknown_failure_type(client: TestClient) -> None:
    response = client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "nonsense"},
    )
    assert response.status_code == 422
