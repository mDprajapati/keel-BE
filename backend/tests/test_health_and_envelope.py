"""Health + error-envelope shape (spec 000 AC 1,2,4)."""

from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.headers.get("X-Request-ID")  # request-id middleware sets it


def test_unknown_route_returns_envelope(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body) == {"error_code", "message", "request_id"}
    assert body["error_code"] == "NOT_FOUND"


def test_missing_auth_is_unauthenticated(client):
    # Dual-auth route with no bearer → 401 envelope (no DB access reached).
    resp = client.post("/api/search", json={"query": "hello"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] in {"UNAUTHENTICATED", "VALIDATION_ERROR"}
