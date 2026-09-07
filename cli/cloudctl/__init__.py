"""cloudctl — developer CLI for the CloudLab local environment.

See cli/README.md for the reasoning: infra-lifecycle commands delegate to
the repo's existing scripts/*.sh, and everything else talks to the real
HTTP API — the same one the React console calls.
"""

from __future__ import annotations

__version__ = "0.1.0"
