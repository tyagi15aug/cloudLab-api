from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import S3ServiceDep
from app.models.resource import BucketList, BucketResource, CreateBucketRequest

router = APIRouter(prefix="/api/resources/s3/buckets", tags=["s3"])


@router.get("", response_model=BucketList)
def list_buckets(
    s3: S3ServiceDep,
    page_size: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> BucketList:
    items, next_cursor = s3.list_buckets(page_size=page_size, cursor=cursor)
    return BucketList(items=items, next_cursor=next_cursor)


@router.post("", response_model=BucketResource, status_code=status.HTTP_201_CREATED)
def create_bucket(body: CreateBucketRequest, s3: S3ServiceDep) -> BucketResource:
    return s3.create_bucket(body.name)


@router.get("/{name}", response_model=BucketResource)
def get_bucket(name: str, s3: S3ServiceDep) -> BucketResource:
    return s3.get_bucket(name)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_bucket(name: str, s3: S3ServiceDep) -> None:
    s3.delete_bucket(name)
