"""RequestIDMiddleware + CORS configuration.

Mirrors the client repo's `app/core/middleware.py` layout. Keeps keel-BE's
existing request-id mechanism (the `request_id_var` ContextVar in
`app.core.logging`) so structlog correlation and the error envelope keep working.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.core.logging import request_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every inbound request.

    Reuses an inbound `X-Request-ID` header if present, else generates one.
    Binds it to the `request_id_var` ContextVar (read by structlog and the
    error envelope) for the duration of the request, and echoes it back on the
    response so callers can correlate logs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


def add_cors_middleware(app: FastAPI, settings: Settings) -> None:
    """Attach CORSMiddleware with the allow-listed origins from settings.

    No wildcards — origins come from settings. Credentials (HttpOnly
    refresh-token cookie) are allowed.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
