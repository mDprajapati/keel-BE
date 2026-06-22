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

from app.config import settings
from app.logging import get_logger

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
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    headers = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []
    return ParsedDocument(
        text=text, is_tabular=True, headers=headers, rows=body, metadata={"row_count": len(body)}
    )


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
        sections = [Section(ref=None, text=p.strip()) for p in text.split("\n\n") if p.strip()]
        return ParsedDocument(
            text=text, page_count=page_count, sections=sections, metadata={"parser": "docling"}
        )
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Docling failed to parse '{file_type}': {exc}") from exc


def parse_document(data: bytes, file_type: str, *, size_bytes: int | None = None) -> ParsedDocument:
    """Parse raw bytes into a `ParsedDocument`. `file_type` is the lowercase extension."""
    ft = file_type.lower().lstrip(".")
    streaming = bool(size_bytes and size_bytes > settings.stream_parse_threshold_bytes)
    if ft == "txt":
        return _parse_txt(data)
    if ft == "csv":
        return _parse_csv(data)
    if ft in _DOCLING_FORMATS:
        return _parse_with_docling(data, ft, streaming)
    raise ParseError(f"Unsupported file type: {ft}")
