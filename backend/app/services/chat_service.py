"""Chat service (v3 §12): conversations/messages + streamed & non-stream answers.

Manages its own DB sessions for persistence so it is robust during SSE streaming
(the request session lifecycle is independent of the long-lived stream)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.chat import ChatMessage, Conversation
from app.models.organization import Workspace
from app.schemas.chat import ChatMessageOut, ChatNonStreamResponse, ConversationOut, EvidenceChunk
from app.services import retrieval_service
from app.services.llm_gateway import call_llm, stream_llm

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are Keel, an enterprise context retrieval assistant. Answer the user's "
    "question using ONLY the provided context from their workspace documents. Cite "
    "sources naturally. If the context does not contain the answer, say so plainly. "
    "Do not invent facts."
)


def _evidence(chunks: list[retrieval_service.RetrievedChunk]) -> list[EvidenceChunk]:
    return [
        EvidenceChunk(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            document_name=c.document_name,
            source_type=c.source_type,
            section_ref=c.section_ref,
            excerpt=c.chunk_text[:200],
            similarity_score=round(c.score, 4),
        )
        for c in chunks
    ]


_HISTORY_TURNS = 10  # last N prior messages (~5 turns) fed to the model for multi-turn


def _messages(
    context: str, query: str, history: list[dict[str, str]] | None = None
) -> list[dict[str, str]]:
    user = (
        f"Context:\n{context}\n\nQuestion: {query}"
        if context
        else f"Question: {query}\n\n(No relevant context found.)"
    )
    msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history or [])  # prior turns (chronological) for multi-turn context
    msgs.append({"role": "user", "content": user})
    return msgs


async def _load_history(
    conversation_id: uuid.UUID | None, workspace_id: uuid.UUID, *, limit: int = _HISTORY_TURNS
) -> list[dict[str, str]]:
    """Prior turns (chronological) for multi-turn context; empty for a new conversation.

    Best-effort — never blocks answering on a history-load error. Uses its own session
    so it is safe on the long-lived SSE path."""
    if conversation_id is None:
        return []
    try:
        factory = get_session_factory()
        async with factory() as db:
            conv = await db.get(Conversation, conversation_id)
            if conv is None or conv.workspace_id != workspace_id:
                return []
            rows = (
                (
                    await db.execute(
                        select(ChatMessage)
                        .where(ChatMessage.conversation_id == conversation_id)
                        .order_by(ChatMessage.created_at.desc())
                        .limit(max(1, limit))
                    )
                )
                .scalars()
                .all()
            )
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]
    except Exception as exc:  # noqa: BLE001 — history is best-effort
        log.warning("history_load_failed", error=str(exc))
        return []


async def _ws_settings(
    workspace_id: uuid.UUID,
) -> tuple[str | None, int | None, float | None]:
    """Per-workspace chat_model / top_k / min_similarity applied at query time (v3 §15.1).

    Best-effort: on any error return Nones so retrieval + the gateway fall back to the
    global defaults. Uses its own session (safe on the long-lived SSE path)."""
    try:
        factory = get_session_factory()
        async with factory() as db:
            ws = await db.get(Workspace, workspace_id)
            if ws is None:
                return None, None, None
            return ws.chat_model, ws.chat_top_k, ws.min_similarity
    except Exception as exc:  # noqa: BLE001 — settings load is best-effort
        log.warning("ws_settings_load_failed", error=str(exc))
        return None, None, None


# ---- Reads (use the request session) ----
async def list_conversations(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID, limit: int = 50
) -> list[ConversationOut]:
    rows = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.workspace_id == workspace_id, Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [ConversationOut(id=c.id, title=c.title, updated_at=c.updated_at) for c in rows]


async def get_messages(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = 500,
) -> list[ChatMessageOut]:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != workspace_id:
        raise NotFoundError("Conversation not found")
    # Bound the query: fetch the most-recent `limit` messages, returned chronologically
    # (avoids loading an unbounded conversation history into memory).
    rows = (
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(max(1, limit))
            )
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [
        ChatMessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            confidence=m.confidence,
            evidence=[EvidenceChunk(**e) for e in (m.evidence or [])],
            created_at=m.created_at,
        )
        for m in rows
    ]


# ---- Persistence (own session) ----
async def _persist(
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
    query: str,
    answer: str,
    confidence: float,
    evidence: list[EvidenceChunk],
    chunk_ids: list[str],
) -> uuid.UUID:
    factory = get_session_factory()
    async with factory() as db:
        conv: Conversation | None = None
        if conversation_id is not None:
            conv = await db.get(Conversation, conversation_id)
        if conv is None:
            conv = Conversation(
                id=conversation_id or uuid.uuid4(),
                workspace_id=workspace_id,
                user_id=user_id or uuid.uuid4(),
                title=query[:48] or "New conversation",
            )
            db.add(conv)
            await db.flush()
        ev_json = [e.model_dump(mode="json") for e in evidence]
        db.add(
            ChatMessage(
                conversation_id=conv.id,
                workspace_id=workspace_id,
                role="user",
                content=query,
                evidence=[],
            )
        )
        db.add(
            ChatMessage(
                conversation_id=conv.id,
                workspace_id=workspace_id,
                role="assistant",
                content=answer,
                confidence=confidence,
                evidence=ev_json,
                retrieved_chunk_ids=[uuid.UUID(c) for c in chunk_ids if _is_uuid(c)] or None,
            )
        )
        conv.title = conv.title or query[:48]
        conv.updated_at = datetime.now(UTC)  # bubble to top of the conversation list
        await db.commit()
        return conv.id


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


# ---- SSE streaming (browser) ----
async def stream_answer(
    *, workspace_id: uuid.UUID, user_id: uuid.UUID, query: str, conversation_id: uuid.UUID | None
) -> AsyncIterator[dict[str, Any]]:
    try:
        chat_model, top_k, min_sim = await _ws_settings(workspace_id)
        history = await _load_history(conversation_id, workspace_id)
        chunks = await retrieval_service.retrieve(
            workspace_id=workspace_id, query=query, top_k=top_k, min_score=min_sim
        )
        context, used, _, _ = retrieval_service.assemble_context(chunks)
        evidence = _evidence(used)
        confidence = retrieval_service.confidence_score(used)

        answer_parts: list[str] = []
        async for token in stream_llm(
            _messages(context, query, history),
            workspace_id=workspace_id,
            operation="chat",
            model=chat_model,
        ):
            answer_parts.append(token)
            yield {"type": "token", "text": token}
        answer = "".join(answer_parts)

        conv_id = await _persist(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            answer=answer,
            confidence=confidence,
            evidence=evidence,
            chunk_ids=[c.chunk_id for c in used],
        )
        yield {
            "type": "done",
            "confidence": confidence,
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "conversation_id": str(conv_id),
        }
    except Exception as exc:  # noqa: BLE001 — surface as a stream error frame
        log.error("chat_stream_failed", error=str(exc))
        yield {"type": "error", "message": "Failed to generate an answer."}


# ---- Non-streaming (REST /api/chat) ----
async def answer_once(
    *,
    workspace_id: uuid.UUID,
    query: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID | None = None,
) -> ChatNonStreamResponse:
    chat_model, top_k, min_sim = await _ws_settings(workspace_id)
    history = await _load_history(conversation_id, workspace_id)
    chunks = await retrieval_service.retrieve(
        workspace_id=workspace_id, query=query, top_k=top_k, min_score=min_sim
    )
    context, used, _, _ = retrieval_service.assemble_context(chunks)
    evidence = _evidence(used)
    confidence = retrieval_service.confidence_score(used)
    result = await call_llm(
        _messages(context, query, history),
        workspace_id=workspace_id,
        operation="chat",
        model=chat_model,
    )
    conv_id = await _persist(
        workspace_id=workspace_id,
        user_id=user_id,
        conversation_id=conversation_id,
        query=query,
        answer=result.content,
        confidence=confidence,
        evidence=evidence,
        chunk_ids=[c.chunk_id for c in used],
    )
    return ChatNonStreamResponse(
        answer=result.content,
        confidence=confidence,
        evidence=evidence,
        conversation_id=str(conv_id),
    )
