# CloudLab — Design & Implementation Plan

**Project type:** Full-stack cloud infrastructure management and testing platform  
**Primary goal:** Build a locally runnable and publicly demoable AWS-like control plane that demonstrates senior-level frontend, backend, cloud, testing, CI/CD, observability, and AI-assisted engineering practices.

---

## 1. Executive Summary

This project is intentionally more than an AWS console clone.

The product will provide an AWS-console-like web interface for interacting with AWS-compatible infrastructure running locally or in an isolated hosted environment. The application will use React on the frontend, FastAPI on the backend, and LocalStack as the primary AWS emulator.

The project will progressively evolve into a developer/testing platform with:

- AWS-style resource management
- A provider abstraction separating application logic from AWS/LocalStack
- Reusable resource definitions in the UI
- Unit and integration testing
- Playwright end-to-end testing
- Dockerized reproducible environments
- GitHub Actions CI
- Failure injection and unreliable-infrastructure simulation
- Request/operation observability
- AI/agentic CI log and test-failure analysis
- A CLI for developer workflows
- A hosted public demo

The key portfolio objective is not to demonstrate that the author can call `boto3`. It is to demonstrate that the author can design, build, test, operate, and evolve a non-trivial full-stack system.

---

# 2. Portfolio Objective

## 2.1 What a hiring manager should conclude

After reviewing the repository and demo, the intended conclusion is:

> This engineer has strong frontend architecture skills but also understands APIs, backend boundaries, cloud abstractions, infrastructure, testing, CI/CD, observability, failure modes, and developer tooling.

The project should demonstrate engineering judgment rather than merely technology usage.

## 2.2 What the project should NOT look like

Avoid presenting it as:

- A simple AWS UI clone
- A CRUD dashboard
- A FastAPI wrapper around `boto3`
- A LocalStack tutorial
- An AI chatbot attached to CI
- A collection of disconnected demos
- A project with tests added only after development is finished

## 2.3 Core engineering story

The project should tell this story:

```text
Cloud Management UI
        ↓
Well-defined API
        ↓
Provider abstraction
        ↓
AWS-compatible infrastructure
        ↓
Reproducible local environment
        ↓
Automated testing
        ↓
Failure injection
        ↓
CI/CD
        ↓
AI-assisted failure analysis
        ↓
Developer CLI
```

---

# 3. Product Vision

## 3.1 Working concept

CloudLab: a local cloud control plane for provisioning, inspecting, testing, and debugging AWS-style infrastructure without requiring access to real AWS resources.

## 3.2 Primary users

### Developer

Wants to:

- Create cloud resources locally
- Inspect resource state
- Experiment safely
- Reproduce failures
- Reset environments

### Frontend/backend engineer

Wants to:

- Test cloud-dependent application behavior
- Reproduce API failures
- See requests and responses
- Run deterministic E2E tests

### QA engineer

Wants to:

- Run realistic workflows
- Inject infrastructure failures
- Validate UI recovery behavior
- Run Playwright suites

### Reviewer/interviewer

Wants to:

- Understand the architecture quickly
- Run the application
- Inspect tests
- See CI results
- Evaluate engineering decisions

---

# 4. High-Level Architecture

```text
                         ┌──────────────────────┐
                         │      React UI        │
                         │                      │
                         │ Resource pages       │
                         │ Tables/forms         │
                         │ Metrics              │
                         │ Debug/operations     │
                         └──────────┬───────────┘
                                    │ HTTP
                                    ▼
                         ┌──────────────────────┐
                         │      FastAPI         │
                         │                      │
                         │ API routes           │
                         │ Validation           │
                         │ Authentication       │
                         │ Error mapping        │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Application Services │
                         │                      │
                         │ S3 service           │
                         │ SQS service          │
                         │ EC2 service          │
                         │ etc.                 │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Provider Abstraction │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
             ┌──────────────┐               ┌──────────────┐
             │ AWS Provider │               │ Local Provider│
             │   boto3      │               │  LocalStack   │
             └──────────────┘               └──────┬───────┘
                                                    │
                                             ┌──────▼──────┐
                                             │ LocalStack  │
                                             │             │
                                             │ S3          │
                                             │ SQS         │
                                             │ DynamoDB    │
                                             │ EC2         │
                                             │ VPC         │
                                             └─────────────┘

                    Cross-cutting infrastructure:

       ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
       │ Failure      │   │ Observability│   │ Test Harness │
       │ Injection    │   │ / Operations │   │ / Seed Data  │
       └──────────────┘   └──────────────┘   └──────────────┘

                         GitHub Actions
                               │
                               ▼
                         Test + Build
                               │
                               ▼
                         Playwright
                               │
                               ▼
                         Artifacts/Logs
                               │
                               ▼
                         AI CI Analyzer
```

---

# 5. Technology Strategy

## 5.1 Frontend

Recommended:

- React
- TypeScript
- Vite
- React Router
- State-management solution chosen deliberately rather than automatically
- Testing Library
- Vitest or equivalent unit-test runner
- Playwright
- ESLint
- Prettier

The frontend should emphasize reusable architecture rather than simply reproducing AWS screens.

## 5.2 Backend

Recommended:

- Python
- FastAPI
- Pydantic
- boto3
- pytest
- HTTP client/integration testing
- Structured logging

FastAPI should expose application-oriented APIs rather than leaking raw AWS SDK details directly into every route.

## 5.3 Infrastructure

Primary emulator:

- LocalStack
- Docker / Docker Compose

Secondary testing technology:

- Moto for fast isolated Python tests where appropriate

### Division of responsibility

```text
Moto
  → fast unit/service-level tests

LocalStack
  → integration tests
  → realistic workflows
  → Playwright environment
  → public demo environment
```

## 5.4 CI/CD

- GitHub Actions
- Docker Compose
- Test artifacts
- Playwright reports
- Failure screenshots/videos
- AI-assisted failure analysis

## 5.5 Future developer tooling

- CLI
- Shell-friendly environment lifecycle commands
- Resource seeding/reset commands
- Failure injection commands
- Test commands

---

# 6. Architectural Principles

## 6.1 Provider independence

Application services should not depend directly on LocalStack.

Preferred:

```text
Route
 ↓
Service
 ↓
Provider interface
 ↓
LocalStack provider
```

rather than:

```text
Route
 ↓
boto3 client configured with LocalStack URL
```

everywhere.

This gives the project a legitimate abstraction boundary.

## 6.2 Resource-oriented design

AWS resources should be represented consistently.

Examples:

- Resource metadata
- Resource identifier
- Region
- Status
- Created timestamp
- Tags
- Actions
- Error state

## 6.3 Testability as an architectural requirement

Every feature should be implemented with its test strategy.

Do not defer testing.

Feature development should follow:

```text
Design
 ↓
Implement
 ↓
Unit test
 ↓
Integration test
 ↓
E2E test where appropriate
 ↓
CI
```

## 6.4 Deterministic environments

A developer should be able to start a known environment from scratch.

Target:

```bash
docker compose up
```

and eventually:

```bash
cloudctl up
cloudctl seed
cloudctl test
cloudctl reset
cloudctl down
```

## 6.5 Observable operations

Important operations should be traceable:

```text
Request
 ↓
API
 ↓
Service
 ↓
Provider
 ↓
LocalStack
```

with:

- Request ID
- Operation name
- Duration
- Result
- Error
- Provider
- Resource

---

# 7. Scope and Resource Roadmap

Do not build every AWS service.

Start with a deliberately small resource set.

## Initial resources

### S3

Good first resource because:

- Easy to understand
- Strong UI opportunities
- CRUD operations
- Useful for testing
- Easy to demonstrate

### SQS

Introduces:

- Messages
- Queue operations
- Async behavior
- Visibility timeouts
- Different state semantics

### DynamoDB

Introduces:

- Tables
- Schemas
- Items
- Query/scan behavior
- Pagination

### EC2

Introduces:

- Instance lifecycle
- More complex state transitions
- Start/stop/reboot semantics

### VPC

Introduces:

- Resource relationships
- Nested/network-oriented concepts
- More interesting visualization opportunities

The order should be:

```text
S3
 ↓
SQS
 ↓
DynamoDB
 ↓
EC2
 ↓
VPC
```

Do not start with EC2/VPC simply because they sound more impressive.

---

# 8. Phase Plan

# Phase 0 — Project Definition and Repository Foundation

## Objective

Create the repository structure and engineering conventions before implementing product functionality.

## 0.1 Define product scope

Tasks:

1. Finalize project name.
2. Write one-paragraph product description.
3. Define initial supported resources.
4. Define explicit non-goals.
5. Define MVP.
6. Define success criteria.

### Deliverable

A concise product specification in the repository.

---

## 0.2 Repository structure

Proposed structure:

```text
cloud-control-plane/
├── apps/
│   ├── web/
│   └── api/
├── packages/
│   └── shared/
├── infrastructure/
│   ├── docker/
│   └── localstack/
├── tests/
│   ├── integration/
│   └── e2e/
├── scripts/
├── docs/
├── .github/
│   └── workflows/
├── docker-compose.yml
├── README.md
└── Makefile
```

Exact structure can evolve.

---

## 0.3 Engineering standards

Set up:

- TypeScript strict mode
- Python linting
- Formatting
- Commit conventions if desired
- Environment-variable conventions
- `.env.example`
- Pre-commit hooks if useful

---

## 0.4 Definition of Done

Every feature should eventually satisfy:

- Code implemented
- Unit tests
- Integration tests when applicable
- E2E test when user-facing workflow warrants it
- Documentation updated
- CI passes
- No unexplained lint/type errors

---

# Phase 1 — First Vertical Slice + Testing Foundation

This is the most important phase.

The goal is not to build a lot.

The goal is to prove the entire architecture works.

```text
React
 ↓
FastAPI
 ↓
Provider abstraction
 ↓
LocalStack
 ↓
S3
```

## 1.1 Start LocalStack

Tasks:

1. Add Docker Compose.
2. Add LocalStack.
3. Configure AWS credentials for local development.
4. Configure region.
5. Verify boto3 connectivity.
6. Add health-check/startup handling.

### Exit criteria

The backend can reliably communicate with LocalStack.

---

## 1.2 Build provider abstraction

Create a provider boundary.

Conceptually:

```python
class CloudProvider:
    ...
```

Then implement:

```text
LocalStackProvider
AWSProvider
```

The exact interface should emerge from real requirements rather than being over-engineered upfront.

---

## 1.3 Implement S3 backend

Tasks:

1. List buckets
2. Create bucket
3. Delete bucket
4. Get bucket metadata
5. Map AWS errors to application errors
6. Handle pagination where applicable
7. Add structured logging

---

## 1.4 Build basic React console

Tasks:

1. Application shell
2. Navigation
3. Resource section
4. S3 list page
5. Create bucket form
6. Delete action
7. Loading states
8. Empty states
9. Error states

Do not obsess over pixel-perfect AWS replication.

Prioritize:

- Clean information architecture
- Good UX
- Reusable components
- Clear state transitions

---

## 1.5 Frontend unit testing — start now

Set up:

- Component testing
- User interaction testing
- API mocking where appropriate
- Error-state testing
- Loading-state testing

Examples:

```text
BucketList
  ✓ renders buckets
  ✓ renders empty state
  ✓ displays loading state
  ✓ displays API failure
  ✓ invokes delete action

CreateBucket
  ✓ validates input
  ✓ submits request
  ✓ shows success
  ✓ handles failure
```

---

## 1.6 Backend unit testing — start now

Use Moto where it provides value.

Test:

- Service behavior
- Error translation
- Validation
- Provider interactions
- Edge cases

---

## 1.7 First GitHub Actions workflow

Do this before Phase 1 is finished.

CI should initially perform:

```text
Checkout
 ↓
Install dependencies
 ↓
Lint
 ↓
Type check
 ↓
Frontend unit tests
 ↓
Backend unit tests
 ↓
Build
```

### Important principle

The CI pipeline should evolve alongside the application.

---

## Phase 1 Exit Criteria

You should be able to:

1. Start LocalStack.
2. Start FastAPI.
3. Start React.
4. Open the console.
5. List S3 buckets.
6. Create a bucket.
7. Delete a bucket.
8. Run frontend unit tests.
9. Run backend tests.
10. Push to GitHub and see CI pass.

At this point, the project is already a legitimate vertical slice.

---

# Phase 2 — Integration Testing + Playwright

## Objective

Prove that the complete system works together.

---

## 2.1 Create environment bootstrap

Build scripts that:

1. Start LocalStack
2. Wait until healthy
3. Seed test resources
4. Start API
5. Start frontend
6. Run tests

The environment should be reproducible.

---

## 2.2 Add integration tests

Test:

```text
FastAPI
 ↓
Provider
 ↓
LocalStack
```

Examples:

- Create bucket
- Retrieve bucket
- Delete bucket
- Error response
- Missing resource
- Duplicate resource

---

## 2.3 Add Playwright

Start with only a few high-value workflows.

### E2E test #1

```text
Open console
 ↓
Navigate to S3
 ↓
Create bucket
 ↓
Verify bucket appears
 ↓
Delete bucket
 ↓
Verify bucket disappears
```

### E2E test #2

```text
Open S3
 ↓
Backend failure
 ↓
UI shows meaningful error
 ↓
Retry
 ↓
Operation succeeds
```

---

## 2.4 CI runs Playwright

GitHub Actions should now:

```text
Build
 ↓
Start Docker environment
 ↓
Seed LocalStack
 ↓
Start services
 ↓
Run Playwright
 ↓
Upload report
 ↓
Upload screenshots/videos on failure
```

---

## 2.5 Improve failure diagnostics

Every E2E failure should leave useful evidence:

- Playwright report
- Screenshot
- Video when appropriate
- Browser console logs
- API logs
- Backend logs

---

## Phase 2 Exit Criteria

A clean GitHub clone should be able to run the full automated test suite without manual cloud setup.

This is an important portfolio milestone.

---

# Phase 3 — Resource Architecture and Expansion

## Objective

Move from one resource to a reusable platform architecture.

---

## 3.1 Define resource model

Establish common concepts:

```text
Resource
 ├── type
 ├── id
 ├── name
 ├── status
 ├── region
 ├── tags
 └── actions
```

Do not force every AWS service into an artificial identical model.

Use common abstractions only where they genuinely help.

---

## 3.2 SQS

Implement:

- List queues
- Create queue
- Delete queue
- Send message
- Receive messages
- Delete message
- Queue details

Testing should include message lifecycle.

---

## 3.3 DynamoDB

Implement:

- List tables
- Create table
- Delete table
- Describe table
- List/query items where appropriate
- Pagination

This resource should introduce more sophisticated data handling.

---

## 3.4 Reusable frontend resource architecture

Build reusable:

- Resource table
- Resource header
- Action menu
- Confirmation dialog
- Pagination
- Filter controls
- Error presentation
- Loading states
- Empty states

Avoid copy/paste resource pages.

---

## 3.5 Resource definitions

Explore a metadata-driven model such as:

```text
ResourceDefinition
 ├── columns
 ├── filters
 ├── actions
 ├── detail sections
 ├── form definitions
 └── API mappings
```

The goal is not to make everything dynamically generated.

The goal is to make repeated console patterns reusable.

---

## Phase 3 Exit Criteria

Adding a new resource should require significantly less duplicated UI code than adding the first resource.

---

# Phase 4 — Failure Injection and Resilience Testing

This phase differentiates the project from a conventional CRUD application.

## Objective

Simulate the reality that cloud APIs fail.

---

## 4.1 Failure injection architecture

Introduce a layer between the application provider and LocalStack:

```text
Application
 ↓
Provider
 ↓
Failure Injection Layer
 ↓
LocalStack
```

---

## 4.2 Supported failures

Start with:

- HTTP 500
- HTTP 403
- Timeout
- Artificial latency
- Throttling
- Connection failure

Later:

- Malformed response
- Partial response
- Intermittent failure
- Probability-based failure

---

## 4.3 Failure configuration

Example model:

```json
{
  "service": "s3",
  "operation": "CreateBucket",
  "failure": "timeout",
  "delayMs": 3000,
  "probability": 1.0
}
```

---

## 4.4 Developer UI

Add:

```text
Developer Tools
 └── Failure Injection
      ├── Service
      ├── Operation
      ├── Failure type
      ├── Delay
      └── Probability
```

This should be clearly marked as a development/testing capability.

---

## 4.5 Playwright resilience tests

Examples:

```text
Create bucket
 ↓
Inject 500
 ↓
Attempt create
 ↓
Verify error state
 ↓
Disable failure
 ↓
Retry
 ↓
Verify success
```

And:

```text
Inject timeout
 ↓
Perform request
 ↓
Verify loading state
 ↓
Verify timeout handling
 ↓
Verify retry behavior
```

---

## 4.6 Engineering goal

The UI should never remain indefinitely stuck because a cloud operation failed.

Test:

- Loading states
- Retry behavior
- Duplicate submissions
- Stale state
- Partial updates
- Error recovery

---

# Phase 5 — Observability and Operation Debugging

## Objective

Make the system explain what happened.

---

## 5.1 Request IDs

Every backend request should have a correlation/request ID.

Example:

```text
request_id=8f3a21
```

---

## 5.2 Structured logs

Example conceptual event:

```json
{
  "request_id": "8f3a21",
  "operation": "CreateBucket",
  "service": "s3",
  "provider": "localstack",
  "duration_ms": 143,
  "status": 200
}
```

---

## 5.3 Operation history

Add a developer-facing operation panel:

```text
Recent Operations

CreateBucket       200    143ms
ListBuckets        200     41ms
DeleteBucket       500    217ms
```

---

## 5.4 Request detail view

Allow the developer to inspect:

- Request
- Response
- Status
- Duration
- Provider
- Error
- Request ID

Avoid exposing secrets or sensitive credentials.

---

## 5.5 Metrics

Track basic application metrics:

- Request count
- Error count
- Latency
- Resource operation count

Do not introduce a giant observability stack unless it adds real value.

---

# Phase 6 — Agentic CI Log Analysis

This should be built after the CI system already generates meaningful failures.

## Objective

Use AI to help engineers understand failed CI runs.

The AI should not simply summarize logs.

It should perform evidence-based failure analysis.

---

## 6.1 Input sources

Potential inputs:

- GitHub Actions logs
- Playwright report
- Screenshot
- Browser console logs
- Backend logs
- Failure-injection configuration
- Test name
- Git commit information

---

## 6.2 Analysis pipeline

```text
CI Failure
   ↓
Collect artifacts
   ↓
Normalize logs
   ↓
Identify failing test
   ↓
Correlate request ID
   ↓
Inspect API/backend logs
   ↓
Inspect infrastructure events
   ↓
Classify failure
   ↓
Generate evidence-backed diagnosis
   ↓
Suggest next action
```

---

## 6.3 Failure categories

Start with:

- Application bug
- Test bug
- Infrastructure failure
- Environment/setup failure
- Expected injected failure
- Timing/race condition
- Dependency failure

---

## 6.4 AI output

Example:

```text
Test:
S3 create bucket

Result:
FAILED

Classification:
Infrastructure-induced failure

Confidence:
High

Evidence:
- Playwright request returned HTTP 500
- Backend mapped the error correctly
- Failure injector was configured for CreateBucket
- UI assertion expected success state

Likely cause:
The test environment intentionally injected an S3 failure.

Recommended action:
Verify whether failure injection should have been disabled for this test.
```

The system should distinguish facts from hypotheses.

---

## 6.5 Agentic behavior

Later, allow the agent to:

- Inspect related logs
- Compare with previous successful runs
- Identify the first meaningful failure
- Correlate timestamps/request IDs
- Inspect test source
- Produce a diagnosis
- Suggest a code/test change

Do not allow automatic code modifications initially.

Human review should remain the default.

---

## 6.6 Portfolio presentation

A CI failure should visibly demonstrate the system:

```text
❌ Playwright failed

AI Analysis

Root cause:
LocalStack returned 500 because failure injection
was enabled for CreateBucket.

Evidence:
[3 linked evidence items]

Confidence:
92%

Suggested next step:
Disable the injected failure for the happy-path test.
```

This is a strong portfolio feature because it is attached to a real engineering workflow.

---

# Phase 7 — CLI / Developer Experience

## Objective

Turn the project into a developer tool rather than only a web application.

---

## 7.1 CLI commands

Potential interface:

```bash
cloudctl up
cloudctl down
cloudctl status
cloudctl seed
cloudctl reset
cloudctl resources
cloudctl test
cloudctl logs
```

Failure injection:

```bash
cloudctl failure list
cloudctl failure inject s3 CreateBucket 500
cloudctl failure clear
```

---

## 7.2 CLI design principle

The CLI should call the same application APIs/services where practical.

Avoid building a completely separate implementation.

---

## 7.3 Developer workflow

Target:

```bash
cloudctl up
cloudctl seed
cloudctl test
```

A developer should be productive within minutes.

---

# Phase 8 — Hosted Demo and Environment Isolation

## Objective

Make the project publicly viewable without requiring visitors to install anything.

---

## 8.1 Hosted architecture

Conceptually:

```text
Internet
   ↓
Frontend
   ↓
API
   ↓
LocalStack
```

All components should run in containers or managed equivalents.

---

## 8.2 Public demo constraints

The hosted demo must assume:

- Multiple users
- Untrusted input
- Resource cleanup
- Limited resources
- No production AWS credentials
- No sensitive data
- Potential abuse

---

## 8.3 Environment strategy

Start with a shared demo environment if necessary.

Later consider:

```text
User/session
   ↓
Ephemeral environment
   ↓
Dedicated LocalStack instance
```

Do not implement per-user infrastructure until the single-environment version is stable.

---

## 8.4 Demo mode

Consider a demo mode that:

- Seeds useful resources
- Prevents destructive global operations
- Automatically resets state
- Shows sample failures
- Explains the architecture

---

# Phase 9 — Performance, Security, and Polish

## 9.1 Performance

Measure rather than assume.

Potential areas:

- Dashboard request concurrency
- API latency
- Resource list rendering
- Pagination
- Caching
- Bundle size
- Playwright runtime

Document meaningful improvements.

---

## 9.2 Security

Even though the system is primarily a demo, demonstrate good practices:

- No hardcoded secrets
- Environment variables
- Input validation
- CORS configuration
- Authentication for administrative tools
- Rate limiting where appropriate
- Safe logging
- No credential leakage
- Protected failure-injection endpoints

---

## 9.3 UX polish

Focus on:

- Loading behavior
- Empty states
- Error recovery
- Confirmation dialogs
- Keyboard accessibility
- Responsive layout
- Clear destructive actions
- Useful developer diagnostics

---

# Phase 10 — Portfolio Packaging

## Objective

Make the engineering work easy for a hiring manager to evaluate.

---

## 10.1 README

README should contain:

1. What the project is
2. Why it exists
3. Architecture diagram
4. Feature list
5. Technology choices
6. Local setup
7. Demo URL
8. Testing
9. CI
10. Failure injection
11. AI analysis
12. CLI
13. Architecture decisions
14. Known limitations
15. Future work

---

## 10.2 Architecture Decision Records

Create small ADRs for meaningful decisions.

Examples:

```text
docs/adr/
├── 001-localstack-over-moto.md
├── 002-provider-abstraction.md
├── 003-playwright-strategy.md
├── 004-failure-injection.md
└── 005-ai-ci-analysis.md
```

Each ADR should explain:

- Context
- Options
- Decision
- Tradeoffs
- Consequences

This can be surprisingly valuable to reviewers.

---

## 10.3 Architecture diagrams

Include:

- System architecture
- CI pipeline
- Failure injection flow
- AI analysis flow
- Resource abstraction

Keep diagrams understandable.

---

## 10.4 Demo video

Create a short 2–4 minute walkthrough.

Suggested sequence:

```text
00:00 — Problem
00:20 — Architecture
00:45 — Create S3 resource
01:10 — Show operation tracing
01:30 — Inject failure
01:55 — Playwright catches failure
02:15 — GitHub Actions
02:35 — AI analyzes failure
03:00 — CLI
03:20 — Closing architecture
```

---

# 9. Testing Strategy

Testing is a first-class part of the architecture.

## 9.1 Test pyramid

```text
             ┌──────────────┐
             │   Playwright │
             │   E2E tests  │
             └──────────────┘
                    ▲
                    │
          ┌──────────────────┐
          │ Integration tests│
          │   LocalStack     │
          └──────────────────┘
                    ▲
                    │
          ┌──────────────────┐
          │    Unit tests    │
          │ React + Python   │
          │     + Moto       │
          └──────────────────┘
```

## 9.2 Unit tests

Fast, numerous, isolated.

Test:

- Components
- Hooks
- State transformations
- API clients
- Services
- Error mapping
- Validation

## 9.3 Integration tests

Test:

- API
- Provider
- LocalStack
- Resource lifecycle

## 9.4 E2E tests

Test only important user workflows.

Examples:

- Create resource
- Delete resource
- Resource detail
- Failure/retry
- Pagination
- Multi-step workflow

Do not turn every UI component into a Playwright test.

---

# 10. CI/CD Strategy

## Initial CI

```text
Lint
 ↓
Type check
 ↓
Unit tests
 ↓
Build
```

## Mature CI

```text
Lint
 ↓
Type check
 ↓
Unit tests
 ↓
Build
 ↓
Start LocalStack
 ↓
Seed infrastructure
 ↓
Start API
 ↓
Start frontend
 ↓
Integration tests
 ↓
Playwright
 ↓
Collect artifacts
 ↓
AI analysis on failure
```

---

# 11. Failure Injection Strategy

Failure injection is not just a UI feature.

It should be designed as a testability capability.

## Failure matrix

| Failure | Example | Purpose |
|---|---|---|
| 500 | Internal error | Error handling |
| 403 | Access denied | Permission handling |
| Timeout | 5-second delay | Loading/retry |
| Throttle | 429 | Backoff behavior |
| Network | Connection failure | Resilience |
| Latency | 2-second delay | UX behavior |
| Intermittent | 30% failure | Race/retry testing |

---

# 12. Data and State Strategy

## 12.1 Seed data

Provide deterministic seed data.

Example:

```text
S3:
  demo-assets
  test-bucket

SQS:
  orders
  notifications

DynamoDB:
  users
  orders
```

## 12.2 Reset

A reset should return the environment to a known state.

```bash
cloudctl reset
```

This is essential for reliable E2E tests.

---

# 13. API Design

Prefer application-level APIs.

Example:

```text
GET    /api/resources/s3/buckets
POST   /api/resources/s3/buckets
DELETE /api/resources/s3/buckets/{name}

GET    /api/resources/sqs/queues
POST   /api/resources/sqs/queues
DELETE /api/resources/sqs/queues/{name}
```

Developer endpoints can be separated:

```text
/api/dev/failures
/api/dev/operations
/api/dev/diagnostics
```

Avoid exposing raw boto3 method names directly as your public API.

---

# 14. Error Model

The frontend should receive consistent application errors.

Conceptual format:

```json
{
  "error": {
    "code": "RESOURCE_CREATE_FAILED",
    "message": "Unable to create bucket",
    "requestId": "8f3a21",
    "retryable": true
  }
}
```

This enables the UI to make intelligent decisions.

For example:

```text
retryable=true
   → show Retry

retryable=false
   → show actionable error

403
   → show permission problem

timeout
   → show retry + diagnostic information
```

---

# 15. Observability Model

Every significant operation should have:

```text
request_id
operation
service
resource
provider
start_time
duration
status
error
```

This data becomes useful not only for humans but also for the AI CI analyzer.

---

# 16. AI Analyzer Architecture

Potential architecture:

```text
GitHub Actions
      │
      ▼
Failure Collector
      │
      ├── CI logs
      ├── Playwright report
      ├── screenshots
      ├── backend logs
      └── metadata
      │
      ▼
Evidence Normalizer
      │
      ▼
Failure Analyzer
      │
      ▼
Structured Diagnosis
      │
      ▼
GitHub Check / PR Comment
```

The analyzer should produce structured output rather than free-form prose only.

Example:

```json
{
  "classification": "infrastructure_failure",
  "confidence": 0.92,
  "summary": "...",
  "evidence": [],
  "likelyCause": "...",
  "recommendedAction": "..."
}
```

---

# 17. Agentic CI Roadmap

## Version 1

AI only analyzes collected artifacts.

## Version 2

AI can inspect related logs automatically.

## Version 3

AI correlates:

- Test source
- Logs
- Request IDs
- Infrastructure state
- Previous runs

## Version 4

AI can propose a patch.

Human approval remains mandatory.

---

# 18. What Should Be Built First?

The exact order matters.

## Priority 1

```text
Repository
 ↓
Docker Compose
 ↓
LocalStack
 ↓
FastAPI
 ↓
Provider abstraction
 ↓
S3 API
 ↓
React shell
 ↓
S3 UI
```

## Priority 2

Immediately add:

```text
React unit tests
Backend unit tests
GitHub Actions
```

Do not postpone these.

## Priority 3

Then:

```text
Integration tests
 ↓
Playwright
 ↓
CI E2E execution
```

## Priority 4

Expand resources:

```text
SQS
 ↓
DynamoDB
 ↓
EC2
 ↓
VPC
```

## Priority 5

Add:

```text
Failure injection
 ↓
Resilience E2E tests
```

## Priority 6

Add:

```text
Observability
 ↓
Operation history
 ↓
Request correlation
```

## Priority 7

Add:

```text
AI CI analysis
```

## Priority 8

Add:

```text
CLI
```

## Priority 9

Host publicly.

## Priority 10

Polish and package for portfolio presentation.

---

# 19. What NOT to Build Early

Avoid these until the core architecture is proven:

- Full AWS service coverage
- Complex authentication
- Kubernetes
- Terraform integration
- Production AWS provisioning
- Per-user LocalStack environments
- Advanced distributed tracing
- Elaborate dashboards
- AI code modification
- Sophisticated plugin systems
- Pixel-perfect AWS console cloning

These are distractions until the core system works.

---

# 20. Definition of the MVP

The MVP is complete when:

```text
React
  ↓
FastAPI
  ↓
Provider abstraction
  ↓
LocalStack
  ↓
S3
```

supports:

- List
- Create
- Delete
- Loading/error states
- React unit tests
- Backend unit tests
- Integration test
- At least 2 Playwright workflows
- GitHub Actions
- Reproducible Docker environment
- README setup instructions

Everything else is post-MVP.

---

# 21. Definition of the Portfolio-Ready Version

The project becomes portfolio-ready when it demonstrates:

### Product

- Multiple AWS-style resources
- Clean console UX
- Hosted demo

### Architecture

- Provider abstraction
- Resource abstraction
- Clear API boundaries

### Testing

- Unit
- Integration
- Playwright
- Failure scenarios

### CI/CD

- GitHub Actions
- Dockerized test environment
- Artifacts

### Reliability

- Failure injection
- Retry/error handling
- Deterministic seed/reset

### Observability

- Request IDs
- Structured logs
- Operation history

### AI

- Evidence-based CI failure analysis

### Developer experience

- CLI
- One-command environment setup

### Documentation

- Architecture diagrams
- ADRs
- Tradeoffs
- Testing strategy

---

# 22. Hiring Manager Evaluation Criteria

The project should make the following visible.

## Frontend

- Component architecture
- State management
- Async UI
- Error handling
- Accessibility
- Performance
- Testing

## Backend

- API design
- Validation
- Error modeling
- Service boundaries
- Concurrency
- Testing

## Cloud

- AWS concepts
- SDK usage
- Resource lifecycle
- Infrastructure emulation
- Provider abstraction

## Testing

- Test pyramid
- Deterministic environments
- E2E strategy
- Failure simulation

## DevOps

- Docker
- CI
- Reproducible builds
- Artifacts
- Deployment

## Systems thinking

- Failure modes
- Observability
- State consistency
- Retries
- Isolation

## AI engineering

- Evidence collection
- Tool-assisted analysis
- Structured outputs
- Confidence
- Human-in-the-loop design

---

# 23. Recommended Development Rhythm

Do not treat phases as giant releases.

Use small vertical increments.

Example:

```text
Day/Iteration 1
  LocalStack + FastAPI

Day/Iteration 2
  Provider + S3 API

Day/Iteration 3
  React S3 page

Day/Iteration 4
  React tests

Day/Iteration 5
  Backend tests + CI

Day/Iteration 6
  Integration tests

Day/Iteration 7
  Playwright

Day/Iteration 8
  CI E2E
```

Then continue resource-by-resource.

Each increment should leave the repository in a working state.

---

# 24. Final Architecture Target

The eventual system should look approximately like this:

```text
                              ┌──────────────────┐
                              │   Public Demo    │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │    React App     │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │     FastAPI      │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │ Application Layer│
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │ Provider Layer   │
                              └────────┬─────────┘
                                       │
                            ┌──────────┴──────────┐
                            │                     │
                     ┌──────▼──────┐      ┌──────▼──────┐
                     │ AWS Provider│      │ LocalStack  │
                     └─────────────┘      └──────┬──────┘
                                                 │
                                   ┌─────────────┼─────────────┐
                                   │             │             │
                                  S3            SQS        DynamoDB
                                   │             │             │
                                  EC2           VPC          ...

              ┌─────────────────────────────────────────────────┐
              │              Cross-Cutting Systems              │
              │                                                 │
              │ Failure Injection │ Observability │ Test Seed   │
              └─────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   CLI / cloudctl │
                              └────────┬─────────┘
                                       │
                                       ▼
                              Same application APIs

                              ┌──────────────────┐
                              │ GitHub Actions   │
                              └────────┬─────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 │                     │                     │
                 ▼                     ▼                     ▼
              Unit tests          Integration           Playwright
              Moto/isolated       LocalStack             E2E
                 │                     │                     │
                 └─────────────────────┼─────────────────────┘
                                       ▼
                                  CI Artifacts
                                       │
                                       ▼
                                AI CI Analyzer
                                       │
                                       ▼
                              Diagnosis + Evidence
```

---

# 25. The Core Principle

The most important rule for this project is:

> **Build the engineering system at the same time as you build the product.**

Do not build a large console first and add tests, CI, observability, and AI afterward.

Instead:

```text
Small feature
   ↓
Tests
   ↓
CI
   ↓
Observable
   ↓
Expand
```

That approach will make the final repository much more convincing to a senior engineering interviewer.

The project should ultimately demonstrate not just that the application works, but that you understand **how to build software that remains understandable, testable, diagnosable, and evolvable as complexity increases.**
