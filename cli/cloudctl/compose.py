"""Process/infrastructure lifecycle: `docker compose` and the repo's own
scripts.

`scripts/dev-up.sh`, `dev-down.sh`, `seed.sh`, and `reset.sh` already do
"start the stack" / "wait for health" / "seed demo data" / "reset state"
correctly — they know real details (healthcheck polling, idempotent
seeding) that would just get re-derived, and probably re-broken, if
rewritten here. So `up`/`down`/`seed`/`reset`/`test` just call those
scripts. `status` and `logs` have no script to lean on, so those talk to
`docker compose` directly.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

#: How many parent directories to walk before giving up.
_MAX_SEARCH_DEPTH = 8


class ProjectNotFoundError(Exception):
    pass


def find_project_root(start: Path | None = None) -> Path:
    """Locates the cloud-control-plane-api checkout, identified by
    `docker-compose.yml` sitting next to a `scripts/` directory — the two
    things every delegated command needs.

    Walks upward from `start` (default: cwd), the same way tools like git
    find their root, so `cloudctl` works from any subdirectory of the
    repo. `CLOUDCTL_PROJECT_ROOT` overrides this entirely, for running
    cloudctl against a checkout that isn't the current directory at all.
    """
    override = os.environ.get("CLOUDCTL_PROJECT_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / "docker-compose.yml").exists():
            raise ProjectNotFoundError(f"CLOUDCTL_PROJECT_ROOT={root} has no docker-compose.yml.")
        return root

    current = (start or Path.cwd()).resolve()
    for _ in range(_MAX_SEARCH_DEPTH):
        if (current / "docker-compose.yml").exists() and (current / "scripts").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent

    raise ProjectNotFoundError(
        "Couldn't find a cloud-control-plane-api checkout (looking for "
        "docker-compose.yml next to a scripts/ directory). Run cloudctl "
        "from inside the repo, or set CLOUDCTL_PROJECT_ROOT."
    )


def run_script(root: Path, script: str, *args: str, env: dict[str, str] | None = None) -> int:
    """Runs one of the repo's own scripts/*.sh, streaming its output
    straight through — these already print their own progress, so
    cloudctl doesn't duplicate that with a second layer of logging.
    """
    full_env = {**os.environ, **(env or {})}
    return subprocess.call([str(root / "scripts" / script), *args], cwd=root, env=full_env)


def compose(root: Path, *args: str) -> int:
    return subprocess.call(["docker", "compose", *args], cwd=root)
