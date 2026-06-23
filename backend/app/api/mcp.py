"""MCP placeholder (v3 §13.5) — exploratory; no server implemented in MVP."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.common import ok

router = APIRouter(tags=["mcp"])


@router.get("/mcp")
async def mcp_placeholder():
    return ok(
        {
            "status": "coming_soon",
            "message": "MCP support is planned for a later phase.",
            "planned_capabilities": [
                "context retrieval tools",
                "ingestion tools",
                "evidence lookup",
            ],
        }
    )
