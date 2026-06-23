"""Shared request/response envelope types used by every /api/* route.

Mirrors the keel-ai contract: every success response is wrapped in
`{status, data, message}` (plus `meta` for paginated lists), and every error
is `{status: "fail", error_code, message, request_id}` (see main.py handlers).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    """Standard success envelope for all /api/* responses.

    Args:
        data: The response payload — any Pydantic model, dict, or list.
        message: Human-readable context string (defaults to empty).
        status: Always "success" — discriminates from ErrorResponse.
    """

    status: Literal["success"] = "success"
    data: T
    message: str = ""


class PageMeta(BaseModel):
    """Pagination metadata attached to PaginatedResponse."""

    total: int
    page: int
    page_size: int


class PaginatedResponse[T](BaseModel):
    """Success envelope for list endpoints that support pagination.

    Args:
        data: The page of items.
        meta: Pagination metadata (total count, current page, page size).
        message: Human-readable context string (defaults to empty).
    """

    status: Literal["success"] = "success"
    data: list[T]
    message: str = ""
    meta: PageMeta


class ErrorResponse(BaseModel):
    """Error envelope returned by all exception handlers in main.py.

    Formalises the {status, error_code, message, request_id} shape so OpenAPI
    can reference it in `responses=` annotations. `detail` is populated only on
    422 validation errors.
    """

    status: Literal["fail"] = "fail"
    error_code: str
    message: str
    request_id: str
    detail: list | None = None


def ok[T](data: T, message: str = "") -> ApiResponse[T]:
    """Construct a success envelope.

    Use this in every route handler instead of constructing ApiResponse directly::

        return ok(UserOut.model_validate(user), "Registered successfully.")

    Args:
        data: Response payload.
        message: Optional human-readable context.

    Returns:
        ApiResponse wrapping the payload.
    """
    return ApiResponse(data=data, message=message)


def paginated[T](
    items: list[T],
    total: int,
    page: int,
    page_size: int,
    message: str = "",
) -> PaginatedResponse[T]:
    """Construct a paginated success envelope for list endpoints.

    Args:
        items: The current page of results.
        total: Total count across all pages.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
        message: Optional human-readable context.

    Returns:
        PaginatedResponse wrapping the page and pagination metadata.
    """
    return PaginatedResponse(
        data=items,
        message=message,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )
