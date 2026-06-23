"""G2: chunked-upload assembly — parts saved by /ingest/file/part are concatenated in
order when /ingest/file finalizes the multipart upload (LocalStorage round-trip).
Offline — no external services."""

from __future__ import annotations

from app.stores.storage import LocalStorage


def test_local_multipart_assembles_parts_in_order(tmp_path):
    s = LocalStorage(str(tmp_path))
    upload_id = "u1"
    for n, chunk in enumerate([b"hello ", b"world", b"!"], start=1):
        s.save_part(upload_id, n, chunk)

    final = s.complete_multipart(upload_id, "workspaces/w/raw/d/out.txt", 3)

    assert s.get_bytes(final) == b"hello world!"
    assert s.size(final) == len(b"hello world!")
