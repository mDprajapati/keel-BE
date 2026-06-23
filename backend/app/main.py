"""FastAPI app factory — middleware (RequestID, CORS), error envelope, /health.

The app imports and boots without secrets/services (external clients are lazy).
Every error response is `{status: "fail", error_code, message, request_id}`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__, startup
from app.api import api_router
from app.core.config import settings
from app.core.errors import AppError, RateLimitError
from app.core.logging import configure_logging, get_logger, request_id_var
from app.core.middleware import RequestIDMiddleware, add_cors_middleware

configure_logging(settings.debug)
log = get_logger(__name__)


def _envelope(error_code: str, message: str, detail: list | None = None) -> dict:
    body: dict[str, object] = {
        "status": "fail",
        "error_code": error_code,
        "message": message,
        "request_id": request_id_var.get() or "",
    }
    if detail is not None:
        body["detail"] = detail
    return body


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await startup.on_startup()
    except Exception as exc:  # noqa: BLE001 — never block boot on optional init
        log.warning("startup_init_failed", error=str(exc))
    try:
        yield
    finally:
        from app.core.database import dispose_engine

        try:
            await dispose_engine()  # drain DB connections on shutdown
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            log.warning("engine_dispose_failed", error=str(exc))


def create_app() -> FastAPI:
    app = FastAPI(title="Keel Backend", version=__version__, lifespan=lifespan)

    add_cors_middleware(app, settings)
    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError):
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimitError) else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.error_code, exc.message),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0].get("msg", "Validation error") if errors else "Validation error"
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", msg, detail=jsonable_encoder(errors)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_request: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception):
        log.error("unhandled_exception", error=str(exc), exc_type=type(exc).__name__)
        return JSONResponse(
            status_code=500, content=_envelope("INTERNAL_ERROR", "Internal server error")
        )

    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready", tags=["health"])
    async def health_ready():
        """Readiness probe: verifies the API can reach its primary datastore (Postgres).
        Returns 503 if not ready so orchestrators don't route traffic to a broken pod."""
        from sqlalchemy import text

        from app.core.database import get_session_factory

        checks: dict[str, str] = {}
        ready = True
        try:
            async with get_session_factory()() as db:
                await db.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception:  # noqa: BLE001 — report, never raise
            checks["postgres"] = "error"
            ready = False
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "degraded", "checks": checks},
        )

    return app


app = create_app()
