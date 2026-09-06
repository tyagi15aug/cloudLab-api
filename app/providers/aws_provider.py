from __future__ import annotations

from typing import Any

import boto3

from app.providers.base import CloudProvider


class AWSProvider(CloudProvider):
    """Points the AWS SDK at real AWS.

    On purpose, this doesn't take static credentials as an argument —
    boto3's own credential chain (env vars, a shared profile, an
    instance/container role) handles that. Keeping this provider dumb is
    what keeps a real AWS key from ever needing to live in this repo's
    config in the first place.
    """

    def __init__(self, *, region: str) -> None:
        self._region = region
        self._clients: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "aws"

    def get_client(self, service_name: str) -> Any:
        if service_name not in self._clients:
            self._clients[service_name] = boto3.client(service_name, region_name=self._region)
        return self._clients[service_name]
