"""initial baseline — create all tables from the ORM metadata

Using ``metadata.create_all`` for the baseline guarantees the schema matches the
ORM models exactly (no hand-transcription drift). Subsequent revisions use normal
``alembic revision --autogenerate`` ops and diff against this baseline.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
