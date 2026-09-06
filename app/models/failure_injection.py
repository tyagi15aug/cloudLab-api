"""Phase 4: request/response models for the dev-only failure-injection API.

Kept separate from app/core/failure_injection.py's `FailureRule` dataclass
(the runtime registry entry) the same way every other resource keeps its
Pydantic wire model separate from its internal representation — the two
happen to look almost identical here, but that's incidental, not a reason
to collapse them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.failure_injection import WILDCARD, FailureType

#: Every real operation name this app issues, plus the wildcard — see each
#: service's `_call(...)` sites. Kept here (rather than imported from each
#: service module) so this module has no dependency on the service layer,
#: matching every other model file in app/models/.
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
