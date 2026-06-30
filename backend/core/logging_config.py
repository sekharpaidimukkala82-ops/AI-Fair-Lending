"""
Structured Logging — Priority 4 Observability.

Outputs JSON-formatted logs for Azure Monitor / Datadog / Grafana Loki.
Every log entry includes: timestamp, level, logger, message, and context fields.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    Compatible with: Azure Monitor, Datadog, Grafana Loki, CloudWatch.
    """

    LEVEL_MAP = {
        logging.DEBUG:    "debug",
        logging.INFO:     "info",
        logging.WARNING:  "warning",
        logging.ERROR:    "error",
        logging.CRITICAL: "critical",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level":     self.LEVEL_MAP.get(record.levelno, "info"),
            "logger":    record.name,
            "message":   record.getMessage(),
            "module":    record.module,
            "function":  record.funcName,
            "line":      record.lineno,
        }

        # Include exception info
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Include extra fields added via logger.info("msg", extra={"key": "val"})
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                payload[key] = value

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(
    level: str = "INFO",
    json_output: bool | None = None,
    app_name: str = "fair_lending",
) -> None:
    """
    Configure root logger and fair_lending loggers.

    In production (ENVIRONMENT=production or LOG_FORMAT=json), outputs JSON.
    In development, outputs human-readable colored text.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Auto-detect output format
    if json_output is None:
        json_output = os.getenv("ENVIRONMENT", "development") == "production" \
                   or os.getenv("LOG_FORMAT", "").lower() == "json"

    # Remove existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    root.setLevel(log_level)
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy in ["httpx", "httpcore", "uvicorn.access", "sqlalchemy.engine",
                  "chromadb", "sentence_transformers", "transformers"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("fair_lending").setLevel(log_level)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)

    logger = logging.getLogger(f"{app_name}.logging")
    logger.info(
        "Logging configured",
        extra={"format": "json" if json_output else "text", "level": level},
    )


class RequestContextFilter(logging.Filter):
    """Injects request_id into every log record during a request."""

    _request_id: str | None = None

    @classmethod
    def set_request_id(cls, request_id: str) -> None:
        cls._request_id = request_id

    @classmethod
    def clear(cls) -> None:
        cls._request_id = None

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = self._request_id or "-"  # type: ignore[attr-defined]
        return True
