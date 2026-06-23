"""Application configuration (pydantic-settings).

Field names mirror the client `keel-ai` convention (``SECRET_KEY``, ``NEO4J_URL``,
``CHAT_MIN_SIMILARITY``, ``MAX_UPLOAD_MB``, ``API_KEY_RATE_LIMIT_PER_MIN`` ...).
keel-BE-specific operational settings (DB pool sizing, multipart/stream
thresholds, login lockout) are retained — the client repo simply never needed
them. Secrets are ``SecretStr``. This is the ONLY place env vars are read.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # ---- App ----
    app_env: str = "local"
    debug: bool = True

    # ---- Security (client names: SECRET_KEY / ACCESS_TOKEN_EXPIRE_MINUTES / ...) ----
    secret_key: SecretStr = SecretStr("dev-only-change-me")
    jwt_algorithm: str = "HS256"  # keel-BE extra (client implies HS256)
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    bcrypt_rounds: int = 12  # keel-BE extra
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> list[str]:
        """Accept a JSON array string, a comma-separated string, or a list."""
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [o.strip() for o in s.split(",") if o.strip()]
        return v  # type: ignore[return-value]

    # ---- Postgres ----
    database_url: str = "postgresql+asyncpg://keel:keel@localhost:5432/keel"
    db_pool_size: int = 5  # keel-BE extras (no client equivalent)
    db_max_overflow: int = 10
    db_pool_recycle_sec: int = 1800  # recycle connections before server-side idle timeout
    db_pool_timeout_sec: int = 30  # fail fast instead of hanging when the pool is exhausted

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # ---- Qdrant ----
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    # ---- Neo4j (client names: NEO4J_URL / NEO4J_USERNAME) ----
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("keelneo4j")

    # ---- Object storage (client name: S3_ENDPOINT) ----
    storage_backend: str = "s3"  # local | s3
    storage_local_path: str = "./data/objects"
    s3_endpoint: str | None = "http://localhost:9000"
    s3_bucket: str = "keel"
    s3_access_key: SecretStr | None = SecretStr("minioadmin")
    s3_secret_key: SecretStr | None = SecretStr("minioadmin")
    s3_region: str = "us-east-1"  # keel-BE extra

    # ---- Google Drive connector (v3 §10; live OAuth requires these to be set) ----
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = (
        ""  # backend callback, e.g. https://host/api/connectors/google_drive/oauth/callback
    )
    frontend_url: str = "/"  # where the OAuth callback sends the browser back to

    # ---- OpenAI / AI (client name: CHAT_MODEL) ----
    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    chat_model: str = "gpt-4o-mini"
    embed_batch_size: int = 100
    embed_max_rpm: int = 3000

    # ---- Retrieval / chat (client name: CHAT_MIN_SIMILARITY) ----
    chat_top_k: int = 10
    chat_min_similarity: float = 0.65
    context_max_tokens: int = 8000

    # ---- Ingestion / Celery (client name: MAX_UPLOAD_MB) ----
    celery_ingestion_concurrency: int = 4
    ingestion_task_timeout_sec: int = 1800
    large_file_timeout_sec: int = 5400
    large_file_threshold_bytes: int = 104_857_600  # 100 MB
    max_upload_mb: int = 500
    multipart_threshold_bytes: int = 10_485_760  # 10 MB
    part_size_bytes: int = 5_242_880  # 5 MB
    stream_parse_threshold_bytes: int = 52_428_800  # 50 MB

    # ---- API (client name: API_KEY_RATE_LIMIT_PER_MIN) ----
    api_key_rate_limit_per_min: int = 100
    login_max_attempts: int = 10
    lockout_window_min: int = 15
    lockout_min: int = 15

    # ---- Derived ----
    @property
    def max_upload_bytes(self) -> int:
        """Byte ceiling derived from MAX_UPLOAD_MB (byte-comparison readers use this)."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def sync_database_url(self) -> str:
        """Sync DSN for Alembic / non-async contexts."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
