"""Application configuration (pydantic-settings).

Every value is read from the environment. Secrets are ``SecretStr``. Defaults let
the app construct/import without a ``.env`` (AI features still need a real key).
This is the ONLY place env vars are read — never call ``os.environ`` elsewhere.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # ---- App ----
    app_env: str = "local"
    debug: bool = True

    # ---- Security ----
    jwt_secret_key: SecretStr = SecretStr("dev-only-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 30
    bcrypt_rounds: int = 12
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- Postgres ----
    database_url: str = "postgresql+asyncpg://keel:keel@localhost:5432/keel"
    db_pool_size: int = 5
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

    # ---- Neo4j ----
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("keelneo4j")

    # ---- Object storage ----
    storage_backend: str = "s3"  # local | s3
    storage_local_path: str = "./data/objects"
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "keel"
    s3_access_key: SecretStr | None = SecretStr("minioadmin")
    s3_secret_key: SecretStr | None = SecretStr("minioadmin")
    s3_region: str = "us-east-1"

    # ---- OpenAI / AI ----
    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536
    chat_model_default: str = "gpt-4o-mini"
    embed_batch_size: int = 100
    embed_max_rpm: int = 3000

    # ---- Retrieval / chat ----
    chat_top_k: int = 10
    min_similarity: float = 0.65
    context_max_tokens: int = 8000

    # ---- Ingestion / Celery ----
    celery_ingestion_concurrency: int = 4
    ingestion_task_timeout_sec: int = 1800
    large_file_timeout_sec: int = 5400
    large_file_threshold_bytes: int = 104_857_600  # 100 MB
    max_upload_bytes: int = 524_288_000  # 500 MB
    multipart_threshold_bytes: int = 10_485_760  # 10 MB
    part_size_bytes: int = 5_242_880  # 5 MB
    stream_parse_threshold_bytes: int = 52_428_800  # 50 MB

    # ---- API ----
    rate_limit_per_minute: int = 100
    login_max_attempts: int = 10
    lockout_window_min: int = 15
    lockout_min: int = 15

    # ---- Derived ----
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

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
