from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import SqsServiceDep
from app.models.sqs import (
    CreateQueueRequest,
    DeleteMessageRequest,
    MessageList,
    MessageResource,
    QueueList,
    QueueResource,
    SendMessageRequest,
)

router = APIRouter(prefix="/api/resources/sqs/queues", tags=["sqs"])


@router.get("", response_model=QueueList)
def list_queues(sqs: SqsServiceDep) -> QueueList:
    # SQS's own ListQueues has no useful notion of a stable sort order or
    # cheap pagination (it's a prefix-filtered scan, at small scale) — this
    # app's queue count is expected to stay small, so unlike S3/DynamoDB,
    # this one honestly doesn't paginate rather than faking a cursor.
    return QueueList(items=sqs.list_queues())


@router.post("", response_model=QueueResource, status_code=status.HTTP_201_CREATED)
def create_queue(body: CreateQueueRequest, sqs: SqsServiceDep) -> QueueResource:
    return sqs.create_queue(body.name)


@router.get("/{name}", response_model=QueueResource)
def get_queue(name: str, sqs: SqsServiceDep) -> QueueResource:
    return sqs.get_queue(name)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_queue(name: str, sqs: SqsServiceDep) -> None:
    sqs.delete_queue(name)


@router.get("/{name}/messages", response_model=MessageList)
def receive_messages(
    name: str, sqs: SqsServiceDep, max_messages: int = Query(default=10, ge=1, le=10)
) -> MessageList:
    return MessageList(items=sqs.receive_messages(name, max_messages=max_messages))


@router.post("/{name}/messages", response_model=MessageResource, status_code=status.HTTP_201_CREATED)
def send_message(name: str, body: SendMessageRequest, sqs: SqsServiceDep) -> MessageResource:
    return sqs.send_message(name, body.body)


@router.post("/{name}/messages/delete", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_message(name: str, body: DeleteMessageRequest, sqs: SqsServiceDep) -> None:
    # A receipt handle is an opaque, often URL-unsafe blob — accepting it in
    # a POST body avoids the escaping problems a DELETE-with-path-param
    # (or DELETE-with-body, which not every HTTP client supports cleanly)
    # would run into.
    sqs.delete_message(name, body.receipt_handle)
