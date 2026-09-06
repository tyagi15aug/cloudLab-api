from __future__ import annotations

import pytest


def test_full_queue_and_message_lifecycle(client):
    assert client.get("/api/resources/sqs/queues").json() == {"items": []}

    create_response = client.post("/api/resources/sqs/queues", json={"name": "orders"})
    assert create_response.status_code == 201
    assert create_response.json()["name"] == "orders"

    list_response = client.get("/api/resources/sqs/queues")
    assert [q["name"] for q in list_response.json()["items"]] == ["orders"]

    get_response = client.get("/api/resources/sqs/queues/orders")
    assert get_response.status_code == 200
    assert get_response.json()["approximate_message_count"] == 0

    send_response = client.post("/api/resources/sqs/queues/orders/messages", json={"body": "hello world"})
    assert send_response.status_code == 201
    assert send_response.json()["body"] == "hello world"

    receive_response = client.get("/api/resources/sqs/queues/orders/messages")
    assert receive_response.status_code == 200
    [message] = receive_response.json()["items"]
    assert message["body"] == "hello world"
    receipt_handle = message["receipt_handle"]

    delete_message_response = client.post(
        "/api/resources/sqs/queues/orders/messages/delete", json={"receipt_handle": receipt_handle}
    )
    assert delete_message_response.status_code == 204

    assert client.get("/api/resources/sqs/queues/orders/messages").json()["items"] == []

    delete_queue_response = client.delete("/api/resources/sqs/queues/orders")
    assert delete_queue_response.status_code == 204
    assert client.get("/api/resources/sqs/queues").json()["items"] == []


def test_get_missing_queue_returns_unified_error_shape(client):
    response = client.get("/api/resources/sqs/queues/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "requestId" in body["error"]


def test_delete_missing_queue_returns_404(client):
    response = client.delete("/api/resources/sqs/queues/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize("body", [{"name": ""}, {}, {"name": "has a space"}])
def test_create_queue_validation_errors_use_unified_shape(client, body):
    response = client.post("/api/resources/sqs/queues", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_send_message_validation_error_on_empty_body(client):
    client.post("/api/resources/sqs/queues", json={"name": "orders"})
    response = client.post("/api/resources/sqs/queues/orders/messages", json={"body": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
