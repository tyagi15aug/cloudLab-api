"""cloudctl entry point: argument parsing and command dispatch.

See cli/README.md for the full command reference and the split between
"delegates to scripts/*.sh" and "calls the real HTTP API" commands.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Any

from cloudctl import __version__
from cloudctl.client import DEFAULT_API_URL, ApiClient, CloudctlAPIError
from cloudctl.compose import ProjectNotFoundError, compose, find_project_root, run_script


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    if not rows:
        print("  (none)")
        return
    widths = [max(len(str(headers[i])), *(len(str(row[i])) for row in rows)) for i in range(len(headers))]

    def fmt(cells: Sequence[Any]) -> str:
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths, strict=True))

    print(fmt(headers))
    print(fmt(["-" * w for w in widths]))
    for row in rows:
        print(fmt(row))


# ---------------------------------------------------------------------------
# Commands that just call the repo's own scripts/*.sh — see compose.py's
# docstring for why these don't get their own Python implementation.
# ---------------------------------------------------------------------------


def cmd_up(_args: argparse.Namespace) -> int:
    root = find_project_root()
    return run_script(root, "dev-up.sh")


def cmd_down(args: argparse.Namespace) -> int:
    root = find_project_root()
    return run_script(root, "dev-down.sh", *(["--volumes"] if args.volumes else []))


def cmd_seed(_args: argparse.Namespace) -> int:
    root = find_project_root()
    return run_script(root, "seed.sh")


def cmd_reset(_args: argparse.Namespace) -> int:
    root = find_project_root()
    return run_script(root, "reset.sh")


def cmd_test(args: argparse.Namespace) -> int:
    root = find_project_root()
    env = {"SKIP_E2E": "1"} if args.skip_e2e else {}
    return run_script(root, "verify-all.sh", *(["--keep-up"] if args.keep_up else []), env=env)


# ---------------------------------------------------------------------------
# Commands that talk to `docker compose` directly — no script covers these.
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    root = find_project_root()
    print("==> Containers (docker compose ps)")
    compose_exit = compose(root, "ps")
    print()

    client = ApiClient(base_url=args.api_url)
    try:
        health = client.health()
    except CloudctlAPIError as exc:
        print(f"==> API: unreachable at {args.api_url} — {exc}")
        return compose_exit or 1
    print(f"==> API: healthy at {args.api_url} — {health}")
    return compose_exit


def cmd_logs(args: argparse.Namespace) -> int:
    root = find_project_root()
    extra = ["-f"] if args.follow else []
    if args.service:
        extra.append(args.service)
    return compose(root, "logs", *extra)


# ---------------------------------------------------------------------------
# Commands that call the real HTTP API (client.py) — nothing else
# implements these, so this is the only place they can live.
# ---------------------------------------------------------------------------


def cmd_resources(args: argparse.Namespace) -> int:
    client = ApiClient(base_url=args.api_url)
    services = [args.service] if args.service else ["s3", "sqs", "dynamodb"]
    try:
        if "s3" in services:
            print("S3 buckets:")
            _print_table(["name", "region"], [[b["name"], b["region"]] for b in client.list_buckets()])
            print()
        if "sqs" in services:
            print("SQS queues:")
            _print_table(
                ["name", "approximate_message_count"],
                [[q["name"], q["approximate_message_count"]] for q in client.list_queues()],
            )
            print()
        if "dynamodb" in services:
            print("DynamoDB tables:")
            _print_table(
                ["name", "status", "item_count"],
                [[t["name"], t["status"], t["item_count"]] for t in client.list_tables()],
            )
    except CloudctlAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_failure_list(args: argparse.Namespace) -> int:
    client = ApiClient(base_url=args.api_url)
    try:
        rules = client.list_failures()
    except CloudctlAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_table(
        ["id", "service", "operation", "failure", "delay_ms", "probability", "hit_count"],
        [
            [
                r["id"],
                r["service"],
                r["operation"],
                r["failure"],
                r["delay_ms"],
                r["probability"],
                r["hit_count"],
            ]
            for r in rules
        ],
    )
    return 0


def cmd_failure_inject(args: argparse.Namespace) -> int:
    client = ApiClient(base_url=args.api_url)
    try:
        rule = client.create_failure(
            service=args.service,
            operation=args.operation,
            failure=args.failure,
            delay_ms=args.delay_ms,
            probability=args.probability,
        )
    except CloudctlAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Injected rule {rule['id']}: {rule['service']}/{rule['operation']} -> {rule['failure']}")
    return 0


def cmd_failure_clear(args: argparse.Namespace) -> int:
    client = ApiClient(base_url=args.api_url)
    try:
        client.clear_failures()
    except CloudctlAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Cleared all failure rules.")
    return 0


def cmd_failure_delete(args: argparse.Namespace) -> int:
    client = ApiClient(base_url=args.api_url)
    try:
        client.delete_failure(args.rule_id)
    except CloudctlAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Deleted rule {args.rule_id}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudctl",
        description="Developer CLI for the CloudLab local environment.",
    )
    parser.add_argument("--version", action="version", version=f"cloudctl {__version__}")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("CLOUDCTL_API_URL", DEFAULT_API_URL),
        help=f"API base URL (default: {DEFAULT_API_URL}, or $CLOUDCTL_API_URL).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "up", help="Start LocalStack + API and seed demo data (scripts/dev-up.sh)."
    ).set_defaults(func=cmd_up)

    down = subparsers.add_parser("down", help="Stop the stack (scripts/dev-down.sh).")
    down.add_argument("--volumes", action="store_true", help="Also drop LocalStack's persisted state.")
    down.set_defaults(func=cmd_down)

    subparsers.add_parser(
        "seed", help="(Re-)create the demo S3/SQS/DynamoDB resources (scripts/seed.sh)."
    ).set_defaults(func=cmd_seed)

    subparsers.add_parser(
        "reset", help="Drop LocalStack state and bring the stack back up, reseeded (scripts/reset.sh)."
    ).set_defaults(func=cmd_reset)

    subparsers.add_parser("status", help="Show container status and API health.").set_defaults(
        func=cmd_status
    )

    logs = subparsers.add_parser("logs", help="Show docker compose logs.")
    logs.add_argument("service", nargs="?", help="Only show logs for this service (e.g. api, localstack).")
    logs.add_argument("-f", "--follow", action="store_true", help="Stream logs instead of a one-shot dump.")
    logs.set_defaults(func=cmd_logs)

    test = subparsers.add_parser("test", help="Run the full verification suite (scripts/verify-all.sh).")
    test.add_argument("--skip-e2e", action="store_true", help="Skip the Docker/Playwright E2E portion.")
    test.add_argument("--keep-up", action="store_true", help="Leave the stack running after E2E.")
    test.set_defaults(func=cmd_test)

    resources = subparsers.add_parser(
        "resources", help="List resources across all/one service via the real API."
    )
    resources.add_argument("--service", choices=["s3", "sqs", "dynamodb"], help="Only list this service.")
    resources.set_defaults(func=cmd_resources)

    failure = subparsers.add_parser("failure", help="Manage failure-injection rules (/api/dev/failures).")
    failure_sub = failure.add_subparsers(dest="failure_command", required=True)

    failure_sub.add_parser("list", help="List active failure rules.").set_defaults(func=cmd_failure_list)

    inject = failure_sub.add_parser(
        "inject", help="Add a failure rule, e.g. `cloudctl failure inject s3 CreateBucket 500`."
    )
    inject.add_argument("service", help='Service name, or "*" for any (e.g. s3, sqs, dynamodb).')
    inject.add_argument("operation", help='Operation name, or "*" for any (e.g. CreateBucket).')
    inject.add_argument(
        "failure",
        help="http_500 | http_403 | timeout | latency | throttle | connection_failure (or 500 / 403).",
    )
    inject.add_argument(
        "--delay-ms", type=int, default=0, help="Delay before applying the failure (max 30000)."
    )
    inject.add_argument(
        "--probability", type=float, default=1.0, help="Chance the rule fires, 0.0-1.0 (default: 1.0)."
    )
    inject.set_defaults(func=cmd_failure_inject)

    failure_sub.add_parser("clear", help="Remove every failure rule.").set_defaults(func=cmd_failure_clear)

    delete = failure_sub.add_parser("delete", help="Remove one failure rule by id.")
    delete.add_argument("rule_id")
    delete.set_defaults(func=cmd_failure_delete)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except ProjectNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
