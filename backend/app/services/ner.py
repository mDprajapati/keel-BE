"""LLM-based NER + relationship extraction (v3 §9.5; AI timeline — not spaCy).

7 entity types incl. INDUSTRY; 4 relationship types. Best-effort: any failure
returns empty lists so the pipeline/chat never breaks.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.services.llm_gateway import call_llm

log = get_logger(__name__)

ENTITY_TYPES = ["PERSON", "ORGANIZATION", "PROJECT", "DOCUMENT", "PRODUCT", "DATE", "INDUSTRY"]
RELATION_TYPES = ["MENTIONS", "AUTHORED_BY", "BELONGS_TO", "REFERENCES"]
_HEAD_CHARS = 24000  # full-doc NER bounded for prompt size

_PROMPT = (
    "Extract named entities and relationships from the document. "
    f"Entity types: {', '.join(ENTITY_TYPES)}. "
    f"Relationship types: {', '.join(RELATION_TYPES)}. "
    'Return ONLY JSON: {"entities":[{"name":..,"type":..}],'
    '"relationships":[{"source":..,"target":..,"type":..,"confidence":0-1}]}. '
    "Use the exact type strings above."
)


@dataclass
class Entity:
    canonical_name: str
    entity_type: str


@dataclass
class Relation:
    source: str
    target: str
    rel_type: str
    confidence: float


def _parse(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    return json.loads(text[start : end + 1])


async def extract(
    text: str, *, workspace_id: str | uuid.UUID, session: Any = None
) -> tuple[list[Entity], list[Relation]]:
    if not text.strip():
        return [], []
    try:
        result = await call_llm(
            [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": text[:_HEAD_CHARS]},
            ],
            workspace_id=workspace_id,
            operation="ner",
            session=session,
        )
        data = _parse(result.content)
        entities = [
            Entity(
                canonical_name=str(e["name"]).strip(), entity_type=str(e["type"]).strip().upper()
            )
            for e in data.get("entities", [])
            if e.get("name") and str(e.get("type", "")).strip().upper() in ENTITY_TYPES
        ]
        relations = [
            Relation(
                source=str(r["source"]).strip(),
                target=str(r["target"]).strip(),
                rel_type=str(r["type"]).strip().upper(),
                confidence=float(r.get("confidence", 0.5)),
            )
            for r in data.get("relationships", [])
            if r.get("source")
            and r.get("target")
            and str(r.get("type", "")).strip().upper() in RELATION_TYPES
        ]
        return entities, relations
    except Exception as exc:  # noqa: BLE001 — graph is best-effort
        log.warning("ner_extraction_failed", error=str(exc))
        return [], []
