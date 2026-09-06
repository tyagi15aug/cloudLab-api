"""SQS resource shapes.

SQS genuinely has two kinds of "resource" here — queues and messages — and
we don't force them into the same shape. A message has no name and no
status beyond "exists in the queue right now," so it gets its own model
instead of an awkward fit into the shared one. Queues get the shared
shape where it actually fits.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QueueResource(BaseModel):
    id: str = Field(..., description="The queue name; used as the id in this app's API.")
    name: str
    url: str
    arn: str
    region: str
    created_at: datetime | None = None
    approximate_message_count: int = 0
    tags: dict[str, str] = Field(default_factory=dict)


class QueueList(BaseModel):
    # No next_cursor here — see routes_sqs.py's list_queues comment for why
    # queues honestly don't paginate rather than faking a cursor for them.
    items: list[QueueResource]


class CreateQueueRequest(BaseModel):
    # SQS queue names: alphanumeric, hyphens, underscores, <= 80 chars.
    name: str = Field(..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class MessageResource(BaseModel):
    message_id: str
    receipt_handle: str
    body: str
    sent_at: datetime | None = None
    approximate_receive_count: int | None = None


class MessageList(BaseModel):
    items: list[MessageResource]


class SendMessageRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=262_144)  # SQS's own 256 KiB cap


class DeleteMessageRequest(BaseModel):
    receipt_handle: str
