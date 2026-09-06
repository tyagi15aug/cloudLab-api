from __future__ import annotations

import pytest


def test_full_table_and_item_lifecycle(client):
    assert client.get("/api/resources/dynamodb/tables").json() == {"items": [], "next_cursor": None}

    create_response = client.post(
        "/api/resources/dynamodb/tables", json={"name": "users", "partition_key": "id"}
    )
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "users"
    assert create_response.json()["partition_key"] == {"name": "id", "type": "S"}

    list_response = client.get("/api/resources/dynamodb/tables")
    assert [t["name"] for t in list_response.json()["items"]] == ["users"]

    get_response = client.get("/api/resources/dynamodb/tables/users")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "ACTIVE"

    put_response = client.post(
        "/api/resources/dynamodb/tables/users/items", json={"item": {"id": "u1", "name": "Alice"}}
    )
    assert put_response.status_code == 201

    items_response = client.get("/api/resources/dynamodb/tables/users/items")
    assert items_response.json()["items"] == [{"id": "u1", "name": "Alice"}]

    delete_item_response = client.post(
        "/api/resources/dynamodb/tables/users/items/delete", json={"key": {"id": "u1"}}
    )
    assert delete_item_response.status_code == 204
    assert client.get("/api/resources/dynamodb/tables/users/items").json()["items"] == []

    delete_table_response = client.delete("/api/resources/dynamodb/tables/users")
    assert delete_table_response.status_code == 204
    assert client.get("/api/resources/dynamodb/tables").json()["items"] == []


def test_get_missing_table_returns_unified_error_shape(client):
    response = client.get("/api/resources/dynamodb/tables/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "requestId" in body["error"]


def test_create_duplicate_table_returns_409(client):
    client.post("/api/resources/dynamodb/tables", json={"name": "users", "partition_key": "id"})
    response = client.post("/api/resources/dynamodb/tables", json={"name": "users", "partition_key": "id"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"


@pytest.mark.parametrize("body", [{"name": "ab", "partition_key": "id"}, {"name": "users"}, {}])
def test_create_table_validation_errors_use_unified_shape(client, body):
    response = client.post("/api/resources/dynamodb/tables", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_put_item_missing_key_returns_400(client):
    client.post("/api/resources/dynamodb/tables", json={"name": "users", "partition_key": "id"})
    response = client.post(
        "/api/resources/dynamodb/tables/users/items", json={"item": {"name": "no id here"}}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_items_pagination_query_params(client):
    client.post("/api/resources/dynamodb/tables", json={"name": "users", "partition_key": "id"})
    for i in range(3):
        client.post("/api/resources/dynamodb/tables/users/items", json={"item": {"id": f"u{i}"}})

    first = client.get("/api/resources/dynamodb/tables/users/items", params={"page_size": 2})
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor

    second = client.get(
        "/api/resources/dynamodb/tables/users/items", params={"page_size": 2, "cursor": cursor}
    )
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None
