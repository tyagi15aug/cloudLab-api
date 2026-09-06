from __future__ import annotations

import pytest


def test_health_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "test"}


def test_full_bucket_lifecycle(client):
    assert client.get("/api/resources/s3/buckets").json() == {"items": [], "next_cursor": None}

    create_response = client.post("/api/resources/s3/buckets", json={"name": "lifecycle-bucket"})
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "lifecycle-bucket"

    list_response = client.get("/api/resources/s3/buckets")
    assert [b["name"] for b in list_response.json()["items"]] == ["lifecycle-bucket"]

    get_response = client.get("/api/resources/s3/buckets/lifecycle-bucket")
    assert get_response.status_code == 200
    assert get_response.json()["tags"] == {}

    delete_response = client.delete("/api/resources/s3/buckets/lifecycle-bucket")
    assert delete_response.status_code == 204
    assert delete_response.content == b""

    assert client.get("/api/resources/s3/buckets").json()["items"] == []


def test_get_missing_bucket_returns_unified_error_shape(client):
    response = client.get("/api/resources/s3/buckets/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert body["error"]["retryable"] is False
    assert "requestId" in body["error"]


def test_delete_missing_bucket_returns_404(client):
    response = client.delete("/api/resources/s3/buckets/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize("body", [{"name": "ab"}, {}, {"name": "x" * 64}])
def test_create_bucket_validation_errors_use_unified_shape(client, body):
    response = client.post("/api/resources/s3/buckets", json=body)
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["retryable"] is False


def test_response_carries_a_request_id_header(client):
    response = client.get("/health")
    assert response.headers.get("x-request-id")


def test_pagination_query_params(client):
    for i in range(3):
        client.post("/api/resources/s3/buckets", json={"name": f"page-bucket-{i}"})

    first = client.get("/api/resources/s3/buckets", params={"page_size": 2})
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor

    second = client.get("/api/resources/s3/buckets", params={"page_size": 2, "cursor": cursor})
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None
