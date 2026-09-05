from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from app.providers.base import CloudProvider


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
