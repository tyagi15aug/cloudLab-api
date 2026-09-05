from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ProviderDep
from app.core.errors import AppError, ErrorCode

router = APIRouter(tags=["health"])


@router.get("/health")
def health(provider: ProviderDep) -> dict:
    """Liveness + provider connectivity check (Phase 1.1).

    A cheap, harmless S3 call (ListBuckets) is used as the connectivity
    probe rather than just returning 200 unconditionally — a container that
    boots fine but can't actually reach LocalStack/AWS should report
    unhealthy, not "ok".
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
