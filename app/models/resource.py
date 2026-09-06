"""Shared resource + error response shapes.

BucketResource follows the same general shape (id/name/region/tags/
created_at) every resource in this app shares, trimmed down to what a
bucket actually has — there's no meaningful "status" for a bucket beyond
existing, so we just don't fake one.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BucketResource(BaseModel):
    id: str = Field(..., description="The bucket name; buckets are globally unique so name IS the id.")
    name: str
    region: str
    created_at: datetime | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class BucketList(BaseModel):
    items: list[BucketResource]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor; pass as ?cursor= to fetch the next page.",
    )


class CreateBucketRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=63)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = Field(default=None, alias="requestId")
    retryable: bool

    model_config = {"populate_by_name": True}


class ErrorResponse(BaseModel):
    error: ErrorBody
