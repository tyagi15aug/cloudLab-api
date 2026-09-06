from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.services.sqs_service import SqsService


@pytest.fixture
def sqs_service(provider):
    return SqsService(provider)


def test_list_queues_empty(sqs_service):
    assert sqs_service.list_queues() == []


def test_create_queue_returns_resource(sqs_service):
    queue = sqs_service.create_queue("orders")
    assert queue.name == "orders"
    assert queue.id == "orders"
    assert queue.url.endswith("/orders")
    assert queue.arn.endswith(":orders")
    assert queue.approximate_message_count == 0


def test_create_then_list_includes_the_queue(sqs_service):
    sqs_service.create_queue("notifications")
    items = sqs_service.list_queues()
    assert [q.name for q in items] == ["notifications"]


def test_list_queues_is_sorted_by_name(sqs_service):
    for name in ["zeta-queue", "alpha-queue", "mid-queue"]:
        sqs_service.create_queue(name)

    items = sqs_service.list_queues()
    assert [q.name for q in items] == ["alpha-queue", "mid-queue", "zeta-queue"]


def test_delete_queue_removes_it(sqs_service):
    sqs_service.create_queue("to-delete")
    sqs_service.delete_queue("to-delete")
    assert sqs_service.list_queues() == []


def test_delete_missing_queue_raises_not_found(sqs_service):
    with pytest.raises(AppError) as exc_info:
        sqs_service.delete_queue("does-not-exist")
    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_get_missing_queue_raises_not_found(sqs_service):
    with pytest.raises(AppError) as exc_info:
        sqs_service.get_queue("does-not-exist")
    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_send_then_receive_message(sqs_service):
    sqs_service.create_queue("orders")
    sent = sqs_service.send_message("orders", "hello world")
    assert sent.body == "hello world"
    assert sent.message_id

    received = sqs_service.receive_messages("orders")
    assert len(received) == 1
    assert received[0].message_id == sent.message_id
    assert received[0].body == "hello world"
    assert received[0].receipt_handle
    assert received[0].approximate_receive_count == 1


def test_receiving_bumps_the_queue_message_count(sqs_service):
    sqs_service.create_queue("orders")
    sqs_service.send_message("orders", "one")
    sqs_service.send_message("orders", "two")

    queue = sqs_service.get_queue("orders")
    assert queue.approximate_message_count == 2


def test_delete_message_removes_it_from_the_queue(sqs_service):
    sqs_service.create_queue("orders")
    sqs_service.send_message("orders", "hello world")
    [message] = sqs_service.receive_messages("orders")

    sqs_service.delete_message("orders", message.receipt_handle)

    assert sqs_service.receive_messages("orders") == []


def test_delete_message_with_invalid_receipt_handle_raises_validation_error(sqs_service):
    sqs_service.create_queue("orders")
    with pytest.raises(AppError) as exc_info:
        sqs_service.delete_message("orders", "not-a-real-receipt-handle")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_receiving_from_an_empty_queue_returns_no_messages(sqs_service):
    sqs_service.create_queue("empty-queue")
    assert sqs_service.receive_messages("empty-queue") == []
