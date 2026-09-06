"""Integration tests: real LocalStackProvider, real S3Service, real HTTP
wire calls against a real moto server process (see conftest.py for why
moto-server rather than moto's in-process mock, and how it stands in for a
real LocalStack container in this sandbox).

These are intentionally a *thin* second layer on top of
tests/test_s3_service.py's exhaustive logic coverage — the goal here isn't
to re-test every branch, it's to prove the provider abstraction actually
works end-to-end over a socket: client construction, endpoint_url routing,
and the full CRUD lifecycle against something that behaves like a real AWS
endpoint rather than an in-process patch.
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.providers.localstack_provider import LocalStackProvider
from app.services.s3_service import S3Service


def test_provider_name(localstack_provider: LocalStackProvider) -> None:
    assert localstack_provider.name == "localstack"


def test_client_is_cached(localstack_provider: LocalStackProvider) -> None:
    # Calling get_client twice for the same service must not construct a
    # second boto3 client (S3Service relies on this to avoid reconnecting
    # per-call).
    assert localstack_provider.get_client("s3") is localstack_provider.get_client("s3")


def test_full_bucket_lifecycle_over_real_http(localstack_provider: LocalStackProvider) -> None:
    service = S3Service(localstack_provider)

    buckets, cursor = service.list_buckets()
    assert buckets == []
    assert cursor is None

    created = service.create_bucket("integration-test-bucket")
    assert created.name == "integration-test-bucket"
    assert created.region == "us-east-1"

    buckets, _ = service.list_buckets()
    assert [b.name for b in buckets] == ["integration-test-bucket"]

    fetched = service.get_bucket("integration-test-bucket")
    assert fetched.name == "integration-test-bucket"
    assert fetched.tags == {}

    service.delete_bucket("integration-test-bucket")

    buckets, _ = service.list_buckets()
    assert buckets == []


def test_get_nonexistent_bucket_maps_to_404_over_real_http(
    localstack_provider: LocalStackProvider,
) -> None:
    service = S3Service(localstack_provider)

    with pytest.raises(AppError) as exc_info:
        service.get_bucket("does-not-exist-anywhere")

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_create_duplicate_bucket_maps_to_conflict_over_real_http(
    moto_server_url: str,
) -> None:
    # Real S3 (and moto's server, faithfully) treats CreateBucket on an
    # already-owned bucket as an idempotent no-op *only* in us-east-1 —
    # every other region raises BucketAlreadyOwnedByYou. Use a non-default
    # region here so this test actually exercises the conflict-mapping path
    # (app/core/errors.py) rather than AWS's us-east-1 special case.
    provider = LocalStackProvider(
        region="us-west-2",
        endpoint_url=moto_server_url,
        access_key_id="test",
        secret_access_key="test",
    )
    service = S3Service(provider)
    service.create_bucket("dup-bucket")

    with pytest.raises(AppError) as exc_info:
        service.create_bucket("dup-bucket")

    assert exc_info.value.code == ErrorCode.RESOURCE_ALREADY_EXISTS


def test_pagination_across_many_buckets_over_real_http(
    localstack_provider: LocalStackProvider,
) -> None:
    service = S3Service(localstack_provider)
    for i in range(5):
        service.create_bucket(f"page-bucket-{i}")

    page1, cursor1 = service.list_buckets(page_size=2)
    assert [b.name for b in page1] == ["page-bucket-0", "page-bucket-1"]
    assert cursor1 is not None

    page2, cursor2 = service.list_buckets(page_size=2, cursor=cursor1)
    assert [b.name for b in page2] == ["page-bucket-2", "page-bucket-3"]
    assert cursor2 is not None

    page3, cursor3 = service.list_buckets(page_size=2, cursor=cursor2)
    assert [b.name for b in page3] == ["page-bucket-4"]
    assert cursor3 is None
