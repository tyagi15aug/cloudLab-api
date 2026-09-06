# cloud-control-plane-api

Backend for the Cloud Control Plane project — a locally runnable,
AWS-console-style control plane backed by LocalStack, built as a full
vertical slice (UI → API → provider abstraction → infrastructure) rather
than a `boto3` wrapper. See `docs/implementation-plan.md` for the full
design and phase plan.

The React console lives in the sibling [`cloud-control-plane-web`](../cloud-control-plane-web)
repo.

**Status:** Phases 1–5 complete — LocalStack, the provider abstraction,
S3/SQS/DynamoDB backends, the React console, unit + integration + E2E
tests, and CI are all in place, plus a dev-only failure-injection layer
(`/api/dev/failures`) that can make any resource operation return an
HTTP 500/403, time out, throttle, add artificial latency, or fail to
connect — on demand, for resilience testing — and a dev-only operation
history/metrics layer (`/api/dev/operations`) recording every resource
call's request ID, duration, status, and error. See that repo's README
for the frontend, and "Phase 4"/"Phase 5" below for the design.

## Prerequisites

- Docker + Docker Compose
- Python 3.12 (only needed for running the API outside Docker)

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

This starts:

- **localstack** on `http://localhost:4566` (S3, SQS, DynamoDB)
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
Route (app/api/routes_{s3,sqs,dynamodb}.py)
  -> {S3,Sqs,DynamoDb}Service (app/services/)
      -> CloudProvider (app/providers/{localstack,aws}_provider.py)
          -> boto3 -> LocalStack or real AWS
```

- **Provider abstraction** (`app/providers/`): services never construct a
  `boto3.client` themselves or know about a LocalStack endpoint URL. Switch
  `CLOUD_PROVIDER=aws` in `.env` to point the same service code at real AWS
  using boto3's default credential chain — no code changes required.
- **Service base class** (`app/services/base.py`, Phase 3): every service
  extends `ProviderService`, which owns timing + structured logging + error
  translation via one `self._call(...)` helper — added when SQS/DynamoDB
  joined S3 so a third resource didn't mean a third copy-paste of that
  plumbing. `app/services/pagination.py` similarly extracted S3's
  offset-cursor helpers for reuse (DynamoDB's item listing uses DynamoDB's
  own native `LastEvaluatedKey` pagination instead — see
  `dynamodb_service.py`'s docstring for why those are genuinely different
  problems, not one abstracted wrong).
- **Error model** (`app/core/errors.py`): every botocore exception is
  translated into an `AppError` with a stable `code` and a `retryable`
  flag, and serialized as `{"error": {"code", "message", "requestId",
  "retryable"}}`. Routes never leak raw AWS errors. Extended in Phase 3
  with SQS/DynamoDB error codes (`ResourceNotFoundException`,
  `ResourceInUseException`, `ConditionalCheckFailedException`, ...).
- **Structured logging** (`app/core/logging.py`): every request and every
  provider operation is logged as one JSON line, tagged with the request's
  `request_id` automatically via a contextvar — the same shape Phase 5's
  operation history (below) and Phase 6's CI log analyzer are meant to
  consume.
- **DynamoDB item conversion** (`app/services/dynamodb_service.py`): items
  are plain JSON above this service — it's the only place in the codebase
  that knows DynamoDB's typed `AttributeValue` wire format
  (`{"S": "x"}`, `{"N": "1"}`) exists. Also handles a real boto3 gotcha:
  `TypeSerializer` rejects native Python floats outright ("Use Decimal
  types instead"), which would 400 every item with a decimal value coming
  from a JSON request body without an explicit float→Decimal conversion.
- **Failure injection** (`app/core/failure_injection.py`, Phase 4): an
  in-memory, process-wide, thread-safe registry of failure rules that
  `ProviderService._call()` consults before every real provider call — see
  "Phase 4" below.
- **Operation history** (`app/core/operations.py`, Phase 5): an in-memory,
  process-wide, thread-safe ring buffer + metrics counters that
  `ProviderService._call()` also records into after every real provider
  call — see "Phase 5" below.

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
POST   /api/resources/s3/buckets                       {"name": "..."}
GET    /api/resources/s3/buckets/{name}
DELETE /api/resources/s3/buckets/{name}

GET    /api/resources/sqs/queues
POST   /api/resources/sqs/queues                       {"name": "..."}
GET    /api/resources/sqs/queues/{name}
DELETE /api/resources/sqs/queues/{name}
GET    /api/resources/sqs/queues/{name}/messages?max_messages=
POST   /api/resources/sqs/queues/{name}/messages       {"body": "..."}
POST   /api/resources/sqs/queues/{name}/messages/delete {"receipt_handle": "..."}

GET    /api/resources/dynamodb/tables
POST   /api/resources/dynamodb/tables                  {"name", "partition_key", "partition_key_type"?, "sort_key"?, "sort_key_type"?}
GET    /api/resources/dynamodb/tables/{name}
DELETE /api/resources/dynamodb/tables/{name}
GET    /api/resources/dynamodb/tables/{name}/items?page_size=&cursor=
POST   /api/resources/dynamodb/tables/{name}/items     {"item": {...}}
POST   /api/resources/dynamodb/tables/{name}/items/delete {"key": {...}}

GET    /api/dev/failures
POST   /api/dev/failures    {"service", "operation", "failure", "delay_ms"?, "probability"?}
DELETE /api/dev/failures
DELETE /api/dev/failures/{rule_id}

GET    /api/dev/operations?limit=
GET    /api/dev/operations/metrics
GET    /api/dev/operations/{operation_id}
DELETE /api/dev/operations
```

The `/api/dev/failures` and `/api/dev/operations` routes are deliberately
unauthenticated — see "Phase 4"/"Phase 5" below.

Message/item deletion use a `POST .../delete` action route rather than
`DELETE` with a path param — a receipt handle or a composite DynamoDB key
isn't a clean single URL segment (see the docstrings on
`routes_sqs.py#delete_message` / `routes_dynamodb.py#delete_item`).

## Repository layout

```text
app/
  api/        routes + dependency wiring (routes_s3, routes_sqs, routes_dynamodb, routes_dev, routes_operations)
  core/       config, structured logging, error model, failure_injection.py (Phase 4), operations.py (Phase 5)
  models/     pydantic resource/error schemas (resource, sqs, dynamodb, failure_injection, operations)
  providers/  CloudProvider abstraction (LocalStack/AWS)
  services/   base.py (shared ProviderService), pagination.py, and one
              service per resource (s3, sqs, dynamodb)
tests/
  test_*.py         unit tests (moto in-process mock) — 133 tests
  integration/      Phase 2.2 — real HTTP against a moto-server process — 13 tests
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
pytest tests --ignore=tests/integration --cov=app   # 133 unit tests
pytest tests/integration -v                          # 13 integration tests
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
./scripts/seed.sh         # (re-)create the plan's Section 12.1 demo resources
./scripts/dev-down.sh     # docker compose down (--volumes to also drop LocalStack state)
./scripts/reset.sh        # drop LocalStack state and bring the stack back up + reseeded
```

`seed.sh` creates: S3 `demo-assets`/`test-bucket`, SQS `orders`/`notifications`,
DynamoDB `users`/`orders` (both partitioned on `id`).

## Phase 3 — SQS, DynamoDB, and the resource-service base class

Adding SQS and DynamoDB after S3 is Phase 3's whole point (Section 3.1's
resource model, deliberately *not* forcing every AWS service into an
identical shape — a message and a table item have no "status" or "region"
of their own, so `MessageResource`/`ItemResource` don't carry those fields
just to look consistent):

- **SQS** (`app/services/sqs_service.py`): list/create/delete queues,
  send/receive/delete messages, queue detail (approximate message count).
  Queue names are used as this app's resource id — SQS itself addresses
  everything by queue URL, so `GetQueueUrl` is one extra provider call per
  operation, in exchange for an API that's name-addressed like S3's rather
  than leaking SQS's URL scheme into routes/frontend code. `ListQueues`
  intentionally isn't paginated — at this app's scale it's an honest
  choice, not a missing feature (see the docstring in `routes_sqs.py`).
- **DynamoDB** (`app/services/dynamodb_service.py`): list/create/delete
  tables, describe table, put/list/delete items, real pagination. Unlike
  S3's offset-based cursor, item listing uses DynamoDB's own
  `LastEvaluatedKey` continuation token (base64/JSON-encoded as this app's
  cursor) — Scan has no concept of an arbitrary offset, only "continue
  after this key."
- **`app/services/base.py`** (`ProviderService`): the timing + structured
  logging + error translation helper `S3Service` built for itself in Phase
  1 (`_call`), extracted so SQS/DynamoDB didn't have to copy-paste it —
  this is the backend's answer to Phase 3.4's "avoid copy/paste resource
  pages," applied to the service layer, not just the frontend.

A real bug this phase caught: boto3's `TypeSerializer` refuses native
Python floats outright when converting to DynamoDB's `AttributeValue`
format ("Float types are not supported. Use Decimal types instead.") —
every item with a decimal value in its JSON request body would have 400'd
without an explicit `float -> Decimal` conversion in
`dynamodb_service.py#_to_dynamo_compatible`.

## Phase 4 — Failure Injection

Phase 4's goal (Section 13 of the plan) was a real failure source the UI
and E2E suite could drive on demand, with the core guarantee that no
injected failure can leave the UI permanently stuck:

- **No new layer — reuse the existing seam.** Every resource operation
  already funnels through `ProviderService._call()` (Phase 3's shared
  base class, added for logging + error translation). Failure injection
  is a single extra line there —
  `failure_injector.apply(service=self.service_name, operation=operation)`
  before the real boto3 call — so `S3Service`, `SqsService`, and
  `DynamoDbService` needed zero changes to gain it.
- **`FailureInjector`** (`app/core/failure_injection.py`) is an in-memory,
  process-wide singleton guarded by a `threading.Lock()` — FastAPI runs
  sync route handlers in a thread pool, so concurrent add/list/apply calls
  are a real race, not a theoretical one. Rules aren't persisted and reset
  on process restart; that's intentional for a dev tool, not a shortcut.
- **Matching**: a rule's `service`/`operation` can each be `"*"` to match
  anything, so one rule can express "fail every SQS operation." Rules also
  carry `probability` (0.0–1.0, for flaky-not-broken scenarios) and
  `delay_ms` (0–30,000, clamped) to add latency before the failure fires
  — or before a non-failure returns, for the `latency` type.
- **Six failure types**, one meaningful distinction among them: `http_500`,
  `http_403`, `throttle`, and `connection_failure` all raise immediately
  after any configured delay. `timeout` also raises (a retryable
  `PROVIDER_UNAVAILABLE`) but only after its delay — simulating a call
  that was slow *and* ultimately failed. `latency` is the odd one out: it
  delays and then lets the real call proceed and succeed, for testing
  that a merely-slow response doesn't misrender as an error.
- **Unauthenticated, on purpose, for now** — `/api/dev/failures` is
  namespaced away from `/api/resources/...` specifically so it's easy to
  gate behind auth later (Phase 9 in the plan) without touching resource
  routes. This is a dev/test tool, not something to expose as-is in a
  production deployment.
- **Testing it at every layer**: `tests/test_failure_injection.py` (15
  tests) covers the registry in isolation — every failure type's exact
  `(code, status, retryable)` triple, wildcard matching, probability edge
  cases, clamping. `tests/test_routes_dev.py` (13 tests) drives the real
  routes against the `FakeProvider`/moto setup, including proving an
  injected failure genuinely short-circuits the real operation (e.g. a
  bucket that was supposed to be created never is). One integration test
  in `tests/integration/test_app_lifecycle.py` does the same against the
  real `LocalStackProvider` and a real moto-server socket, to rule out
  anything moto's in-process mock might paper over.

## Phase 5 — Observability and Operation Debugging

Phase 5's objective (Section 5 of the plan) was to make the system explain
what happened. Request IDs and structured logging already existed from
Phase 1; this phase adds the developer-facing history and metrics on top:

- **Same seam, again.** `ProviderService._call()` already logs every
  operation's outcome (Phase 1) and consults the failure injector before
  it runs (Phase 4). Phase 5 adds one more call there —
  `operation_recorder.record(...)` — right alongside the existing
  `log_operation(...)` call, so every resource operation is recorded with
  zero per-service code, matching Phase 4's "instrument the shared seam
  once" pattern exactly.
- **`OperationRecorder`** (`app/core/operations.py`) is an in-memory,
  process-wide singleton guarded by a `threading.Lock()` — same reasoning
  as `FailureInjector`. It keeps a bounded ring buffer (`deque(maxlen=200)`)
  of recent operations for `/api/dev/operations` and `/{id}`, plus
  separate cumulative counters (total count, error count, duration sum,
  and a per-service/operation breakdown) that deliberately *don't* live in
  the ring buffer, so `/api/dev/operations/metrics` stays accurate for the
  process's whole lifetime even once more than 200 operations have
  happened and older ones have aged out of history.
- **An injected failure and a real one are recorded identically.** By the
  time `_call()` reaches its `except AppError` branch, it can't tell
  whether that `AppError` came from Phase 4's failure injector or a real
  translated botocore exception — so both show up in operation history
  with the same shape (status="error", the error's code, its `retryable`
  flag). This is a feature, not a gap: the history panel reflects what
  actually happened to the request, not a sanitized version of it.
- **`/metrics` is registered before `/{operation_id}`** in
  `routes_operations.py` specifically so a request for it is never
  swallowed by the parameterized route — FastAPI/Starlette tries routes in
  declaration order, and `/metrics` failing the `int` conversion `{operation_id}`
  expects would otherwise matter if the order were reversed.
- **Testing it at every layer**, mirroring Phase 4's structure:
  `tests/test_operations.py` (14 tests) covers `OperationRecorder` in
  isolation — ring-buffer eviction, metrics math, request-id/retryable
  pass-through. `tests/test_routes_operations.py` (12 tests) drives the
  real routes against the `FakeProvider` setup, including proving that
  totals survive ring-buffer eviction and that both a failed and a
  succeeded call on the same operation both count correctly. One
  integration test in `tests/integration/test_app_lifecycle.py` proves the
  same against a real `LocalStackProvider` and a real moto-server socket.

## E2E tests

The `cloud-control-plane-web` repo's `tests/e2e/` (Playwright) drives the
real console in a real browser against this API — see that repo's README.
`scripts/dev-up.sh` above is the fastest way to get this API into the state
those tests expect.

## CI

`.github/workflows/ci.yml` runs lint, format check, type check, the unit
test suite (with coverage), the integration test suite, and a Docker build
on every push/PR to `main`.
