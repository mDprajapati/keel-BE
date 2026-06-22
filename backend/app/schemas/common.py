"""Shared schema primitives."""

from __future__ import annotations

from pydantic import BaseModel


class Paginated[T](BaseModel):
    data: list[T]
    total: int
    page: int
    limit: int


class ErrorEnvelope(BaseModel):
    error_code: str
    message: str
    request_id: str
