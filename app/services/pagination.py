"""Shared application-level cursor pagination (Phase 3 refactor).

Originally lived inside s3_service.py as `_encode_cursor`/`_decode_cursor`;
extracted so SQS/DynamoDB services can paginate the same way without
copy-pasting it — see app/services/s3_service.py's list_buckets docstring
for why this is offset-based rather than native AWS pagination.
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
