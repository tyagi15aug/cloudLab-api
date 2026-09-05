from __future__ import annotations

from typing import Any

import boto3

from app.providers.base import CloudProvider


class AWSProvider(CloudProvider):
    """Routes AWS SDK calls at real AWS.

    Deliberately does not accept static credentials — boto3's default
    credential chain (environment, shared config/profile, container/instance
    role) is what should supply them. Keeping this provider "dumb" is what
    keeps a real AWS key from ever needing to live in this codebase's
    config.
    """

    def __init__(self, *, region: str) -> None:
        self._region = region
        self._clients: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "aws"

    def get_client(self, service_name: str) -> Any:
        if service_name not in self._clients:
            self._clients[service_name] = boto3.client(
                service_name, region_name=self._region
            )
        return self._clients[service_name]
