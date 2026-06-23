"""LLM tag generation from the first ~2000 tokens (v3 §8.2). Best-effort."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.core.logging import get_logger
from app.services.llm_gateway import call_llm

log = get_logger(__name__)

MAX_TAGS = 20
MAX_TAG_LEN = 50
# ~2000 tokens ≈ 8000 chars; cheap, dependency-free bound for the tag prompt.
_HEAD_CHARS = 8000

_PROMPT = (
    "You generate concise topical tags for an enterprise document. "
    "Return ONLY a JSON array of 5-15 short lowercase tags (1-3 words each), "
    'no commentary. Example: ["finance", "q3 report", "compliance"].'
)


def _normalize(raw: list[Any]) -> list[str]:
    seen: list[str] = []
    for item in raw:
        tag = str(item).strip().lower()[:MAX_TAG_LEN]
        if tag and tag not in seen:
            seen.append(tag)
        if len(seen) >= MAX_TAGS:
            break
    return seen


def _parse_json_array(content: str) -> list[Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("[") :] if "[" in text else text
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    return json.loads(text[start : end + 1])


async def generate_tags(
    text: str, *, workspace_id: str | uuid.UUID, session: Any = None
) -> list[str]:
    if not text.strip():
        return []
    try:
        result = await call_llm(
            [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": text[:_HEAD_CHARS]},
            ],
            workspace_id=workspace_id,
            operation="tagging",
            session=session,
        )
        return _normalize(_parse_json_array(result.content))
    except Exception as exc:  # noqa: BLE001 — tagging never blocks ingestion
        log.warning("tag_generation_failed", error=str(exc))
        return []
