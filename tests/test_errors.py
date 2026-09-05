from __future__ import annotations

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.errors import ErrorCode, translate_boto_error


def make_client_error(code: str, message: str = "boom", operation: str = "TestOp") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


@pytest.mark.parametrize(
    "aws_code,expected_code,expected_status,expected_retryable",
    [
        ("NoSuchBucket", ErrorCode.RESOURCE_NOT_FOUND, 404, False),
        ("404", ErrorCode.RESOURCE_NOT_FOUND, 404, False),
        ("NoSuchTagSet", ErrorCode.RESOURCE_NOT_FOUND, 404, False),
        ("BucketAlreadyExists", ErrorCode.RESOURCE_ALREADY_EXISTS, 409, False),
        ("BucketAlreadyOwnedByYou", ErrorCode.RESOURCE_ALREADY_EXISTS, 409, False),
        ("BucketNotEmpty", ErrorCode.RESOURCE_CONFLICT, 409, False),
        ("AccessDenied", ErrorCode.ACCESS_DENIED, 403, False),
        ("InvalidBucketName", ErrorCode.VALIDATION_ERROR, 400, False),
        ("SlowDown", ErrorCode.THROTTLED, 429, True),
        ("Throttling", ErrorCode.THROTTLED, 429, True),
        ("ServiceUnavailable", ErrorCode.PROVIDER_UNAVAILABLE, 503, True),
        ("SomeBrandNewAwsErrorCode", ErrorCode.PROVIDER_ERROR, 502, True),
    ],
)
def test_translate_client_error(aws_code, expected_code, expected_status, expected_retryable):
    app_error = translate_boto_error(make_client_error(aws_code))
    assert app_error.code == expected_code
    assert app_error.status_code == expected_status
    assert app_error.retryable is expected_retryable


def test_translate_client_error_includes_resource_in_message():
    app_error = translate_boto_error(make_client_error("NoSuchBucket"), resource="my-bucket")
    assert "my-bucket" in app_error.message


def test_translate_connection_error_is_retryable_and_unavailable():
    exc = EndpointConnectionError(endpoint_url="http://localhost:4566")
    app_error = translate_boto_error(exc)
    assert app_error.code == ErrorCode.PROVIDER_UNAVAILABLE
    assert app_error.status_code == 503
    assert app_error.retryable is True


def test_translate_unknown_exception_is_internal_error_not_retryable():
    app_error = translate_boto_error(ValueError("something else entirely"))
    assert app_error.code == ErrorCode.INTERNAL_ERROR
    assert app_error.status_code == 500
    assert app_error.retryable is False
    # The raw exception message should not leak to the caller.
    assert "something else entirely" not in app_error.message
