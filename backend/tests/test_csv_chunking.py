"""G4: CSV is chunked by streaming rows in fixed batches (header repeated), so a large
sheet is never materialized as one list. Offline — no external services."""

from __future__ import annotations

from app.services.chunking import ROWS_PER_CHUNK, chunk_parsed
from app.services.parsing import parse_document


def test_csv_streams_into_row_batches():
    n = 120
    lines = ["h1,h2", *[f"a{i},b{i}" for i in range(n)]]
    parsed = parse_document(("\n".join(lines)).encode(), "csv")

    chunks = chunk_parsed(parsed)

    assert parsed.metadata["row_count"] == n
    assert len(chunks) == -(-n // ROWS_PER_CHUNK)  # ceil(120 / 50) == 3
    assert all(c.chunk_text.startswith("h1,h2") for c in chunks)
    assert chunks[0].metadata["row_range"] == [1, 50]
    assert chunks[-1].metadata["row_range"] == [101, 120]
