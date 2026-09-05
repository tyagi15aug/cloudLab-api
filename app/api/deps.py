from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.providers.base import CloudProvider
from app.providers.factory import get_provider
from app.services.s3_service import S3Service

ProviderDep = Annotated[CloudProvider, Depends(get_provider)]


def get_s3_service(provider: ProviderDep) -> S3Service:
    return S3Service(provider)


S3ServiceDep = Annotated[S3Service, Depends(get_s3_service)]
