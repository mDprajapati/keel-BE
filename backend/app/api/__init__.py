"""Aggregate every router under the single `/api` prefix (matches keel-UI)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    admin_users,
    apikeys,
    auth,
    chat,
    connectors,
    conversations,
    dashboard,
    documents,
    ingest,
    mcp,
    model,
    search,
)
from app.api import settings as settings_router

api_router = APIRouter(prefix="/api")

for _router in (
    auth.router,
    documents.router,
    ingest.router,
    conversations.router,
    chat.router,
    search.router,
    apikeys.router,
    connectors.router,
    admin_users.router,
    dashboard.router,
    model.router,
    settings_router.router,
    mcp.router,
):
    api_router.include_router(_router)
