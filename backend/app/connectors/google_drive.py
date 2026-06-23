"""Google Drive adapter (v3 §10).

Talks to Google's REST API over httpx (a core dep) — no Google SDK needed. Refresh
tokens are encrypted at rest with Fernet (cryptography, in the `connectors` extra).
Network + crypto are imported/created lazily so the app boots without creds or libs.

Live OAuth requires GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI to be
set; until then the connector reports "not connected" (parallel to the OPENAI_API_KEY
requirement for AI). The OAuth `state` is HMAC-signed to prevent callback forgery.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode

import httpx

from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 — public OAuth endpoint, not a secret
_DRIVE = "https://www.googleapis.com/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"


def is_configured() -> bool:
    return bool(settings.google_client_id and settings.google_redirect_uri)


def _secret_material() -> str:
    raw = settings.secret_key
    return raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)


# ---- OAuth state (HMAC-signed: connector_id.signature) ----
def sign_state(connector_id: str) -> str:
    sig = hmac.new(_secret_material().encode(), connector_id.encode(), hashlib.sha256).hexdigest()[
        :16
    ]
    return f"{connector_id}.{sig}"


def verify_state(state: str) -> str | None:
    connector_id, _, sig = state.partition(".")
    expected = hmac.new(
        _secret_material().encode(), connector_id.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return connector_id if sig and hmac.compare_digest(sig, expected) else None


def build_auth_url(connector_id: str) -> str:
    return f"{_AUTH}?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": sign_state(connector_id),
        }
    )


# ---- Token + Drive calls (httpx) ----
async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])


async def list_files(access_token: str, folder_id: str | None = None) -> list[dict]:
    parent = folder_id or "root"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_DRIVE}/files",
            params={
                "q": f"'{parent}' in parents and trashed=false",
                "fields": "files(id,name,mimeType)",
                "pageSize": 200,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return list(resp.json().get("files", []))


async def get_metadata(access_token: str, file_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_DRIVE}/files/{file_id}",
            params={"fields": "id,name,mimeType,size,modifiedTime"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def download_file(access_token: str, file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(
            f"{_DRIVE}/files/{file_id}",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.content


# ---- Refresh-token encryption at rest (Fernet, lazy) ----
def _fernet():
    from cryptography.fernet import Fernet  # lazy — lives in the `connectors` extra

    key = base64.urlsafe_b64encode(hashlib.sha256(_secret_material().encode()).digest())
    return Fernet(key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()
