#!/usr/bin/env bash
# Tears down the LocalStack + API stack started by dev-up.sh.
# Pass --volumes to also drop LocalStack's persisted state.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "${1:-}" == "--volumes" ]]; then
  echo "==> Stopping stack and removing volumes..."
  docker compose down --volumes
else
  echo "==> Stopping stack..."
  docker compose down
fi
