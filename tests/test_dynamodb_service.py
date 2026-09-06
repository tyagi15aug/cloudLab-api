from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.services.dynamodb_service import DynamoDbService


@pytest.fixture
def ddb_service(provider):
    return DynamoDbService(provider)


def test_list_tables_empty(ddb_service):
    assert ddb_service.list_tables() == []


def test_create_table_returns_resource(ddb_service):
    table = ddb_service.create_table("users", partition_key="id")
    assert table.name == "users"
    assert table.id == "users"
    assert table.status == "ACTIVE"
    assert table.partition_key.name == "id"
    assert table.partition_key.type == "S"
    assert table.sort_key is None


def test_create_table_with_composite_key(ddb_service):
    table = ddb_service.create_table(
        "orders", partition_key="pk", partition_key_type="S", sort_key="sk", sort_key_type="S"
    )
    assert table.partition_key.name == "pk"
    assert table.sort_key is not None
    assert table.sort_key.name == "sk"


def test_create_then_list_includes_the_table(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    items = ddb_service.list_tables()
    assert [t.name for t in items] == ["users"]


def test_list_tables_is_sorted_by_name(ddb_service):
    for name in ["zeta-table", "alpha-table", "mid-table"]:
        ddb_service.create_table(name, partition_key="id")

    items = ddb_service.list_tables()
    assert [t.name for t in items] == ["alpha-table", "mid-table", "zeta-table"]


def test_delete_table_removes_it(ddb_service):
    ddb_service.create_table("to-delete", partition_key="id")
    ddb_service.delete_table("to-delete")
    assert ddb_service.list_tables() == []


def test_delete_missing_table_raises_not_found(ddb_service):
    with pytest.raises(AppError) as exc_info:
        ddb_service.delete_table("does-not-exist")
    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_get_missing_table_raises_not_found(ddb_service):
    with pytest.raises(AppError) as exc_info:
        ddb_service.get_table("does-not-exist")
    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_create_duplicate_table_raises_already_exists(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    with pytest.raises(AppError) as exc_info:
        ddb_service.create_table("users", partition_key="id")
    assert exc_info.value.code == ErrorCode.RESOURCE_ALREADY_EXISTS


def test_put_and_list_items_round_trips_plain_json(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    ddb_service.put_item("users", {"id": "u1", "name": "Alice", "age": 30, "active": True})

    items, cursor = ddb_service.list_items("users")
    assert items == [{"id": "u1", "name": "Alice", "age": 30, "active": True}]
    assert cursor is None


def test_put_item_with_float_round_trips_as_float_not_decimal(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    ddb_service.put_item("users", {"id": "u1", "score": 4.5})

    [item], _ = ddb_service.list_items("users")
    assert item["score"] == 4.5
    assert isinstance(item["score"], float)


def test_delete_item_removes_it(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    ddb_service.put_item("users", {"id": "u1", "name": "Alice"})
    ddb_service.delete_item("users", {"id": "u1"})

    items, _ = ddb_service.list_items("users")
    assert items == []


def test_put_item_missing_key_raises_validation_error(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    with pytest.raises(AppError) as exc_info:
        ddb_service.put_item("users", {"name": "no id here"})
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert exc_info.value.status_code == 400


def test_list_items_paginates_using_native_dynamodb_pagination(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    for i in range(5):
        ddb_service.put_item("users", {"id": f"u{i}"})

    first_page, cursor = ddb_service.list_items("users", page_size=2)
    assert len(first_page) == 2
    assert cursor is not None

    second_page, cursor2 = ddb_service.list_items("users", page_size=2, cursor=cursor)
    assert len(second_page) == 2
    assert cursor2 is not None

    third_page, cursor3 = ddb_service.list_items("users", page_size=2, cursor=cursor2)
    assert len(third_page) == 1
    assert cursor3 is None

    all_ids = {item["id"] for item in first_page + second_page + third_page}
    assert all_ids == {f"u{i}" for i in range(5)}


def test_list_items_rejects_a_malformed_cursor(ddb_service):
    ddb_service.create_table("users", partition_key="id")
    with pytest.raises(AppError) as exc_info:
        ddb_service.list_items("users", cursor="not-valid-base64!!")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert exc_info.value.status_code == 400
