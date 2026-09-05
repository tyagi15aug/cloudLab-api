from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.providers.aws_provider import AWSProvider
from app.providers.base import CloudProvider
from app.providers.localstack_provider import LocalStackProvider


def build_provider(settings: Settings) -> CloudProvider:
    if settings.cloud_provider == "aws":
        return AWSProvider(region=settings.aws_region)

    return LocalStackProvider(
        region=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )


@lru_cache
def get_provider() -> CloudProvider:
    """Process-wide singleton provider, built from the active settings.

    FastAPI route handlers should depend on this via Depends(get_provider)
    (see app/api/deps.py) rather than importing it directly, so tests can
    override it.
    """
    return build_provider(get_settings())
