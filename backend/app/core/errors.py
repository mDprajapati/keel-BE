"""Application error hierarchy.

Raise these anywhere; the central handlers in ``app.main`` turn them into the
envelope ``{error_code, message, request_id}`` with the right HTTP status. Never
return ad-hoc error dicts from routers/services.
"""

from __future__ import annotations


class AppError(Exception):
    """Base for all expected application errors."""

    status_code: int = 400
    error_code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code


class BadRequestError(AppError):
    status_code = 400
    error_code = "BAD_REQUEST"


class InvalidFileTypeError(AppError):
    status_code = 400
    error_code = "INVALID_FILE_TYPE"


class UnauthorizedError(AppError):
    status_code = 401
    error_code = "UNAUTHENTICATED"


class ForbiddenError(AppError):
    status_code = 403
    error_code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class UnprocessableError(AppError):
    status_code = 422
    error_code = "UNPROCESSABLE"


class LastAdminError(AppError):
    status_code = 422
    error_code = "LAST_ADMIN"


class RateLimitError(AppError):
    status_code = 429
    error_code = "RATE_LIMITED"

    def __init__(self, message: str = "Rate limit exceeded", *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamAIError(AppError):
    status_code = 502
    error_code = "UPSTREAM_AI_ERROR"
