"""S3 application service (Phase 1.3).

This is the only place in the codebase that should import botocore
exception types or know an AWS error code like "BucketAlreadyExists" exists
— routes call this service, this service calls the CloudProvider, and every
boto3/botocore detail is translated or absorbed before it goes back up.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError

from app.core.errors import ErrorCode, AppError, translate_boto_error
from app.core.logging import elapsed_ms, log_operation, timed_ms
from app.models.resource import BucketResource
from app.providers.base import CloudProvider

logger = logging.getLogger("app.services.s3")

DEFAULT_PAGE_SIZE = 50


class S3Service:
    def __init__(self, provider: CloudProvider) -> None:
        self._provider = provider

    def _client(self):
        return self._provider.get_client("s3")

    # -- internal helper: every provider call goes through here so timing,
    # structured logging, and error translation happen exactly once. -------
    def _call(self, operation: str, fn, *, resource: str | None = None):
        start = timed_ms()
        try:
            result = fn()
        except (ClientError, BotoCoreError) as exc:
            app_error = translate_boto_error(exc, resource=resource)
            log_operation(
                logger,
                operation=operation,
                service="s3",
                provider=self._provider.name,
                duration_ms=elapsed_ms(start),
                status="error",
                resource=resource,
                error=app_error.code.value,
            )
            raise app_error from exc
        else:
            log_operation(
                logger,
                operation=operation,
                service="s3",
                provider=self._provider.name,
                duration_ms=elapsed_ms(start),
                status="success",
                resource=resource,
            )
            return result

    # -- public API -----------------------------------------------------

    def list_buckets(
        self, *, page_size: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> tuple[list[BucketResource], str | None]:
        """List buckets, paginated.

        S3's ListBuckets returns every bucket in one call (there's no
        per-account bucket limit that makes native pagination worth the
        added complexity at this scale, and LocalStack's support for the
        newer ContinuationToken/MaxBuckets params is inconsistent across
        versions). Pagination is therefore applied at this layer: the
        cursor is just a base64-encoded offset into the (name-sorted) full
        list. This keeps the API contract identical to what real
        server-side pagination would look like, so routes/frontend code
        written against it doesn't change if this is later swapped for
        native AWS pagination.
        """
        response = self._call("ListBuckets", lambda: self._client().list_buckets())
        region = self._provider_region()

        buckets = sorted(response.get("Buckets", []), key=lambda b: b["Name"])
        all_resources = [
            BucketResource(
                id=b["Name"],
                name=b["Name"],
                region=region,
                created_at=b.get("CreationDate"),
            )
            for b in buckets
        ]

        offset = _decode_cursor(cursor)
        page = all_resources[offset : offset + page_size]
        next_offset = offset + page_size
        next_cursor = _encode_cursor(next_offset) if next_offset < len(all_resources) else None

        return page, next_cursor

    def create_bucket(self, name: str) -> BucketResource:
        region = self._provider_region()

        def _create():
            # us-east-1 is the one region that rejects an explicit
            # LocationConstraint on CreateBucket.
            if region == "us-east-1":
                return self._client().create_bucket(Bucket=name)
            return self._client().create_bucket(
                Bucket=name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )

        self._call("CreateBucket", _create, resource=name)
        return BucketResource(id=name, name=name, region=region, created_at=datetime.utcnow())

    def delete_bucket(self, name: str) -> None:
        self._call("DeleteBucket", lambda: self._client().delete_bucket(Bucket=name), resource=name)

    def get_bucket(self, name: str) -> BucketResource:
        # HeadBucket confirms existence/access and maps a missing bucket to
        # NoSuchBucket-equivalent 404s consistently across providers.
        self._call("HeadBucket", lambda: self._client().head_bucket(Bucket=name), resource=name)

        region = self._get_bucket_region(name)
        tags = self._get_bucket_tags(name)

        return BucketResource(id=name, name=name, region=region, tags=tags)

    # -- internal helpers -------------------------------------------------

    def _provider_region(self) -> str:
        # Every client this provider hands out is configured for the same
        # region, so any client's `.meta.region_name` reflects it.
        return self._client().meta.region_name

    def _get_bucket_region(self, name: str) -> str:
        response = self._call(
            "GetBucketLocation", lambda: self._client().get_bucket_location(Bucket=name), resource=name
        )
        # AWS returns None/"" for us-east-1 instead of the literal name.
        return response.get("LocationConstraint") or "us-east-1"

    def _get_bucket_tags(self, name: str) -> dict[str, str]:
        try:
            response = self._call(
                "GetBucketTagging", lambda: self._client().get_bucket_tagging(Bucket=name), resource=name
            )
        except AppError as exc:
            # A bucket with no tags is not an error condition for callers of
            # this service — GetBucketTagging just 404s ("NoSuchTagSet") to
            # say so. Anything else (access denied, provider unavailable)
            # should still propagate.
            if exc.code == ErrorCode.RESOURCE_NOT_FOUND:
                return {}
            raise
        return {tag["Key"]: tag["Value"] for tag in response.get("TagSet", [])}


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
    except (ValueError, UnicodeDecodeError):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid pagination cursor.",
            status_code=400,
            retryable=False,
        )
