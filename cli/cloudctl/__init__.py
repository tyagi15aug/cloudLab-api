"""cloudctl — developer CLI for the Cloud Control Plane local environment.

See cli/README.md for the design rationale (Phase 7 of the implementation
plan): infrastructure lifecycle commands delegate to the repo's existing
scripts/*.sh, and everything else talks to the real HTTP API — the same
one the React console calls.
"""

from __future__ import annotations

__version__ = "0.1.0"
