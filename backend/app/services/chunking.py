"""Token-based + format-specific chunking (v3 §9.3).

target 512 / max 1024 / overlap 64 / min 50 tokens. Text → paragraph/section
chunks; tabular (CSV/XLSX) → row-based with the header repeated per chunk.
tiktoken is used when present, with a cheap char-based fallback otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.parsing import ParsedDocument, Section

TARGET_TOKENS = 512
MAX_TOKENS = 1024
OVERLAP_TOKENS = 64
MIN_TOKENS = 50
ROWS_PER_CHUNK = 50

_encoder = None
_encoder_tried = False


@dataclass
class ChunkData:
    chunk_index: int
    chunk_text: str
    token_count: int
    section_ref: str | None = None
    metadata: dict = field(default_factory=dict)


def _get_encoder():
    global _encoder, _encoder_tried
    if not _encoder_tried:
        _encoder_tried = True
        try:
            import tiktoken  # lazy/optional

            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001
            _encoder = None
    return _encoder


def count_tokens(text: str) -> int:
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)  # ~4 chars/token fallback


def _split_tokens(text: str) -> list[str]:
    """Token-bounded windows with overlap. Splits on whitespace; never mid-word."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, TARGET_TOKENS - OVERLAP_TOKENS)
    # ~0.75 words per token (1 token ≈ 0.75 words): size windows to the 512-token
    # target. (Previously divided, yielding ~900-token windows — far over target.)
    window_words = max(1, int(TARGET_TOKENS * 0.75))
    i = 0
    while i < len(words):
        piece = " ".join(words[i : i + window_words])
        # Enforce the hard cap by trimming if a window overshoots.
        while count_tokens(piece) > MAX_TOKENS and " " in piece:
            piece = piece.rsplit(" ", 1)[0]
        chunks.append(piece)
        i += max(1, int(step * 0.75))
    return chunks


def _chunk_text(parsed: ParsedDocument) -> list[ChunkData]:
    out: list[ChunkData] = []
    idx = 0
    buffer = ""
    buf_ref: str | None = None

    def flush(ref):
        nonlocal buffer, idx
        if buffer.strip():
            for piece in _split_tokens(buffer):
                out.append(
                    ChunkData(
                        chunk_index=idx,
                        chunk_text=piece,
                        token_count=count_tokens(piece),
                        section_ref=ref,
                    )
                )
                idx += 1
        buffer = ""

    sections = parsed.sections or [Section(ref=None, text=parsed.text)]
    for sec in sections:
        if count_tokens(buffer + " " + sec.text) > TARGET_TOKENS:
            flush(buf_ref)
            buf_ref = sec.ref
        buffer = (buffer + "\n\n" + sec.text).strip() if buffer else sec.text
        buf_ref = buf_ref or sec.ref
    flush(buf_ref)

    # Merge a trailing too-small chunk into its predecessor (min 50 tokens).
    if len(out) >= 2 and out[-1].token_count < MIN_TOKENS:
        prev = out[-2]
        prev.chunk_text = f"{prev.chunk_text}\n\n{out[-1].chunk_text}"
        prev.token_count = count_tokens(prev.chunk_text)
        out.pop()
    return out


def _chunk_tabular(parsed: ParsedDocument) -> list[ChunkData]:
    header = parsed.headers
    header_line = ",".join(header)
    out: list[ChunkData] = []
    for idx, start in enumerate(range(0, len(parsed.rows), ROWS_PER_CHUNK)):
        block = parsed.rows[start : start + ROWS_PER_CHUNK]
        body = "\n".join(",".join(str(c) for c in row) for row in block)
        text = f"{header_line}\n{body}" if header_line else body
        out.append(
            ChunkData(
                chunk_index=idx,
                chunk_text=text,
                token_count=count_tokens(text),
                section_ref=f"Rows {start + 1}-{start + len(block)}",
                metadata={"row_range": [start + 1, start + len(block)]},
            )
        )
    return out


def chunk_parsed(parsed: ParsedDocument) -> list[ChunkData]:
    return _chunk_tabular(parsed) if parsed.is_tabular else _chunk_text(parsed)
