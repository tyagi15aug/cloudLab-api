"""DynamoDB application service (Phase 3.3).

Two things make this service meaningfully different from S3Service/SqsService:

1. Items are freeform JSON above this layer — `_to_plain`/`_to_attribute_value`
   are the only place DynamoDB's typed AttributeValue wire format
   (`{"S": "x"}`, `{"N": "1"}`, ...) is visible in the codebase.
2. Item listing uses DynamoDB's own native pagination (`LastEvaluatedKey`),
   not the offset-based cursor S3Service uses — Scan has no concept of an
   arbitrary offset, only "continue after this key". The cursor here is a
   base64-encoded JSON blob of that key instead of an integer offset.
"""

from __future__ import annotations

import base64
import json
import logging
from decimal import Decimal
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from app.core.errors import AppError, ErrorCode
from app.models.dynamodb import KeyAttribute, TableResource
from app.providers.base import CloudProvider
from app.services.base import ProviderService

logger = logging.getLogger("app.services.dynamodb")

DEFAULT_PAGE_SIZE = 25

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


class DynamoDbService(ProviderService):
    service_name = "dynamodb"

    def __init__(self, provider: CloudProvider) -> None:
        super().__init__(provider, logger=logger)

    # -- tables -----------------------------------------------------------

    def list_tables(self) -> list[TableResource]:
        response = self._call("ListTables", lambda: self._client().list_tables())
        names = response.get("TableNames", [])
        return sorted((self.get_table(name) for name in names), key=lambda t: t.name)

    def create_table(
        self,
        name: str,
        *,
        partition_key: str,
        partition_key_type: str = "S",
        sort_key: str | None = None,
        sort_key_type: str = "S",
    ) -> TableResource:
        key_schema = [{"AttributeName": partition_key, "KeyType": "HASH"}]
        attribute_definitions = [{"AttributeName": partition_key, "AttributeType": partition_key_type}]
        if sort_key:
            key_schema.append({"AttributeName": sort_key, "KeyType": "RANGE"})
            attribute_definitions.append({"AttributeName": sort_key, "AttributeType": sort_key_type})

        self._call(
            "CreateTable",
            lambda: self._client().create_table(
                TableName=name,
                KeySchema=key_schema,
                AttributeDefinitions=attribute_definitions,
                BillingMode="PAY_PER_REQUEST",
            ),
            resource=name,
        )
        return self.get_table(name)

    def delete_table(self, name: str) -> None:
        self._call("DeleteTable", lambda: self._client().delete_table(TableName=name), resource=name)

    def get_table(self, name: str) -> TableResource:
        response = self._call(
            "DescribeTable", lambda: self._client().describe_table(TableName=name), resource=name
        )
        table = response["Table"]

        attr_types = {a["AttributeName"]: a["AttributeType"] for a in table.get("AttributeDefinitions", [])}
        partition_key = next(k for k in table["KeySchema"] if k["KeyType"] == "HASH")
        sort_key_entry = next((k for k in table["KeySchema"] if k["KeyType"] == "RANGE"), None)

        return TableResource(
            id=table["TableName"],
            name=table["TableName"],
            arn=table.get("TableArn", ""),
            region=self._provider_region(),
            status=table.get("TableStatus", "UNKNOWN"),
            item_count=table.get("ItemCount", 0),
            created_at=table.get("CreationDateTime").timestamp() if table.get("CreationDateTime") else None,
            partition_key=KeyAttribute(
                name=partition_key["AttributeName"],
                type=attr_types.get(partition_key["AttributeName"], "S"),
            ),
            sort_key=(
                KeyAttribute(
                    name=sort_key_entry["AttributeName"],
                    type=attr_types.get(sort_key_entry["AttributeName"], "S"),
                )
                if sort_key_entry
                else None
            ),
        )

    # -- items --------------------------------------------------------------

    def list_items(
        self, name: str, *, page_size: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        kwargs: dict[str, Any] = {"TableName": name, "Limit": page_size}
        start_key = _decode_item_cursor(cursor)
        if start_key is not None:
            kwargs["ExclusiveStartKey"] = start_key

        response = self._call("Scan", lambda: self._client().scan(**kwargs), resource=name)

        items = [_to_plain(item) for item in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")
        next_cursor = _encode_item_cursor(last_key) if last_key else None
        return items, next_cursor

    def put_item(self, name: str, item: dict[str, Any]) -> dict[str, Any]:
        av_item = _to_attribute_value_map(item)
        self._call("PutItem", lambda: self._client().put_item(TableName=name, Item=av_item), resource=name)
        return item

    def delete_item(self, name: str, key: dict[str, Any]) -> None:
        av_key = _to_attribute_value_map(key)
        self._call(
            "DeleteItem", lambda: self._client().delete_item(TableName=name, Key=av_key), resource=name
        )


# -- AttributeValue <-> plain JSON conversion --------------------------------


def _to_attribute_value_map(plain: dict[str, Any]) -> dict[str, Any]:
    try:
        return {k: _serializer.serialize(_to_dynamo_compatible(v)) for k, v in plain.items()}
    except TypeError as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Unsupported value type in item: {exc}",
            status_code=400,
            retryable=False,
        ) from exc


def _to_dynamo_compatible(value: Any) -> Any:
    """boto3's TypeSerializer refuses native Python floats outright ("Float
    types are not supported. Use Decimal types instead.") — real bug this
    surfaced: JSON request bodies naturally produce floats for any
    non-integer number, so every item with a decimal value would 400
    without this conversion. `str(value)` avoids binary float imprecision
    (Decimal(4.5) directly can produce long repeating-binary artifacts;
    Decimal(str(4.5)) doesn't)."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo_compatible(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo_compatible(v) for v in value]
    return value


def _to_plain(av_map: dict[str, Any]) -> dict[str, Any]:
    return {k: _from_dynamo_value(_deserializer.deserialize(v)) for k, v in av_map.items()}


def _from_dynamo_value(value: Any) -> Any:
    """Recursively converts Decimal (DynamoDB's number type) to int/float,
    since neither the JSON encoder nor most frontends expect Decimal."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo_value(v) for v in value]
    return value


# -- item-listing cursor: DynamoDB's own LastEvaluatedKey, not an offset ----


def _encode_item_cursor(last_evaluated_key: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(last_evaluated_key).encode()).decode()


def _decode_item_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid pagination cursor.",
            status_code=400,
            retryable=False,
        ) from exc
