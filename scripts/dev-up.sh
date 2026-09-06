#!/usr/bin/env bash
# Phase 2.1: reproducible environment bootstrap.
#
# Starts LocalStack + the API via docker compose, waits for both to report
# healthy, then seeds deterministic demo data (Section 12.1 of the plan).
# Idempotent: safe to re-run against an already-running stack.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Starting LocalStack + API..."
docker compose up -d --build

echo "==> Waiting for the API to report healthy..."
for _ in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "==> API is healthy."
    ./scripts/seed.sh
    exit 0
  fi
  sleep 2
done

echo "==> Timed out waiting for the API to become healthy." >&2
echo "    Check: docker compose logs" >&2
exit 1
