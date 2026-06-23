"""G1: Google Drive OAuth URL construction + HMAC-signed state (the parts verifiable
without Google credentials). Offline — no network, no DB."""

from __future__ import annotations

from app.connectors import google_drive
from app.core.config import settings


def test_state_sign_verify_roundtrip():
    signed = google_drive.sign_state("conn-123")
    assert google_drive.verify_state(signed) == "conn-123"
    assert google_drive.verify_state("conn-123.deadbeef") is None  # tampered signature
    assert google_drive.verify_state("conn-123") is None  # unsigned


def test_build_auth_url_has_required_params(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cid")
    monkeypatch.setattr(
        settings, "google_redirect_uri", "https://host/api/connectors/google_drive/oauth/callback"
    )

    url = google_drive.build_auth_url("conn-1")

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=cid" in url
    assert "response_type=code" in url
    assert "access_type=offline" in url  # required to receive a refresh_token
    assert "state=conn-1." in url  # signed state, not the bare id
    assert google_drive.is_configured() is True
