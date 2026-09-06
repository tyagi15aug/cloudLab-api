#!/usr/bin/env bash
# Deterministic seed data (plan Section 12.1). Safe to re-run — every
# creation call below tolerates "already exists" by ignoring curl's
# failure (|| true) rather than trying to pre-check existence.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

echo "==> Seeding S3 buckets..."
for bucket in demo-assets test-bucket; do
  curl -sf -X POST "${API_URL}/api/resources/s3/buckets" \
    -H 'content-type: application/json' \
    -d "{\"name\": \"${bucket}\"}" > /dev/null || true
done

echo "==> Seeding SQS queues..."
for queue in orders notifications; do
  curl -sf -X POST "${API_URL}/api/resources/sqs/queues" \
    -H 'content-type: application/json' \
    -d "{\"name\": \"${queue}\"}" > /dev/null || true
done

echo "==> Seeding DynamoDB tables..."
curl -sf -X POST "${API_URL}/api/resources/dynamodb/tables" \
  -H 'content-type: application/json' \
  -d '{"name": "users", "partition_key": "id"}' > /dev/null || true
curl -sf -X POST "${API_URL}/api/resources/dynamodb/tables" \
  -H 'content-type: application/json' \
  -d '{"name": "orders", "partition_key": "id"}' > /dev/null || true

echo "==> Seed complete."
echo "--- S3 ---"
curl -sf "${API_URL}/api/resources/s3/buckets" | python3 -m json.tool
echo "--- SQS ---"
curl -sf "${API_URL}/api/resources/sqs/queues" | python3 -m json.tool
echo "--- DynamoDB ---"
curl -sf "${API_URL}/api/resources/dynamodb/tables" | python3 -m json.tool
