# cloudctl (Phase 7)

A developer CLI for the Cloud Control Plane local environment — the plan's
Phase 7 objective: "turn the project into a developer tool rather than only
a web application."

```bash
cloudctl up                          # start LocalStack + API, seed demo data
cloudctl seed                        # (re-)create demo S3/SQS/DynamoDB resources
cloudctl resources                   # list everything, via the real API
cloudctl status                      # container status + API health
cloudctl logs [service] [-f]         # docker compose logs
cloudctl failure inject s3 CreateBucket 500   # make the next CreateBucket call fail
cloudctl failure list
cloudctl failure clear
cloudctl test [--skip-e2e] [--keep-up]        # scripts/verify-all.sh
cloudctl reset                       # drop LocalStack state, bring the stack back up
cloudctl down [--volumes]
```

Target workflow (plan Section 7.3 — "productive within minutes"):

```bash
cloudctl up
cloudctl seed
cloudctl test
```

## Install

```bash
pip install -e cli/            # from the cloud-control-plane-api repo root
cloudctl --version
```

No third-party dependencies — see "Why stdlib-only" below.

`cloudctl` auto-detects the repo root (walks upward looking for
`docker-compose.yml` next to `scripts/`, the same way `git` finds `.git`),
so it works from any subdirectory of the repo. Set `CLOUDCTL_PROJECT_ROOT`
to point it at a checkout that isn't your current directory.
`CLOUDCTL_API_URL` (or `--api-url`) overrides the API base URL, default
`http://localhost:8000`.

## Design principle (plan Section 7.2)

> The CLI should call the same application APIs/services where practical.
> Avoid building a completely separate implementation.

This cuts two ways here, and `cloudctl` follows both:

- **`up` / `down` / `seed` / `reset` / `test`** delegate to the repo's
  existing `scripts/*.sh` (`cloudctl/compose.py`) instead of re-deriving
  their logic in Python. Those scripts already encode real details —
  health-check polling, idempotent seed data, the exact `docker compose`
  invocations CI itself uses — that reimplementing here would either
  duplicate or subtly re-break. One implementation, two entry points.
- **`resources` / `failure *` / the health check inside `status`** have no
  existing script or business logic anywhere else — they're thin HTTP
  calls to the real API (`cloudctl/client.py`), the same endpoints the
  React console calls. There's nothing to avoid duplicating; this *is*
  "the same application API."

## Why stdlib-only

`cloudctl` uses only `urllib`, `subprocess`, `argparse`, and `pathlib` —
no `requests`, `click`, or `rich`. For a small CLI whose job is "make one
HTTP call or shell out to one script," a third-party HTTP client and a
third-party argument-parsing framework buy readability at the cost of
another thing to install and pin. `pip install -e cli/` with zero
transitive dependencies is also just a nicer story for a portfolio piece
someone might actually try.

## Tests

```bash
cd cli && python3 -m pytest tests -v
```

Every command is tested with `find_project_root`, `run_script`,
`compose`, and `ApiClient` all mocked out — no Docker, no real script
execution, no real HTTP server required. `ruff check .` / `ruff format
--check .` / `mypy cloudctl --ignore-missing-imports` from the repo root
cover this directory too.
