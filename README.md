# cloud-control-plane-api

Backend for the Cloud Control Plane project — a locally runnable,
AWS-console-style control plane backed by LocalStack, built as a full
vertical slice (UI → API → provider abstraction → infrastructure) rather
than a `boto3` wrapper. See `docs/implementation-plan.md` for the full
design and phase plan.

The React console lives in the sibling [`cloud-control-plane-web`](../cloud-control-plane-web)
repo (Phase 1.4 — not built yet).

**Status:** Phase 1.1–1.3 done — LocalStack, the provider abstraction, and
the S3 backend exist. Phase 1.4+ (React console, tests, CI) is next.

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
tests/        Phase 1.6 (not implemented yet)
docs/
  implementation-plan.md
infrastructure/
scripts/
docker-compose.yml
.env.example
```

## Tests

Not yet implemented — Phase 1.6 of the plan (backend unit testing with
Moto) covers this. `requirements-dev.txt` is already pinned in
anticipation of it.
