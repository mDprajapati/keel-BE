"""Organization + Workspace (tenant root). Workspace holds runtime settings."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    workspaces: Mapped[list[Workspace]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Workspace(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Fixed at creation (no runtime switch)
    embedding_model: Mapped[str] = mapped_column(String(100), default="text-embedding-3-small")
    embedding_dims: Mapped[int] = mapped_column(Integer, default=1536)

    # Runtime-configurable settings (v3 §15)
    chat_model: Mapped[str] = mapped_column(String(50), default="gpt-4o-mini")
    chat_top_k: Mapped[int] = mapped_column(Integer, default=10)
    min_similarity: Mapped[float] = mapped_column(Float, default=0.65)
    auto_start_ingestion: Mapped[bool] = mapped_column(Boolean, default=True)
    rest_api_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    default_rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=100)

    organization: Mapped[Organization] = relationship(back_populates="workspaces")
