from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.services.s3_service import S3Service


@pytest.fixture
def s3_service(provider):
    return S3Service(provider)


def test_list_buckets_empty(s3_service):
    items, cursor = s3_service.list_buckets()
    assert items == []
    assert cursor is None


def test_create_bucket_returns_resource(s3_service):
    bucket = s3_service.create_bucket("my-test-bucket")
    assert bucket.name == "my-test-bucket"
    assert bucket.id == "my-test-bucket"
    assert bucket.region == "us-east-1"
    assert bucket.created_at is not None


def test_create_then_list_includes_the_bucket(s3_service):
    s3_service.create_bucket("alpha-bucket")
    items, _ = s3_service.list_buckets()
    assert [b.name for b in items] == ["alpha-bucket"]


def test_list_buckets_is_sorted_by_name(s3_service):
    for name in ["zeta-bucket", "alpha-bucket", "mid-bucket"]:
        s3_service.create_bucket(name)

    items, _ = s3_service.list_buckets()
    assert [b.name for b in items] == ["alpha-bucket", "mid-bucket", "zeta-bucket"]


def test_list_buckets_paginates(s3_service):
    for name in ["bucket-a", "bucket-b", "bucket-c"]:
        s3_service.create_bucket(name)

    first_page, cursor = s3_service.list_buckets(page_size=2)
    assert [b.name for b in first_page] == ["bucket-a", "bucket-b"]
    assert cursor is not None

    second_page, next_cursor = s3_service.list_buckets(page_size=2, cursor=cursor)
    assert [b.name for b in second_page] == ["bucket-c"]
    assert next_cursor is None


def test_list_buckets_rejects_a_malformed_cursor(s3_service):
    with pytest.raises(AppError) as exc_info:
        s3_service.list_buckets(cursor="not-valid-base64!!")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert exc_info.value.status_code == 400


def test_delete_bucket_removes_it(s3_service):
    s3_service.create_bucket("to-delete")
    s3_service.delete_bucket("to-delete")
    items, _ = s3_service.list_buckets()
    assert items == []


def test_delete_missing_bucket_raises_not_found(s3_service):
    with pytest.raises(AppError) as exc_info:
        s3_service.delete_bucket("does-not-exist")
    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.status_code == 404
    assert exc_info.value.retryable is False


def test_get_missing_bucket_raises_not_found(s3_service):
    with pytest.raises(AppError) as exc_info:
        s3_service.get_bucket("does-not-exist")
    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_get_bucket_with_no_tags_returns_empty_dict(s3_service):
    s3_service.create_bucket("untagged-bucket")
    bucket = s3_service.get_bucket("untagged-bucket")
    assert bucket.tags == {}
    assert bucket.region == "us-east-1"


def test_get_bucket_returns_its_tags(s3_service):
    s3_service.create_bucket("tagged-bucket")
    # Tag it directly via the provider's own client, bypassing S3Service —
    # tagging isn't part of this service's API surface, only reading tags
    # back through get_bucket is.
    s3_service._client().put_bucket_tagging(
        Bucket="tagged-bucket",
        Tagging={"TagSet": [{"Key": "env", "Value": "test"}]},
    )

    bucket = s3_service.get_bucket("tagged-bucket")
    assert bucket.tags == {"env": "test"}


def test_create_bucket_in_non_default_region_sets_location_constraint(make_provider):
    service = S3Service(make_provider(region="us-west-2"))
    bucket = service.create_bucket("west-bucket")
    assert bucket.region == "us-west-2"
