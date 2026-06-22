"""Context assembly + confidence (spec 007 AC 1,2; v3 §12.2)."""

from __future__ import annotations

from app.services.retrieval_service import RetrievedChunk, assemble_context, confidence_score


def _chunk(i: int, score: float, text: str = "x") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{i}",
        document_id=f"d{i}",
        document_name=f"Doc {i}",
        source_type="manual_upload",
        section_ref=f"p{i}",
        chunk_text=text,
        score=score,
    )


def test_confidence_is_mean_of_top_3():
    chunks = [_chunk(1, 0.9), _chunk(2, 0.6), _chunk(3, 0.3), _chunk(4, 0.1)]
    assert confidence_score(chunks) == round((0.9 + 0.6 + 0.3) / 3, 4)


def test_confidence_empty_is_zero():
    assert confidence_score([]) == 0.0


def test_assemble_context_truncates_over_cap():
    big = "word " * 500  # ~hundreds of tokens each
    chunks = [_chunk(i, 0.9 - i * 0.1, big) for i in range(5)]
    context, used, token_count, truncated = assemble_context(chunks, max_tokens=300)
    assert truncated is True
    assert len(used) < len(chunks)
    assert token_count <= 300
