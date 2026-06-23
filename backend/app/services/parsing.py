"""Docling parsing adapter (v3 §9, AI timeline).

Lazy-imports Docling so the app boots without it (it lives in the `parse` extra,
installed on the worker). TXT/CSV have native fallbacks that always work; rich
formats (PDF/DOCX/XLSX/PPTX) require Docling and raise `ParseError` if absent —
the pipeline treats that as a permanent failure (dead-letter, no retry).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_DOCLING_FORMATS = {"pdf", "docx", "pptx", "xlsx", "png", "jpg"}


class ParseError(Exception):
    """Permanent parse failure (unsupported/corrupt/parser unavailable)."""


@dataclass
class Section:
    ref: str | None
    text: str


@dataclass
class ParsedDocument:
    text: str = ""
    page_count: int = 1
    sections: list[Section] = field(default_factory=list)
    is_tabular: bool = False
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _parse_txt(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8", errors="replace")
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return ParsedDocument(
        text=text, sections=[Section(ref=None, text=p) for p in paras] or [Section(None, text)]
    )


def _parse_csv(data: bytes) -> ParsedDocument:
    # Materialize only the header + row count; data rows are streamed at chunk time
    # from `text` so a large CSV isn't copied twice (a full rows list AND text). v3 §9.3.
    # Note: `text` itself is still held in RAM (tagging/NER read it). True O(1)
    # streaming from object storage is deferred — see the note in parse_document.
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    headers = next(reader, [])
    row_count = sum(1 for _ in reader)
    return ParsedDocument(
        text=text, is_tabular=True, headers=headers, metadata={"row_count": row_count}
    )


def _sections_from_markdown(text: str) -> list[Section]:
    """Split markdown into paragraph sections, tagging each with the nearest preceding
    heading as its `section_ref` (v3 §9.1 — feeds the evidence panel's page/heading)."""
    sections: list[Section] = []
    current_ref: str | None = None
    for raw in text.split("\n\n"):
        block = raw.strip()
        if not block:
            continue
        lines = block.splitlines()
        if lines[0].lstrip().startswith("#"):
            current_ref = lines[0].lstrip("# ").strip() or current_ref
            rest = "\n".join(lines[1:]).strip()
            if rest:
                sections.append(Section(ref=current_ref, text=rest))
            continue
        sections.append(Section(ref=current_ref, text=block))
    return sections or [Section(ref=None, text=text)]


def _parse_with_docling(data: bytes, file_type: str, streaming: bool) -> ParsedDocument:
    try:
        from docling.document_converter import DocumentConverter  # lazy/optional
    except ImportError as exc:
        raise ParseError(
            f"Docling not installed — cannot parse '{file_type}'. Install the 'parse' extra."
        ) from exc

    try:
        converter = DocumentConverter()
        source = io.BytesIO(data)
        result = converter.convert(source)
        doc = result.document
        text = doc.export_to_markdown()
        page_count = len(getattr(doc, "pages", []) or []) or 1
        sections = _sections_from_markdown(text)
        return ParsedDocument(
            text=text, page_count=page_count, sections=sections, metadata={"parser": "docling"}
        )
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Docling failed to parse '{file_type}': {exc}") from exc


def parse_document(data: bytes, file_type: str, *, size_bytes: int | None = None) -> ParsedDocument:
    """Parse raw bytes into a `ParsedDocument`. `file_type` is the lowercase extension.

    Note: receives the whole file as `bytes` (already loaded by the worker from
    storage). CSV chunking streams rows (memory-safe), but Docling page-by-page parsing
    for very large PDFs and a storage-level stream seam (avoid loading 500 MB at once)
    are deferred — they need the `parse` extra + a live worker to verify.
    """
    ft = file_type.lower().lstrip(".")
    streaming = bool(size_bytes and size_bytes > settings.stream_parse_threshold_bytes)
    if ft == "txt":
        return _parse_txt(data)
    if ft == "csv":
        return _parse_csv(data)
    if ft in _DOCLING_FORMATS:
        return _parse_with_docling(data, ft, streaming)
    raise ParseError(f"Unsupported file type: {ft}")
