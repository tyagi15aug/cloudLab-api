"""SQS application service.

We use the queue name as this app's resource id, even though SQS itself
addresses everything by queue URL. That costs an extra GetQueueUrl call
per operation, but it keeps our API consistent with S3 (name-addressed)
instead of leaking SQS's URL-based addressing up into routes and the
frontend.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.models.sqs import MessageResource, QueueResource
from app.providers.base import CloudProvider
from app.services.base import ProviderService

logger = logging.getLogger("app.services.sqs")

DEFAULT_RECEIVE_MAX = 10


class SqsService(ProviderService):
    service_name = "sqs"

    def __init__(self, provider: CloudProvider) -> None:
        super().__init__(provider, logger=logger)

    # -- public API -----------------------------------------------------

    def list_queues(self) -> list[QueueResource]:
        response = self._call("ListQueues", lambda: self._client().list_queues())
        urls = response.get("QueueUrls", [])
        return sorted((self._describe_queue(url) for url in urls), key=lambda q: q.name)

    def create_queue(self, name: str) -> QueueResource:
        self._call("CreateQueue", lambda: self._client().create_queue(QueueName=name), resource=name)
        url = self._get_queue_url(name)
        return self._describe_queue(url)

    def delete_queue(self, name: str) -> None:
        url = self._get_queue_url(name)
        self._call("DeleteQueue", lambda: self._client().delete_queue(QueueUrl=url), resource=name)

    def get_queue(self, name: str) -> QueueResource:
        url = self._get_queue_url(name)
        return self._describe_queue(url)

    def send_message(self, name: str, body: str) -> MessageResource:
        url = self._get_queue_url(name)
        response = self._call(
            "SendMessage",
            lambda: self._client().send_message(QueueUrl=url, MessageBody=body),
            resource=name,
        )
        return MessageResource(
            message_id=response["MessageId"],
            receipt_handle="",  # SendMessage doesn't return one; not receiving this message.
            body=body,
        )

    def receive_messages(
        self, name: str, *, max_messages: int = DEFAULT_RECEIVE_MAX
    ) -> list[MessageResource]:
        url = self._get_queue_url(name)
        response = self._call(
            "ReceiveMessage",
            lambda: self._client().receive_message(
                QueueUrl=url,
                MaxNumberOfMessages=min(max(max_messages, 1), 10),  # SQS's own hard cap
                AttributeNames=["SentTimestamp", "ApproximateReceiveCount"],
            ),
            resource=name,
        )
        return [
            MessageResource(
                message_id=m["MessageId"],
                receipt_handle=m["ReceiptHandle"],
                body=m["Body"],
                sent_at=_epoch_ms_to_datetime(m.get("Attributes", {}).get("SentTimestamp")),
                approximate_receive_count=_to_int(m.get("Attributes", {}).get("ApproximateReceiveCount")),
            )
            for m in response.get("Messages", [])
        ]

    def delete_message(self, name: str, receipt_handle: str) -> None:
        url = self._get_queue_url(name)
        self._call(
            "DeleteMessage",
            lambda: self._client().delete_message(QueueUrl=url, ReceiptHandle=receipt_handle),
            resource=name,
        )

    # -- internal helpers -------------------------------------------------

    def _get_queue_url(self, name: str) -> str:
        response = self._call(
            "GetQueueUrl", lambda: self._client().get_queue_url(QueueName=name), resource=name
        )
        return response["QueueUrl"]

    def _describe_queue(self, url: str) -> QueueResource:
        response = self._call(
            "GetQueueAttributes",
            lambda: self._client().get_queue_attributes(
                QueueUrl=url,
                AttributeNames=["QueueArn", "ApproximateNumberOfMessages", "CreatedTimestamp"],
            ),
            resource=url,
        )
        attrs = response.get("Attributes", {})
        arn = attrs.get("QueueArn", "")
        name = url.rstrip("/").rsplit("/", 1)[-1]
        return QueueResource(
            id=name,
            name=name,
            url=url,
            arn=arn,
            region=self._provider_region(),
            created_at=_epoch_seconds_to_datetime(attrs.get("CreatedTimestamp")),
            approximate_message_count=_to_int(attrs.get("ApproximateNumberOfMessages")) or 0,
        )


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _epoch_seconds_to_datetime(value: str | None) -> datetime | None:
    n = _to_int(value)
    return datetime.fromtimestamp(n, tz=UTC) if n is not None else None


def _epoch_ms_to_datetime(value: str | None) -> datetime | None:
    n = _to_int(value)
    return datetime.fromtimestamp(n / 1000, tz=UTC) if n is not None else None
