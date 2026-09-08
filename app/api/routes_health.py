from __future__ import annotations

import concurrent.futures
import logging

from fastapi import APIRouter

from app.api.deps import ProviderDep
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger("app.api.routes_health")

router = APIRouter(tags=["health"])

# Distinct from `router` above (Master Plan §3.2 / CloudLab Implementation
# Plan §8.5) — this one is mounted under /api so it sits alongside every
# other route the SPA calls, and it's polled by the launch/cold-start
# splash screen rather than CI/tests/the CLI.
readiness_router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(provider: ProviderDep) -> dict:
    """Liveness + provider connectivity check.

    Actually probes the provider with a cheap, harmless S3 call
    (ListBuckets) instead of just returning 200 unconditionally — a
    container that boots fine but can't reach LocalStack/AWS should say
    so, not report "ok".
    """
    try:
        provider.get_client("s3").list_buckets()
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a health probe
        raise AppError(
            ErrorCode.PROVIDER_UNAVAILABLE,
            "Cloud provider is not reachable.",
            status_code=503,
            retryable=True,
            cause=exc if isinstance(exc, Exception) else None,
        ) from exc

    return {"status": "ok", "provider": provider.name}


def _probe_localstack(provider) -> str:
    """Same ListBuckets probe as `/health`, but bounded to a few seconds
    regardless of the provider's own client timeouts.

    This gets polled every ~2s by the splash screen while the app is
    cold-starting, so a slow-but-eventually-successful call is exactly as
    unhelpful here as an outright failure — either way the poll needs an
    answer now, not in 30s. Running it on a worker thread with
    `future.result(timeout=...)` bounds *this request's* wait without
    having to touch the cached client's own timeout config (which "/health"
    and every resource route also use, and shouldn't have shortened out
    from under them). The probe thread is abandoned (not cancelled) if it
    times out — `shutdown(wait=False)` so this endpoint doesn't itself hang
    waiting for a slow socket to give up.
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(lambda: provider.get_client("s3").list_buckets())
    try:
        future.result(timeout=3)
        return "ready"
    except Exception as exc:  # noqa: BLE001 - readiness probe, deliberately broad
        logger.info("Readiness check: provider not yet reachable: %s", exc)
        return "starting"
    finally:
        pool.shutdown(wait=False)


@readiness_router.get("/health")
def readiness(provider: ProviderDep) -> dict:
    """Aggregate cold-start readiness check for the SPA's launch screen.

    Unlike `/health` above, this always returns 200 — it's meant to be
    polled while the app is still waking up, and a 503/timeout here would
    read as "the API is down" instead of "still booting", which is the one
    thing a cold-start splash screen must not show. Each dependency is
    reported separately because this process can be up and answering
    before LocalStack (a separate, also-idle Render service) has finished
    waking from its own idle state — see Master Plan §3.2 / CloudLab
    Implementation Plan §8.5.
    """
    localstack_status = _probe_localstack(provider)
    overall = "ready" if localstack_status == "ready" else "starting"

    return {"api": "ready", "localstack": localstack_status, "overall": overall}
