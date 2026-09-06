#!/usr/bin/env bash
# Deterministic seed data (plan Section 12.1). Safe to re-run — bucket
# creation is idempotent for the same owner in us-east-1, and the API
# tolerates the "already exists" case for any other region gracefully
# (RESOURCE_ALREADY_EXISTS, which this script just ignores).
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

for bucket in demo-assets test-bucket; do
  echo "==> Seeding bucket: ${bucket}"
  curl -sf -X POST "${API_URL}/api/resources/s3/buckets" \
    -H 'content-type: application/json' \
    -d "{\"name\": \"${bucket}\"}" > /dev/null || true
done

echo "==> Seed complete. Current buckets:"
curl -sf "${API_URL}/api/resources/s3/buckets" | python3 -m json.tool
