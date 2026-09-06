#!/usr/bin/env bash
# Resets the stack to a clean, freshly-seeded state without a full rebuild:
# drops LocalStack's volume, restarts, and re-seeds. Useful after manual
# poking-around, or before a demo/recording.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Resetting stack (drops LocalStack state)..."
docker compose down --volumes
./scripts/dev-up.sh
