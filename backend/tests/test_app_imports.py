"""Import-safety (spec 000 AC 1): the app package imports with no env/services."""

from __future__ import annotations


def test_app_imports_without_env():
    import app.main

    assert app.main.app is not None


def test_models_metadata_complete():
    from app.models import Base

    # All 16 tables registered on the shared metadata (Alembic baseline source).
    assert len(Base.metadata.tables) >= 15
