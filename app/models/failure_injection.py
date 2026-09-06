"""Request/response models for the dev-only failure-injection API.

Kept separate from `FailureRule` (the dataclass the registry actually
stores, in app/core/failure_injection.py) the same way every other
resource keeps its wire model separate from its internal one. They look
almost identical right now — that's a coincidence, not a reason to merge
them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.failure_injection import WILDCARD, FailureType

#: Every real operation name this app issues, plus the wildcard — check
#: each service's `_call(...)` sites if you're adding a new one. Listed
#: here by hand rather than imported from the service modules, so this
#: file doesn't have to depend on the service layer.
KNOWN_SERVICES: tuple[str, ...] = (WILDCARD, "s3", "sqs", "dynamodb")
KNOWN_OPERATIONS: tuple[str, ...] = (
    WILDCARD,
    # S3
    "ListBuckets",
    "CreateBucket",
    "DeleteBucket",
    "HeadBucket",
    "GetBucketLocation",
    "GetBucketTagging",
    # SQS
    "ListQueues",
    "CreateQueue",
    "DeleteQueue",
    "GetQueueUrl",
    "GetQueueAttributes",
    "SendMessage",
    "ReceiveMessage",
    "DeleteMessage",
    # DynamoDB
    "ListTables",
    "CreateTable",
    "DeleteTable",
    "DescribeTable",
    "Scan",
    "PutItem",
    "DeleteItem",
)


class FailureRuleResource(BaseModel):
    id: str
    service: str
    operation: str
    failure: FailureType
    delay_ms: int
    probability: float
    hit_count: int


class FailureRuleList(BaseModel):
    items: list[FailureRuleResource]


class CreateFailureRuleRequest(BaseModel):
    service: str = Field(min_length=1, max_length=32)
    operation: str = Field(min_length=1, max_length=64)
    failure: FailureType
    delay_ms: int = Field(default=0, ge=0, le=30_000)
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
