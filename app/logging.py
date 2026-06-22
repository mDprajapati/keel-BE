"""structlog setup — JSON logs, request correlation, NO PII.

Never log passwords, tokens, API-key secrets, refresh cookies, or personal data.
Use ``log = get_logger(__name__)`` and ``log.info("event", key=value)`` — never ``print``.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog

# Per-request correlation id, bound by RequestIDMiddleware.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_logger, _name, event_dict):
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(debug: bool = False) -> None:
    """Idempotent structlog + stdlib logging configuration."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    renderer = structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
