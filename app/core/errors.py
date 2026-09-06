"""Our own error type, and the mapping that gets us there from boto3.

The frontend should never have to know what a raw botocore exception or an
AWS error code looks like. Every provider failure gets translated into an
AppError with a stable `code`, a plain-English message, and a `retryable`
flag the UI can act on directly:

    retryable=true   -> show a Retry action
    retryable=false  -> show an actionable, non-retryable error
    403              -> permission problem
    timeout          -> retry + diagnostic info
"""

from __future__ import annotations

from enum import StrEnum

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
)
from botocore.exceptions import (
    ConnectionError as BotoConnectionError,
)


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    ACCESS_DENIED = "ACCESS_DENIED"
    THROTTLED = "THROTTLED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """A translated, UI-safe error.

    `status_code` is the HTTP status the API route should respond with;
    `code`/`retryable` are what actually reach the response body and drive
    frontend behavior.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int,
        retryable: bool,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.cause = cause


# botocore error Code -> (AppError code, http status, retryable)
_CLIENT_ERROR_MAP: dict[str, tuple[ErrorCode, int, bool]] = {
    "BucketAlreadyExists": (ErrorCode.RESOURCE_ALREADY_EXISTS, 409, False),
    "BucketAlreadyOwnedByYou": (ErrorCode.RESOURCE_ALREADY_EXISTS, 409, False),
    "NoSuchBucket": (ErrorCode.RESOURCE_NOT_FOUND, 404, False),
    # HeadBucket is a HEAD request, so a missing bucket carries no real error
    # body — AWS represents it as bare Code="404"/Message="Not Found" rather
    # than "NoSuchBucket".
    "404": (ErrorCode.RESOURCE_NOT_FOUND, 404, False),
    # GetBucketTagging on a bucket with no tags 404s under this code; the
    # service layer treats it as "no tags" rather than an error (see
    # S3Service._get_bucket_tags), but map it correctly regardless in case
    # it ever surfaces directly.
    "NoSuchTagSet": (ErrorCode.RESOURCE_NOT_FOUND, 404, False),
    "BucketNotEmpty": (ErrorCode.RESOURCE_CONFLICT, 409, False),
    "AccessDenied": (ErrorCode.ACCESS_DENIED, 403, False),
    "InvalidBucketName": (ErrorCode.VALIDATION_ERROR, 400, False),
    "InvalidAccessKeyId": (ErrorCode.ACCESS_DENIED, 403, False),
    "SlowDown": (ErrorCode.THROTTLED, 429, True),
    "Throttling": (ErrorCode.THROTTLED, 429, True),
    "TooManyRequests": (ErrorCode.THROTTLED, 429, True),
    "RequestTimeout": (ErrorCode.PROVIDER_UNAVAILABLE, 503, True),
    "ServiceUnavailable": (ErrorCode.PROVIDER_UNAVAILABLE, 503, True),
    "InternalError": (ErrorCode.PROVIDER_ERROR, 502, True),
    # -- SQS -----------------------------------------------------------
    "AWS.SimpleQueueService.NonExistentQueue": (ErrorCode.RESOURCE_NOT_FOUND, 404, False),
    "QueueAlreadyExists": (ErrorCode.RESOURCE_ALREADY_EXISTS, 409, False),
    # A queue can't be recreated with the same name for ~60s after deletion
    # on real AWS; moto doesn't enforce the timer, but map the code in case
    # it ever does.
    "AWS.SimpleQueueService.QueueDeletedRecently": (ErrorCode.RESOURCE_CONFLICT, 409, True),
    "ReceiptHandleIsInvalid": (ErrorCode.VALIDATION_ERROR, 400, False),
    "InvalidMessageContents": (ErrorCode.VALIDATION_ERROR, 400, False),
    # -- DynamoDB --------------------------------------------------------
    "ResourceNotFoundException": (ErrorCode.RESOURCE_NOT_FOUND, 404, False),
    # Also covers "table already exists" and "table mid create/delete" — both
    # are real DynamoDB overloads of the same code.
    "ResourceInUseException": (ErrorCode.RESOURCE_ALREADY_EXISTS, 409, False),
    "ConditionalCheckFailedException": (ErrorCode.RESOURCE_CONFLICT, 409, False),
    "ProvisionedThroughputExceededException": (ErrorCode.THROTTLED, 429, True),
    "LimitExceededException": (ErrorCode.THROTTLED, 429, True),
    # DynamoDB's ValidationException is used for both real request-shape
    # problems and this app's own bad-input cases — always a 400.
    "ValidationException": (ErrorCode.VALIDATION_ERROR, 400, False),
}


def translate_boto_error(exc: Exception, *, resource: str | None = None) -> AppError:
    """Map a botocore/boto3 exception to an AppError.

    Anything not explicitly recognized degrades to a retryable PROVIDER_ERROR
    rather than leaking the raw exception — an unmapped AWS error code is a
    gap to fill in, not a reason to 500 with a stack trace.
    """
    if isinstance(exc, ClientError):
        aws_code = exc.response.get("Error", {}).get("Code", "Unknown")
        aws_message = exc.response.get("Error", {}).get("Message", str(exc))
        mapped = _CLIENT_ERROR_MAP.get(aws_code)
        if mapped:
            code, status_code, retryable = mapped
        else:
            code, status_code, retryable = (ErrorCode.PROVIDER_ERROR, 502, True)
        suffix = f" ({resource})" if resource else ""
        return AppError(
            code,
            f"{aws_message}{suffix}",
            status_code=status_code,
            retryable=retryable,
            cause=exc,
        )

    if isinstance(exc, EndpointConnectionError | BotoConnectionError):
        return AppError(
            ErrorCode.PROVIDER_UNAVAILABLE,
            "Could not reach the cloud provider endpoint.",
            status_code=503,
            retryable=True,
            cause=exc,
        )

    if isinstance(exc, BotoCoreError):
        return AppError(
            ErrorCode.PROVIDER_ERROR,
            str(exc) or "Unexpected provider error.",
            status_code=502,
            retryable=True,
            cause=exc,
        )

    return AppError(
        ErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred.",
        status_code=500,
        retryable=False,
        cause=exc,
    )
