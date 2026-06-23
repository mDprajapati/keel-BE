# Keel backend image (api + worker share it).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: build tools for compiled wheels; curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching. Project now lives under backend/.
COPY backend/pyproject.toml ./
COPY README.md ./
COPY backend/app ./app
# Ingestion worker + pipeline live in a separate top-level package (same image).
# Copied before the editable install so setuptools discovers `ingestion*` too.
COPY backend/ingestion ./ingestion
# Base install (no docling). Add ".[parse,connectors]" to enable Docling/GDrive.
RUN pip install --upgrade pip && pip install -e .

# Project files
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["/app/entrypoint.sh"]
