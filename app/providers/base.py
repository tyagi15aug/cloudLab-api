"""The provider abstraction — this is the thing that makes "swap LocalStack
for real AWS" a one-line config change instead of a rewrite.

Services never touch boto3 or a LocalStack endpoint URL directly:

    Route -> Service -> CloudProvider -> {LocalStackProvider, AWSProvider}

So adding a new backend (a fake in-memory provider for tests, say) just
means writing one more CloudProvider, not hunting down every
`boto3.client(...)` call in the codebase.

Keep this interface small. `get_client` is the one thing every resource
type needs — an authenticated, correctly-endpointed boto3 client for a
given AWS service name. Anything resource-specific belongs in
app/services/, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CloudProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider, e.g. "localstack" or "aws".

        Purely for logging/operation records — service code should never
        branch on this.
        """

    @abstractmethod
    def get_client(self, service_name: str) -> Any:
        """Return a boto3 client for the given AWS service (e.g. "s3")."""
