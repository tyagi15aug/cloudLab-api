"""Shared service-layer plumbing.

Every resource service (S3, SQS, DynamoDB) routes its provider calls
through `ProviderService._call()` below instead of hitting the boto3
client directly. One place doing timing, error translation, structured
logging, failure injection, and operation history means adding a fourth
resource type never means copy-pasting all of that again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from botocore.exceptions import BotoCoreError, ClientError

from app.core.errors import AppError, translate_boto_error
from app.core.failure_injection import failure_injector
from app.core.logging import elapsed_ms, log_operation, request_id_ctx, timed_ms
from app.core.operations import operation_recorder
from app.providers.base import CloudProvider

T = TypeVar("T")


class ProviderService:
    """Base class for a resource service backed by one boto3 client.

    Subclasses set `service_name` (the boto3/botocore service, e.g. "s3",
    "sqs", "dynamodb") and a `logger`, then route every provider call
    through `self._call(...)` instead of calling `self._client()` methods
    directly.
    """

    service_name: str

    def __init__(self, provider: CloudProvider, *, logger: logging.Logger) -> None:
        self._provider = provider
        self._logger = logger

    def _client(self):
        return self._provider.get_client(self.service_name)

    def _call(self, operation: str, fn: Callable[[], T], *, resource: str | None = None) -> T:
        start = timed_ms()
        request_id = request_id_ctx.get()
        try:
            # Give the failure injector (app/core/failure_injection.py) a
            # chance to fake a failure before we make the real call. It
            # raises an AppError directly rather than a botocore exception
            # — there's no real AWS call happening for it to fail — which
            # is why the `except AppError` branch below exists: it logs an
            # injected failure exactly the same way as a real one.
            failure_injector.apply(service=self.service_name, operation=operation)
            result = fn()
        except AppError as exc:
            duration_ms = elapsed_ms(start)
            log_operation(
                self._logger,
                operation=operation,
                service=self.service_name,
                provider=self._provider.name,
                duration_ms=duration_ms,
                status="error",
                resource=resource,
                error=exc.code.value,
            )
            # Same event as the log line above, but kept in memory too so
            # it's queryable over HTTP (app/core/operations.py) instead of
            # only living in stdout. An injected failure and a real one
            # both end up here looking identical — by this point they're
            # both just an AppError, and that's fine.
            operation_recorder.record(
                service=self.service_name,
                operation=operation,
                provider=self._provider.name,
                status="error",
                duration_ms=duration_ms,
                request_id=request_id,
                resource=resource,
                error=exc.code.value,
                retryable=exc.retryable,
            )
            raise
        except (ClientError, BotoCoreError) as exc:
            app_error = translate_boto_error(exc, resource=resource)
            duration_ms = elapsed_ms(start)
            log_operation(
                self._logger,
                operation=operation,
                service=self.service_name,
                provider=self._provider.name,
                duration_ms=duration_ms,
                status="error",
                resource=resource,
                error=app_error.code.value,
            )
            operation_recorder.record(
                service=self.service_name,
                operation=operation,
                provider=self._provider.name,
                status="error",
                duration_ms=duration_ms,
                request_id=request_id,
                resource=resource,
                error=app_error.code.value,
                retryable=app_error.retryable,
            )
            raise app_error from exc
        else:
            duration_ms = elapsed_ms(start)
            log_operation(
                self._logger,
                operation=operation,
                service=self.service_name,
                provider=self._provider.name,
                duration_ms=duration_ms,
                status="success",
                resource=resource,
            )
            operation_recorder.record(
                service=self.service_name,
                operation=operation,
                provider=self._provider.name,
                status="success",
                duration_ms=duration_ms,
                request_id=request_id,
                resource=resource,
            )
            return result

    def _provider_region(self) -> str:
        return self._client().meta.region_name
