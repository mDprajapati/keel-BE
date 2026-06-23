"""Conversation history (JWT). Paginated to match keel-UI."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_current_user, get_db
from app.schemas.chat import ChatMessageOut, ConversationOut
from app.schemas.common import PaginatedResponse, paginated
from app.services import chat_service

router = APIRouter(tags=["chat"])


@router.get("/conversations", response_model=PaginatedResponse[ConversationOut])
async def list_conversations(
    principal: Principal = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    items = await chat_service.list_conversations(
        db, workspace_id=principal.workspace_id, user_id=principal.require_user()
    )
    return paginated(items, total=len(items), page=1, page_size=50)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[ChatMessageOut],
)
async def conversation_messages(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await chat_service.get_messages(
        db, workspace_id=principal.workspace_id, conversation_id=conversation_id
    )
    return paginated(items, total=len(items), page=1, page_size=50)
