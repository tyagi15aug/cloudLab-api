#!/usr/bin/env bash
# Runs everything both CI jobs (test + e2e) do, in one command, on a normal
# machine with Docker installed. This is the fastest way to check "does the
# whole project still work" after a change, without pushing and waiting on
# GitHub Actions.
#
# Assumes this repo and cloud-control-plane-web are cloned as siblings on
# disk (the project is deliberately two separate repos, not a monorepo).
#
# Usage:
#   ./scripts/verify-all.sh            # full run; stops the stack afterward
#   ./scripts/verify-all.sh --keep-up  # leaves docker compose running after
#   SKIP_E2E=1 ./scripts/verify-all.sh # skip Docker/Playwright entirely
#                                       # (e.g. no Docker on this machine)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root (cloud-control-plane-api/)

WEB_DIR="../cloud-control-plane-web"
KEEP_UP=0
[[ "${1:-}" == "--keep-up" ]] && KEEP_UP=1

step() { echo; echo "==> $1"; }

# ---------------------------------------------------------------------------
# Backend: lint, types, unit + integration tests. None of this needs Docker
# — unit tests use moto's in-process mock, integration tests spin up their
# own moto.server subprocess (see tests/integration/conftest.py).
# ---------------------------------------------------------------------------
step "Backend: installing dependencies"
pip install -r requirements-dev.txt -q

step "Backend: lint (ruff check)"
ruff check .

step "Backend: format check (ruff format --check)"
ruff format --check .

step "Backend: type check (mypy)"
mypy app --ignore-missing-imports

step "Backend: unit tests (moto, no Docker)"
python3 -m pytest tests --ignore=tests/integration --cov=app --cov-report=term-missing

step "Backend: integration tests (moto.server, no Docker)"
python3 -m pytest tests/integration -v

# ---------------------------------------------------------------------------
# CLI (Phase 7): a separate installable package, zero third-party deps.
# ruff/ruff format above already cover cli/ (they run against the whole
# repo); mypy is scoped separately since cli/cloudctl is its own package.
# ---------------------------------------------------------------------------
step "CLI: installing cloudctl"
pip install -e cli/ -q

step "CLI: type check (mypy)"
mypy cli/cloudctl --ignore-missing-imports

step "CLI: tests"
(cd cli && python3 -m pytest tests -v)

# ---------------------------------------------------------------------------
# Frontend: lint, types, build, unit tests. None of this needs a running
# backend either — MSW mocks the API at the network layer for these tests.
# ---------------------------------------------------------------------------
if [[ ! -d "$WEB_DIR" ]]; then
  echo
  echo "!! Sibling repo not found at $WEB_DIR — clone cloud-control-plane-web" >&2
  echo "   next to this repo to run frontend checks and E2E tests." >&2
  exit 1
fi

step "Frontend: installing dependencies"
(cd "$WEB_DIR" && npm ci)

step "Frontend: lint (eslint)"
(cd "$WEB_DIR" && npm run lint)

step "Frontend: type check"
(cd "$WEB_DIR" && npm run typecheck)

step "Frontend: unit tests (vitest)"
(cd "$WEB_DIR" && npm test)

step "Frontend: build"
(cd "$WEB_DIR" && npm run build)

if [[ "${SKIP_E2E:-0}" == "1" ]]; then
  echo
  echo "SKIP_E2E=1 — skipping the real stack + Playwright run."
  echo "All non-E2E checks passed."
  exit 0
fi

# ---------------------------------------------------------------------------
# E2E: needs the real thing — real LocalStack + API via docker compose, then
# Playwright driving a real browser against it (see tests/e2e/README.md).
# ---------------------------------------------------------------------------
step "Starting LocalStack + API (docker compose)"
[[ -f .env ]] || cp .env.example .env
docker compose up -d --build

cleanup() {
  if [[ "$KEEP_UP" == "1" ]]; then
    echo
    echo "==> Leaving the stack running (--keep-up). Stop it with:"
    echo "    (cd $(pwd) && ./scripts/dev-down.sh)"
  else
    step "Stopping stack"
    docker compose down
  fi
}
trap cleanup EXIT

step "Waiting for the API to report healthy"
healthy=0
for _ in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != "1" ]]; then
  echo "API did not become healthy in time." >&2
  docker compose logs
  exit 1
fi

step "Seeding demo data"
./scripts/seed.sh

step "Frontend: Playwright E2E (against the real stack)"
(cd "$WEB_DIR" && npx playwright install --with-deps chromium && npm run test:e2e)

step "All checks passed: lint, types, unit, integration, build, and E2E."
