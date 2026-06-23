"""Object storage adapter — local FS or S3-compatible (MinIO).

`STORAGE_BACKEND` selects the impl. Path convention:
`workspaces/{workspace_id}/raw/{document_id}/{filename}` (v3 §8.1). The S3 client
is built lazily so importing this module never connects.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def build_path(workspace_id: str, document_id: str, filename: str) -> str:
    return f"workspaces/{workspace_id}/raw/{document_id}/{filename}"


class StorageAdapter:
    def save_bytes(self, path: str, data: bytes) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def get_bytes(self, path: str) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError

    def save_part(self, upload_id: str, part_number: int, data: bytes) -> None:
        raise NotImplementedError

    def complete_multipart(self, upload_id: str, final_path: str, part_count: int) -> str:
        raise NotImplementedError


class LocalStorage(StorageAdapter):
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _full(self, path: str) -> Path:
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def save_bytes(self, path: str, data: bytes) -> str:
        self._full(path).write_bytes(data)
        return path

    def get_bytes(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def save_part(self, upload_id: str, part_number: int, data: bytes) -> None:
        self._full(f"_parts/{upload_id}/{part_number:06d}.part").write_bytes(data)

    def complete_multipart(self, upload_id: str, final_path: str, part_count: int) -> str:
        out = self._full(final_path)
        with out.open("wb") as fh:
            for n in range(1, part_count + 1):
                part = self.root / f"_parts/{upload_id}/{n:06d}.part"
                fh.write(part.read_bytes())
        return final_path


class S3Storage(StorageAdapter):
    def __init__(self) -> None:
        self._client: Any = None

    def _c(self) -> Any:
        if self._client is None:
            import boto3  # lazy

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key.get_secret_value()
                if settings.s3_access_key
                else None,
                aws_secret_access_key=settings.s3_secret_key.get_secret_value()
                if settings.s3_secret_key
                else None,
                region_name=settings.s3_region,
            )
        return self._client

    def save_bytes(self, path: str, data: bytes) -> str:
        self._c().put_object(Bucket=settings.s3_bucket, Key=path, Body=data)
        return path

    def get_bytes(self, path: str) -> bytes:
        return self._c().get_object(Bucket=settings.s3_bucket, Key=path)["Body"].read()

    def save_part(self, upload_id: str, part_number: int, data: bytes) -> None:
        self._c().put_object(
            Bucket=settings.s3_bucket, Key=f"_parts/{upload_id}/{part_number:06d}.part", Body=data
        )

    def complete_multipart(self, upload_id: str, final_path: str, part_count: int) -> str:
        # Client-side concat (simple + portable across S3-compatible stores).
        buf = bytearray()
        for n in range(1, part_count + 1):
            buf += self.get_bytes(f"_parts/{upload_id}/{n:06d}.part")
        return self.save_bytes(final_path, bytes(buf))


_adapter: StorageAdapter | None = None


def get_storage() -> StorageAdapter:
    global _adapter
    if _adapter is None:
        if settings.storage_backend == "local":
            _adapter = LocalStorage(os.path.abspath(settings.storage_local_path))
        else:
            _adapter = S3Storage()
    return _adapter
