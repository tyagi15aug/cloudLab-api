"""Fixtures for Phase 2.2 integration tests.

Unlike tests/test_*.py (which use moto's in-process `mock_aws()` — no
sockets, sub-second), these tests run a real `moto.server` process and talk
to it over real HTTP, the same way LocalStackProvider talks to a real
LocalStack container. That's the point of this suite: it exercises the
actual network path (endpoint_url, boto3 client construction, retries,
connection errors) that the unit tests bypass by design.

moto's server implements the same S3 REST surface LocalStack does, so this
is a faithful stand-in everywhere this sandbox can't pull the real
`localstack/localstack` image from Docker Hub (see the repo README). CI and
any normal dev machine can run the real thing via docker-compose instead;
nothing here is LocalStack-specific.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Iterator

import boto3
import pytest
import requests

from app.providers.localstack_provider import LocalStackProvider


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def moto_server_url() -> Iterator[str]:
    """Starts a real moto server subprocess for the whole test session."""
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "moto.server", "-p", str(port), "-H", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(50):
            try:
                requests.get(url, timeout=0.5)
                break
            except requests.exceptions.ConnectionError:
                time.sleep(0.2)
        else:
            proc.terminate()
            raise RuntimeError("moto server did not start in time")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(autouse=True)
def _reset_moto_state(moto_server_url: str) -> Iterator[None]:
    """moto's server keeps state across requests within a run; reset it
    between tests so they don't leak buckets into each other."""
    yield
    requests.post(f"{moto_server_url}/moto-api/reset")


@pytest.fixture
def localstack_provider(moto_server_url: str) -> LocalStackProvider:
    return LocalStackProvider(
        region="us-east-1",
        endpoint_url=moto_server_url,
        access_key_id="test",
        secret_access_key="test",
    )


@pytest.fixture
def raw_s3_client(moto_server_url: str):
    """A boto3 client talking to the same moto server, for setting up
    fixture state / asserting on side effects without going through the
    provider abstraction under test."""
    return boto3.client(
        "s3",
        region_name="us-east-1",
        endpoint_url=moto_server_url,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
