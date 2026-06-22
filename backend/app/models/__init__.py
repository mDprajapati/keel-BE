"""ORM models. Importing this package registers every table on ``Base.metadata``
(used by Alembic autogenerate and relationship resolution)."""

from app.models.api_key import ApiCallLog, ApiKey
from app.models.base import (
    ApiKeyScope,
    Base,
    ConnectorStatus,
    ConnectorType,
    EmbeddingStatus,
    FileType,
    IngestionStatus,
    Role,
    SourceType,
)
from app.models.chat import ChatMessage, Conversation
from app.models.connector import Connector, ConnectorCredential
from app.models.document import Document, DocumentChunk
from app.models.ingestion import IngestionError, IngestionJob, TokenUsage
from app.models.organization import Organization, Workspace
from app.models.user import OrganizationMember, RefreshToken, User

__all__ = [
    "Base",
    "Role",
    "SourceType",
    "IngestionStatus",
    "EmbeddingStatus",
    "FileType",
    "ApiKeyScope",
    "ConnectorType",
    "ConnectorStatus",
    "Organization",
    "Workspace",
    "User",
    "OrganizationMember",
    "RefreshToken",
    "Document",
    "DocumentChunk",
    "Conversation",
    "ChatMessage",
    "Connector",
    "ConnectorCredential",
    "ApiKey",
    "ApiCallLog",
    "IngestionJob",
    "IngestionError",
    "TokenUsage",
]
