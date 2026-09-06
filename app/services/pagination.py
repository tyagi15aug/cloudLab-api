"""Cursor pagination, shared across services that don't have a native
cursor to lean on.

This used to live inside s3_service.py as private helpers; pulled out so
DynamoDB's table listing (and anything else that needs it) doesn't have
to copy-paste it. See S3Service.list_buckets for why S3 needs this at
all instead of using AWS's own pagination.
"""

from __future__ import annotations

import base64

from app.core.errors import AppError, ErrorCode


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid pagination cursor.",
            status_code=400,
            retryable=False,
        ) from exc
