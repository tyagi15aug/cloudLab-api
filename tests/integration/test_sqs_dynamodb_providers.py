"""Phase 3 integration coverage, following the same pattern as
test_localstack_provider.py: real LocalStackProvider + real service classes
over real HTTP against a moto-server process, not the in-process mock the
unit suite uses.
"""

from __future__ import annotations

from app.services.dynamodb_service import DynamoDbService
from app.services.sqs_service import SqsService


def test_sqs_full_lifecycle_over_real_http(localstack_provider) -> None:
    sqs = SqsService(localstack_provider)

    assert sqs.list_queues() == []

    queue = sqs.create_queue("integration-orders")
    assert queue.name == "integration-orders"
    assert queue.arn.endswith(":integration-orders")

    sqs.send_message("integration-orders", "hello over real http")
    [message] = sqs.receive_messages("integration-orders")
    assert message.body == "hello over real http"

    sqs.delete_message("integration-orders", message.receipt_handle)
    assert sqs.receive_messages("integration-orders") == []

    sqs.delete_queue("integration-orders")
    assert sqs.list_queues() == []


def test_dynamodb_full_lifecycle_over_real_http(localstack_provider) -> None:
    ddb = DynamoDbService(localstack_provider)

    assert ddb.list_tables() == []

    table = ddb.create_table("integration-users", partition_key="id")
    assert table.name == "integration-users"
    assert table.status == "ACTIVE"

    ddb.put_item("integration-users", {"id": "u1", "name": "Alice", "score": 4.5})
    items, cursor = ddb.list_items("integration-users")
    assert items == [{"id": "u1", "name": "Alice", "score": 4.5}]
    assert cursor is None

    ddb.delete_item("integration-users", {"id": "u1"})
    items, _ = ddb.list_items("integration-users")
    assert items == []

    ddb.delete_table("integration-users")
    assert ddb.list_tables() == []
