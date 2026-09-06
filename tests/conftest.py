from __future__ import annotations

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.core.failure_injection import failure_injector
from app.main import app
from app.providers.base import CloudProvider
from app.providers.factory import get_provider


@pytest.fixture(autouse=True)
def _reset_failure_injector():
    """The failure injector (Phase 4) is a process-wide singleton — see
    app/core/failure_injection.py. Without this, a rule added by one test
    would leak into every test that runs after it in the same pytest
    process, exactly the kind of cross-test state moto's `mock_aws()` and
    the integration suite's `/moto-api/reset` already guard against."""
    failure_injector.clear()
    yield
    failure_injector.clear()


class FakeProvider(CloudProvider):
    """A CloudProvider for tests: same interface real code depends on, but
    backed by moto's in-process AWS mock instead of a real LocalStack
    container — no network, no Docker, sub-second test runs."""

    def __init__(self, region: str = "us-east-1") -> None:
        self._region = region
        self._clients: dict[str, object] = {}

    @property
    def name(self) -> str:
        return "test"

    def get_client(self, service_name: str):
        if service_name not in self._clients:
            self._clients[service_name] = boto3.client(service_name, region_name=self._region)
        return self._clients[service_name]


@pytest.fixture
def aws():
    """Activates moto's AWS mock for the duration of a test."""
    with mock_aws():
        yield


@pytest.fixture
def provider(aws):
    return FakeProvider()


@pytest.fixture
def make_provider(aws):
    """Factory version of `provider`, for the handful of tests that need a
    non-default region."""

    def _make(region: str = "us-east-1") -> FakeProvider:
        return FakeProvider(region=region)

    return _make


@pytest.fixture
def client(provider):
    """A FastAPI TestClient wired to the FakeProvider, shared by every
    tests/test_routes_*.py module. Used without `with` so the app's
    lifespan (which retries a real connectivity check) never runs — these
    are route/service tests, not a real end-to-end startup test."""
    app.dependency_overrides[get_provider] = lambda: provider
    yield TestClient(app)
    app.dependency_overrides.clear()
