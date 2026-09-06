"""SQS resource shapes (Phase 3.2).

SQS's own "resource" is genuinely queue + message — the plan's shared shape
(Section 3.1: id/name/status/region/tags) is deliberately not forced onto
messages, which have no name and no meaningful "status" beyond existing in
the queue. Queues get the shared shape where it fits.
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
    # No next_cursor: see routes_sqs.py's list_queues docstring for why this
    # resource honestly doesn't paginate rather than faking a cursor.
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
