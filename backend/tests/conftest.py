"""Test fixtures. These tests mock all adapters / avoid external services, so the
suite is green on a clean checkout (no Postgres/Redis/Qdrant/Neo4j/OpenAI needed).

The TestClient is created WITHOUT the lifespan context manager so startup does not
attempt to reach Neo4j.
"""

from __future__ import annotations

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
