from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.providers.base import CloudProvider
from app.providers.factory import get_provider
from app.services.dynamodb_service import DynamoDbService
from app.services.s3_service import S3Service
from app.services.sqs_service import SqsService

ProviderDep = Annotated[CloudProvider, Depends(get_provider)]


def get_s3_service(provider: ProviderDep) -> S3Service:
    return S3Service(provider)


def get_sqs_service(provider: ProviderDep) -> SqsService:
    return SqsService(provider)


def get_dynamodb_service(provider: ProviderDep) -> DynamoDbService:
    return DynamoDbService(provider)


S3ServiceDep = Annotated[S3Service, Depends(get_s3_service)]
SqsServiceDep = Annotated[SqsService, Depends(get_sqs_service)]
DynamoDbServiceDep = Annotated[DynamoDbService, Depends(get_dynamodb_service)]
