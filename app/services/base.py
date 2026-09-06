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

from app.core.errors import translate_boto_error
from app.core.logging import elapsed_ms, log_operation, timed_ms
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
        try:
            result = fn()
        except (ClientError, BotoCoreError) as exc:
            app_error = translate_boto_error(exc, resource=resource)
            log_operation(
                self._logger,
                operation=operation,
                service=self.service_name,
                provider=self._provider.name,
                duration_ms=elapsed_ms(start),
                status="error",
                resource=resource,
                error=app_error.code.value,
            )
            raise app_error from exc
        else:
            log_operation(
                self._logger,
                operation=operation,
                service=self.service_name,
                provider=self._provider.name,
                duration_ms=elapsed_ms(start),
                status="success",
                resource=resource,
            )
            return result

    def _provider_region(self) -> str:
        return self._client().meta.region_name
