"""DynamoDB resource shapes (Phase 3.3).

Items are freeform by nature (that's the point of a NoSQL table), so
`ItemResource` deliberately doesn't try to force a schema on them — it's a
plain JSON object. `DynamoDbService` (services/dynamodb_service.py) is what
converts between DynamoDB's typed AttributeValue wire format
(`{"S": "x"}`, `{"N": "1"}`, ...) and this plain-JSON shape, so nothing
above the service layer needs to know DynamoDB's type-tagging scheme
exists.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AttributeType = Literal["S", "N", "B"]


class KeyAttribute(BaseModel):
    name: str
    type: AttributeType


class TableResource(BaseModel):
    id: str = Field(..., description="The table name; table names are unique per account+region.")
    name: str
    arn: str
    region: str
    status: str
    item_count: int = 0
    created_at: float | None = None
    partition_key: KeyAttribute
    sort_key: KeyAttribute | None = None


class TableList(BaseModel):
    items: list[TableResource]
    next_cursor: str | None = None


class CreateTableRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=255, pattern=r"^[A-Za-z0-9_.-]+$")
    partition_key: str = Field(..., min_length=1)
    partition_key_type: AttributeType = "S"
    sort_key: str | None = None
    sort_key_type: AttributeType = "S"


class ItemResource(BaseModel):
    """A single item, as plain JSON — see module docstring."""

    attributes: dict[str, Any]


class ItemList(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class PutItemRequest(BaseModel):
    item: dict[str, Any] = Field(..., description="Must include the table's key attribute(s).")


class DeleteItemRequest(BaseModel):
    key: dict[str, Any] = Field(..., description="The table's key attribute(s) identifying the item.")
