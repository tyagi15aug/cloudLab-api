"""Integration test: the real FastAPI app, including its startup lifespan
(provider connectivity retry loop in app/main.py), running against a real
moto server process instead of the dependency-override shortcut
tests/test_routes_s3.py uses.

This is the closest thing in this repo to "docker compose up and curl it"
without an actual container runtime — it proves CLOUD_PROVIDER/AWS_* env
vars really do wire the app to a live endpoint end-to-end, which the
dependency-override unit tests don't exercise at all.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def live_app_client(moto_server_url: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLOUD_PROVIDER", "localstack")
    monkeypatch.setenv("AWS_ENDPOINT_URL", moto_server_url)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("STARTUP_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("STARTUP_RETRY_DELAY_SECONDS", "0.1")

    # Settings/provider are process-wide @lru_cache singletons — clear them
    # and reimport app.main fresh so it picks up the env vars above rather
    # than whatever an earlier test/module import already cached.
    from app.core.config import get_settings
    from app.providers.factory import get_provider

    get_settings.cache_clear()
    get_provider.cache_clear()

    import app.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client

    get_settings.cache_clear()
    get_provider.cache_clear()


def test_health_check_against_live_endpoint(live_app_client: TestClient) -> None:
    response = live_app_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "localstack"


def test_full_crud_through_the_real_app_over_http(live_app_client: TestClient) -> None:
    create = live_app_client.post("/api/resources/s3/buckets", json={"name": "app-lifecycle-bucket"})
    assert create.status_code == 201
    assert create.json()["name"] == "app-lifecycle-bucket"
    assert "x-request-id" in create.headers

    listed = live_app_client.get("/api/resources/s3/buckets")
    assert listed.status_code == 200
    assert [b["name"] for b in listed.json()["items"]] == ["app-lifecycle-bucket"]

    fetched = live_app_client.get("/api/resources/s3/buckets/app-lifecycle-bucket")
    assert fetched.status_code == 200

    deleted = live_app_client.delete("/api/resources/s3/buckets/app-lifecycle-bucket")
    assert deleted.status_code == 204

    missing = live_app_client.get("/api/resources/s3/buckets/app-lifecycle-bucket")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_validation_error_shape_over_real_app(live_app_client: TestClient) -> None:
    response = live_app_client.post("/api/resources/s3/buckets", json={"name": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "requestId" in body["error"]


def test_failure_injection_works_against_the_real_localstack_provider(live_app_client: TestClient) -> None:
    """The failure injector (Phase 4) hooks ProviderService._call(), which
    every service subclass shares — this proves it works identically when
    the provider underneath is the real LocalStackProvider talking over a
    real socket, not just the FakeProvider the rest of the unit suite uses.
    """
    created = live_app_client.post(
        "/api/dev/failures",
        json={"service": "s3", "operation": "CreateBucket", "failure": "http_500"},
    )
    assert created.status_code == 201

    failed = live_app_client.post("/api/resources/s3/buckets", json={"name": "injected-failure-bucket"})
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "INTERNAL_ERROR"

    # The real CreateBucket call to moto's server never went out.
    listed = live_app_client.get("/api/resources/s3/buckets")
    assert listed.json()["items"] == []

    live_app_client.delete("/api/dev/failures")
    succeeded = live_app_client.post("/api/resources/s3/buckets", json={"name": "injected-failure-bucket"})
    assert succeeded.status_code == 201
