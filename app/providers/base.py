"""The provider abstraction boundary.

Application services (see app/services/) depend on this interface, never on
boto3 or a LocalStack endpoint URL directly:

    Route -> Service -> CloudProvider -> {LocalStackProvider, AWSProvider}

instead of every service constructing its own `boto3.client("s3",
endpoint_url=...)`. That's the whole point of the boundary: swapping
LocalStack for real AWS — or adding failure injection in Phase 4, or a fake
in-memory provider for fast unit tests in Phase 1.6 — becomes "implement one
more CloudProvider", not "grep every service for boto3.client calls".

The interface is deliberately small. `get_client` is the only thing every
resource type will always need (an authenticated, correctly-endpointed
boto3 client for a given AWS service name); resource-specific behavior
belongs in app/services/, not here. Widen this interface only when a real
service needs something a boto3 client can't give it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CloudProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider, e.g. "localstack" or "aws".

        Used only for observability (structured log/operation records) —
        never branched on by service code.
        """

    @abstractmethod
    def get_client(self, service_name: str) -> Any:
        """Return a boto3 client for the given AWS service (e.g. "s3")."""
