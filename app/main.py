from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes_health import router as health_router
from app.api.routes_s3 import router as s3_router
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import configure_logging, request_id_ctx
from app.models.resource import ErrorBody, ErrorResponse
from app.providers.factory import get_provider

logger = logging.getLogger("app.main")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a request_id to every request, echoes it back as a response
    header, and makes it available to every log line emitted while handling
    the request via the request_id contextvar (app/core/logging.py)."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response


def _verify_provider_connectivity() -> None:
    """Retry a cheap S3 call a few times before declaring the provider
    unreachable (Phase 1.1: "Add health-check/startup handling").

    docker-compose's `depends_on: condition: service_healthy` already keeps
    the api container from starting before LocalStack's own healthcheck
    passes, but that's a property of Compose, not of the app — running the
    API directly (`uvicorn app.main:app`) against a LocalStack that's still
    booting has no such guarantee, so the app retries on its own too.
    """
    settings = get_settings()
    provider = get_provider()
    last_error: Exception | None = None

    for attempt in range(1, settings.startup_retry_attempts + 1):
        try:
            provider.get_client("s3").list_buckets()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Provider connectivity check failed (attempt %s/%s): %s",
                attempt,
                settings.startup_retry_attempts,
                exc,
                extra={"provider": provider.name, "attempt": attempt},
            )
            time.sleep(settings.startup_retry_delay_seconds)
        else:
            logger.info(
                "Provider connectivity verified.",
                extra={"provider": provider.name, "attempt": attempt},
            )
            return

    logger.error(
        "Could not verify provider connectivity after %s attempts; starting anyway.",
        settings.startup_retry_attempts,
        extra={"provider": provider.name, "error": str(last_error)},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    _verify_provider_connectivity()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Cloud Control Plane API", lifespan=lifespan)

    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code.value,
                message=exc.message,
                requestId=request_id_ctx.get(),
                retryable=exc.retryable,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(by_alias=True))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Keep request-body validation errors in the same {"error": {...}}
        # shape as every other error (see section 14 of the plan) instead of
        # leaking FastAPI's default {"detail": [...]} format.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"{field}: {first.get('msg')}" if field else (first.get("msg") or "Invalid request.")
        body = ErrorResponse(
            error=ErrorBody(
                code=ErrorCode.VALIDATION_ERROR.value,
                message=message,
                requestId=request_id_ctx.get(),
                retryable=False,
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(by_alias=True))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", extra={"path": request.url.path})
        body = ErrorResponse(
            error=ErrorBody(
                code=ErrorCode.INTERNAL_ERROR.value,
                message="An unexpected error occurred.",
                requestId=request_id_ctx.get(),
                retryable=False,
            )
        )
        return JSONResponse(status_code=500, content=body.model_dump(by_alias=True))

    app.include_router(health_router)
    app.include_router(s3_router)

    return app


app = create_app()
