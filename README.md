# cloud-control-plane-api

Backend for the Cloud Control Plane project — a locally runnable,
AWS-console-style control plane backed by LocalStack, built as a full
vertical slice (UI → API → provider abstraction → infrastructure) rather
than a `boto3` wrapper. See `docs/implementation-plan.md` for the full
design and phase plan.

The React console lives in the sibling [`cloud-control-plane-web`](../cloud-control-plane-web)
repo.

**Status:** Phase 1 complete (1.1–1.7) — LocalStack, the provider
abstraction, the S3 backend, the React console, unit tests on both sides,
and CI are all in place. See that repo's README for the frontend.

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
tests/        pytest + moto — service, error-mapping, and route tests
docs/
  implementation-plan.md
infrastructure/
scripts/
.github/workflows/ci.yml
docker-compose.yml
.env.example
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest                       # 36 tests: service logic, error mapping, routes
ruff check .                 # lint
ruff format --check .        # formatting
mypy app --ignore-missing-imports
```

Tests run against [moto](https://github.com/getmoto/moto)'s in-process AWS
mock rather than a real LocalStack container — sub-second, no Docker
required, and exactly what Section 5.3 of the plan calls for ("Moto for
fast isolated Python tests"). `tests/conftest.py`'s `FakeProvider`
implements the same `CloudProvider` interface the real app depends on, so
these tests exercise real `S3Service` and route code, not a parallel mock
of it.

## CI

`.github/workflows/ci.yml` runs lint, format check, type check, the test
suite (with coverage), and a Docker build on every push/PR to `main`.
