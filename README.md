# cloud-control-plane-api

Backend for the Cloud Control Plane project — a locally runnable,
AWS-console-style control plane backed by LocalStack, built as a full
vertical slice (UI → API → provider abstraction → infrastructure) rather
than a `boto3` wrapper. See `docs/implementation-plan.md` for the full
design and phase plan.

The React console lives in the sibling [`cloud-control-plane-web`](../cloud-control-plane-web)
repo.

**Status:** Phases 1 and 2 complete — LocalStack, the provider abstraction,
the S3 backend, the React console, unit + integration + E2E tests, and CI
are all in place. See that repo's README for the frontend, and
`scripts/`/`tests/integration/` below for what Phase 2 added.

## Prerequisites

- Docker + Docker Compose
- Python 3.12 (only needed for running the API outside Docker)

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

This starts:

- **localstack** on `http://localhost:4566` (S3 only for now)
- **api** on `http://localhost:8000`

> **Note:** this was built and verified in a sandboxed environment whose
> network policy blocks pulling images from Docker Hub entirely (even
> `python:3.12-slim`), so `docker compose up` itself could not be run there.
> Everything else — the app code, both test suites, both builds — was
> verified for real; this compose file and Dockerfile are straightforward
> and should just work, but they're the first thing to confirm in an
> environment with normal registry access.

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok","provider":"localstack"}

curl -X POST http://localhost:8000/api/resources/s3/buckets \
  -H 'content-type: application/json' -d '{"name":"demo-bucket"}'

curl http://localhost:8000/api/resources/s3/buckets

curl http://localhost:8000/api/resources/s3/buckets/demo-bucket

curl -X DELETE http://localhost:8000/api/resources/s3/buckets/demo-bucket
```

Interactive API docs: `http://localhost:8000/docs`.

To run the console against this API, see `cloud-control-plane-web`'s README
— its dev server proxies `/api` and `/health` here automatically.

## Running the API without Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AWS_ENDPOINT_URL=http://localhost:4566  # localstack must be running separately
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=us-east-1
uvicorn app.main:app --reload
```

## Architecture

```text
Route (app/api/routes_s3.py)
  -> S3Service (app/services/s3_service.py)
      -> CloudProvider (app/providers/{localstack,aws}_provider.py)
          -> boto3 -> LocalStack or real AWS
```

- **Provider abstraction** (`app/providers/`): services never construct a
  `boto3.client` themselves or know about a LocalStack endpoint URL. Switch
  `CLOUD_PROVIDER=aws` in `.env` to point the same service code at real AWS
  using boto3's default credential chain — no code changes required.
- **Error model** (`app/core/errors.py`): every botocore exception is
  translated into an `AppError` with a stable `code` and a `retryable`
  flag, and serialized as `{"error": {"code", "message", "requestId",
  "retryable"}}`. Routes never leak raw AWS errors.
- **Structured logging** (`app/core/logging.py`): every request and every
  provider operation is logged as one JSON line, tagged with the request's
  `request_id` automatically via a contextvar — the same shape Phase 5's
  operation history and Phase 6's CI log analyzer are meant to consume
  later.

## Configuration

All via environment variables (see `.env.example` / `app/core/config.py`):

| Variable | Default | Notes |
|---|---|---|
| `CLOUD_PROVIDER` | `localstack` | `localstack` or `aws` |
| `AWS_REGION` | `us-east-1` | |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack only |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `test` / `test` | LocalStack accepts any value; leave unset for `CLOUD_PROVIDER=aws` and use the default credential chain instead |
| `LOG_LEVEL` | `INFO` | |

## API

```text
GET    /health
GET    /api/resources/s3/buckets?page_size=&cursor=
POST   /api/resources/s3/buckets            {"name": "..."}
GET    /api/resources/s3/buckets/{name}
DELETE /api/resources/s3/buckets/{name}
```

## Repository layout

```text
app/
  api/        routes + dependency wiring
  core/       config, structured logging, error model
  models/     pydantic resource/error schemas
  providers/  CloudProvider abstraction (LocalStack/AWS)
  services/   S3Service and friends
tests/
  test_*.py         unit tests (moto in-process mock)
  integration/      Phase 2.2 — real HTTP against a moto-server process
docs/
  implementation-plan.md
infrastructure/
scripts/
  dev-up.sh, seed.sh, dev-down.sh, reset.sh
.github/workflows/ci.yml
docker-compose.yml
.env.example
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests --ignore=tests/integration --cov=app   # 36 unit tests
pytest tests/integration -v                          # 9 integration tests
ruff check .                 # lint
ruff format --check .        # formatting
mypy app --ignore-missing-imports
```

**Unit tests** (`tests/*.py`) run against [moto](https://github.com/getmoto/moto)'s
in-process AWS mock rather than a real LocalStack container — sub-second,
no Docker required, and exactly what Section 5.3 of the plan calls for
("Moto for fast isolated Python tests"). `tests/conftest.py`'s
`FakeProvider` implements the same `CloudProvider` interface the real app
depends on, so these tests exercise real `S3Service` and route code, not a
parallel mock of it.

**Integration tests** (`tests/integration/`, Phase 2.2) spin up a real
`moto.server` subprocess and talk to it over real HTTP with the real
`LocalStackProvider` class and, in `test_app_lifecycle.py`, the real
FastAPI app including its startup connectivity-retry lifespan — the
network path the unit tests bypass by design. `tests/integration/conftest.py`
explains why moto-server rather than a real LocalStack container (same
Docker Hub sandbox limitation as above); a real LocalStack container is a
drop-in replacement — just point `AWS_ENDPOINT_URL` at it, no test code
changes.

One of these tests caught a genuine AWS quirk worth knowing about: S3's
`CreateBucket` is idempotent for the bucket's own owner in `us-east-1`
(200 OK on recreate) but raises `BucketAlreadyOwnedByYou`/`BucketAlreadyExists`
in every other region — moto reproduces this faithfully, so
`test_create_duplicate_bucket_maps_to_conflict_over_real_http` uses a
non-default region to actually exercise the conflict-mapping code path.

## Scripts (Phase 2.1)

```bash
./scripts/dev-up.sh       # docker compose up --build, wait for health, seed demo data
./scripts/seed.sh         # (re-)create the two demo buckets from the plan's Section 12.1
./scripts/dev-down.sh     # docker compose down (--volumes to also drop LocalStack state)
./scripts/reset.sh        # drop LocalStack state and bring the stack back up + reseeded
```

## E2E tests

The `cloud-control-plane-web` repo's `tests/e2e/` (Playwright) drives the
real console in a real browser against this API — see that repo's README.
`scripts/dev-up.sh` above is the fastest way to get this API into the state
those tests expect.

## CI

`.github/workflows/ci.yml` runs lint, format check, type check, the unit
test suite (with coverage), the integration test suite, and a Docker build
on every push/PR to `main`.
