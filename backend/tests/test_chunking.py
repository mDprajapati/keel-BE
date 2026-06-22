"""Chunking rules (spec 004 AC 2)."""

from __future__ import annotations

from app.services.chunking import MAX_TOKENS, chunk_parsed
from app.services.parsing import ParsedDocument, Section


def test_text_chunks_respect_token_cap():
    text = " ".join(["lorem ipsum dolor sit amet"] * 800)
    parsed = ParsedDocument(text=text, sections=[Section(ref="Intro", text=text)])
    chunks = chunk_parsed(parsed)
    assert chunks, "expected at least one chunk"
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    assert all(c.chunk_index == i for i, c in enumerate(chunks))


def test_tabular_repeats_header_per_chunk():
    parsed = ParsedDocument(
        is_tabular=True, headers=["id", "value"], rows=[[str(i), f"v{i}"] for i in range(120)]
    )
    chunks = chunk_parsed(parsed)
    assert len(chunks) == 3  # 50 rows/chunk → 50,50,20
    assert all(c.chunk_text.startswith("id,value") for c in chunks)
