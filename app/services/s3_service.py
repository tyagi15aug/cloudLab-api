"""S3 application service.

This is the only place that should ever import a botocore exception type
or know that an AWS error code like "BucketAlreadyExists" exists. Routes
call this, this calls the CloudProvider, and every boto3 detail gets
translated or swallowed before anything goes back up.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.core.errors import AppError, ErrorCode
from app.models.resource import BucketResource
from app.providers.base import CloudProvider
from app.services.base import ProviderService
from app.services.pagination import decode_cursor, encode_cursor

logger = logging.getLogger("app.services.s3")

DEFAULT_PAGE_SIZE = 50


class S3Service(ProviderService):
    service_name = "s3"

    def __init__(self, provider: CloudProvider) -> None:
        super().__init__(provider, logger=logger)

    # -- public API -----------------------------------------------------

    def list_buckets(
        self, *, page_size: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> tuple[list[BucketResource], str | None]:
        """List buckets, paginated.

        S3's ListBuckets just hands back every bucket in one call — no
        native pagination worth relying on here, and LocalStack's support
        for the newer ContinuationToken/MaxBuckets params isn't consistent
        across versions anyway. So we paginate ourselves: the cursor is a
        base64-encoded offset into the full, name-sorted list. Same API
        shape a real paginated endpoint would have, so nothing above this
        layer would need to change if we ever swap this for native AWS
        pagination.
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

        offset = decode_cursor(cursor)
        page = all_resources[offset : offset + page_size]
        next_offset = offset + page_size
        next_cursor = encode_cursor(next_offset) if next_offset < len(all_resources) else None

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
