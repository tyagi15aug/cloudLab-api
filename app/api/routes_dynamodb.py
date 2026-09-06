from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status

from app.api.deps import DynamoDbServiceDep
from app.models.dynamodb import (
    CreateTableRequest,
    DeleteItemRequest,
    ItemList,
    PutItemRequest,
    TableList,
    TableResource,
)

router = APIRouter(prefix="/api/resources/dynamodb/tables", tags=["dynamodb"])


@router.get("", response_model=TableList)
def list_tables(dynamodb: DynamoDbServiceDep) -> TableList:
    return TableList(items=dynamodb.list_tables())


@router.post("", response_model=TableResource, status_code=status.HTTP_201_CREATED)
def create_table(body: CreateTableRequest, dynamodb: DynamoDbServiceDep) -> TableResource:
    return dynamodb.create_table(
        body.name,
        partition_key=body.partition_key,
        partition_key_type=body.partition_key_type,
        sort_key=body.sort_key,
        sort_key_type=body.sort_key_type,
    )


@router.get("/{name}", response_model=TableResource)
def get_table(name: str, dynamodb: DynamoDbServiceDep) -> TableResource:
    return dynamodb.get_table(name)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_table(name: str, dynamodb: DynamoDbServiceDep) -> None:
    dynamodb.delete_table(name)


@router.get("/{name}/items", response_model=ItemList)
def list_items(
    name: str,
    dynamodb: DynamoDbServiceDep,
    page_size: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ItemList:
    items, next_cursor = dynamodb.list_items(name, page_size=page_size, cursor=cursor)
    return ItemList(items=items, next_cursor=next_cursor)


@router.post("/{name}/items", status_code=status.HTTP_201_CREATED)
def put_item(name: str, body: PutItemRequest, dynamodb: DynamoDbServiceDep) -> dict[str, Any]:
    return dynamodb.put_item(name, body.item)


@router.post("/{name}/items/delete", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_item(name: str, body: DeleteItemRequest, dynamodb: DynamoDbServiceDep) -> None:
    # Same reasoning as SQS's delete-message route: a composite key isn't a
    # clean single path segment, so it travels in the body of a POST instead
    # of a DELETE-with-path-param.
    dynamodb.delete_item(name, body.key)
