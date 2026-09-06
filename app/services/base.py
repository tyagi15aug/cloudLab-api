"""Shared service-layer plumbing (Phase 3 refactor).

`S3Service` (Phase 1) implemented this same "every provider call goes
through one instrumented helper" pattern on its own. Extracting it here
before adding SQS/DynamoDB is exactly the point of Phase 3.1/3.4: a second
and third resource shouldn't have to re-invent (or copy-paste) timing +
structured logging + error translation.
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
            # Phase 4: consulted before every real provider call so any
            # resource service gets failure injection for free — see
            # app/core/failure_injection.py. Raises AppError directly (for
            # every failure type except pure LATENCY, which just delays)
            # rather than a botocore exception, since there's no real AWS
            # call to fail; the `except AppError` branch below logs it
            # exactly like a translated real error.
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
            # Phase 5: the same completed-operation event `log_operation`
            # just emitted to stdout, additionally kept queryable over HTTP
            # — see app/core/operations.py. An injected failure (above) and
            # a real translated one (below) both land here identically,
            # since by this point they're both just an AppError.
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
