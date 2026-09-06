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
    # SQS's ListQueues doesn't give us a stable sort order or cheap
    # pagination to build on (it's a prefix-filtered scan under the hood),
    # and we don't expect this app to ever have that many queues. So unlike
    # S3/DynamoDB, this one just doesn't paginate — an honest limitation,
    # not a faked cursor that does nothing.
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
    # A receipt handle is an opaque blob that's often not URL-safe, so it
    # goes in a POST body instead of a path param — saves us the escaping
    # headaches, and DELETE-with-a-body isn't reliably supported everywhere
    # anyway.
    sqs.delete_message(name, body.receipt_handle)
