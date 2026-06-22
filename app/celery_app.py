"""Celery app — dedicated `ingestion` queue, retry/backoff, 30/90-min timeouts."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery = Celery(
    "keel",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.tasks.ingestion"],
)

celery.conf.update(
    task_default_queue="ingestion",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_soft_time_limit=settings.ingestion_task_timeout_sec,  # 30 min
    task_time_limit=settings.large_file_timeout_sec,  # 90 min hard cap
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)
