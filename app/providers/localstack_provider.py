from __future__ import annotations

from typing import Any

import boto3

from app.providers.base import CloudProvider


class LocalStackProvider(CloudProvider):
    """Points the AWS SDK at a LocalStack endpoint instead of real AWS.

    LocalStack doesn't check credentials, just that something is there —
    so the access key/secret below are placeholders ("test"/"test" by
    default), not real secrets. See .env.example.
    """

    def __init__(
        self,
        *,
        region: str,
        endpoint_url: str,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> None:
        self._region = region
        self._endpoint_url = endpoint_url
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._clients: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "localstack"

    def get_client(self, service_name: str) -> Any:
        if service_name not in self._clients:
            self._clients[service_name] = boto3.client(
                service_name,
                region_name=self._region,
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
            )
        return self._clients[service_name]
