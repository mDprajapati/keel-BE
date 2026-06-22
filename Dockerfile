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

# Install Python deps first for layer caching.
COPY pyproject.toml README.md ./
COPY app ./app
# Base install (no docling). Add ".[parse,connectors]" to enable Docling/GDrive.
RUN pip install --upgrade pip && pip install -e .

# Project files
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY docker ./docker
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["/app/docker/entrypoint.sh"]
