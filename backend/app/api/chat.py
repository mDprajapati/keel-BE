"""Chat — SSE streaming (JWT) + non-streaming REST (dual auth)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import log_api_call
from app.core.deps import Principal, get_current_user, get_db, get_principal
from app.schemas.chat import ChatNonStreamResponse, ChatQuery
from app.schemas.common import ApiResponse, ok
from app.services import chat_service

router = APIRouter(tags=["chat"])


@router.post("/chat/query")
async def chat_query(payload: ChatQuery, principal: Principal = Depends(get_current_user)):
    """SSE stream: `data: <json>\\n\\n` frames (token* then done)."""

    async def event_stream() -> AsyncIterator[bytes]:
        async for event in chat_service.stream_answer(
            workspace_id=principal.workspace_id,
            user_id=principal.require_user(),
            query=payload.question,
            conversation_id=payload.conversation_id,
        ):
            yield f"data: {json.dumps(event)}\n\n".encode()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat", response_model=ApiResponse[ChatNonStreamResponse])
async def chat_rest(
    payload: ChatQuery,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    response = await chat_service.answer_once(
        workspace_id=principal.workspace_id,
        query=payload.question,
        conversation_id=payload.conversation_id,
        user_id=principal.user_id,
    )
    await log_api_call(db, principal, "/api/chat")
    return ok(response)
