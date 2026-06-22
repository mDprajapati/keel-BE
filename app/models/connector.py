"""Connector + ConnectorCredential (encrypted refresh token, never logged)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConnectorStatus, TimestampMixin, UUIDMixin


class Connector(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "connectors"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # google_drive | onedrive
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ConnectorStatus.disconnected.value, nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_document_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConnectorCredential(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "connector_credentials"

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Encrypted at rest; NEVER logged.
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
