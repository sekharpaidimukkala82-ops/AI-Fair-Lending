"""
Prometheus Metrics — Priority 4 Observability.

Exposes /metrics endpoint for Prometheus scraping.
Tracks: API latency, request count, model accuracy drift,
        fairness score trends, queue depths, error rates.
"""
from __future__ import annotations

import time
import logging
from typing import Callable

from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute

logger = logging.getLogger("fair_lending.metrics")

# ── Try to import prometheus_client (optional dep) ────────────────────────
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info,
        generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry, REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.info("prometheus_client not installed — metrics endpoint disabled")


# ── Metric definitions ────────────────────────────────────────────────────
if _PROMETHEUS_AVAILABLE:
    HTTP_REQUEST_COUNT = Counter(
        "fairlend_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"],
    )
    HTTP_REQUEST_LATENCY = Histogram(
        "fairlend_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )
    ACTIVE_WEBSOCKETS = Gauge(
        "fairlend_active_websockets",
        "Currently active WebSocket connections",
    )
    FAIRNESS_SCORE = Gauge(
        "fairlend_fairness_score",
        "Latest fairness score per dataset",
        ["dataset_id"],
    )
    ML_MODEL_ACCURACY = Gauge(
        "fairlend_ml_model_accuracy",
        "Current ML model accuracy",
        ["model_id"],
    )
    DATASETS_TOTAL = Gauge(
        "fairlend_datasets_total",
        "Total number of uploaded datasets",
    )
    DATASETS_PROCESSING = Gauge(
        "fairlend_datasets_processing",
        "Datasets currently being processed",
    )
    CELERY_QUEUE_DEPTH = Gauge(
        "fairlend_celery_queue_depth",
        "Celery queue depth",
        ["queue_name"],
    )
    FAIRNESS_VIOLATIONS = Counter(
        "fairlend_fairness_violations_total",
        "Total fairness violations detected",
        ["severity"],
    )
    AUDIT_ACTIONS = Counter(
        "fairlend_audit_actions_total",
        "Total audit log actions",
        ["action"],
    )
    PLATFORM_INFO = Info(
        "fairlend_platform",
        "Platform version and configuration info",
    )
    PLATFORM_INFO.info({
        "version": "2.0.0",
        "environment": "production",
        "embedding_model": "all-MiniLM-L6-v2",
    })


# ── Middleware ────────────────────────────────────────────────────────────
async def prometheus_middleware(request: Request, call_next: Callable) -> Response:
    """FastAPI middleware that records HTTP metrics for every request."""
    if not _PROMETHEUS_AVAILABLE:
        return await call_next(request)

    # Skip metrics endpoint itself to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        raise
    finally:
        duration = time.perf_counter() - start

        # Normalize path (strip UUIDs/IDs for label cardinality)
        path = _normalize_path(request.url.path)

        HTTP_REQUEST_COUNT.labels(
            method=request.method,
            endpoint=path,
            status_code=str(status_code),
        ).inc()

        HTTP_REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=path,
        ).observe(duration)


def _normalize_path(path: str) -> str:
    """Replace UUID/numeric segments with placeholders to reduce label cardinality."""
    import re
    path = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "{id}", path)
    path = re.sub(r"/\d+", "/{id}", path)
    return path


# ── Helper functions called by business logic ─────────────────────────────
def record_fairness_score(dataset_id: str, score: float) -> None:
    """Call after every fairness audit to update the gauge."""
    if _PROMETHEUS_AVAILABLE:
        FAIRNESS_SCORE.labels(dataset_id=dataset_id[:8]).set(score)


def record_model_accuracy(model_id: str, accuracy: float) -> None:
    if _PROMETHEUS_AVAILABLE:
        ML_MODEL_ACCURACY.labels(model_id=model_id[:8]).set(accuracy)


def record_fairness_violation(severity: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        FAIRNESS_VIOLATIONS.labels(severity=severity).inc()


def record_audit_action(action: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        AUDIT_ACTIONS.labels(action=action).inc()


def update_dataset_gauges(total: int, processing: int) -> None:
    if _PROMETHEUS_AVAILABLE:
        DATASETS_TOTAL.set(total)
        DATASETS_PROCESSING.set(processing)


def update_celery_queue_depth(queue_name: str, depth: int) -> None:
    if _PROMETHEUS_AVAILABLE:
        CELERY_QUEUE_DEPTH.labels(queue_name=queue_name).set(depth)


def update_websocket_count(count: int) -> None:
    if _PROMETHEUS_AVAILABLE:
        ACTIVE_WEBSOCKETS.set(count)


# ── /metrics route ────────────────────────────────────────────────────────
router = APIRouter(tags=["Observability"])


@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics scrape endpoint."""
    if not _PROMETHEUS_AVAILABLE:
        return Response(
            content="# prometheus_client not installed\n",
            media_type="text/plain",
            status_code=200,
        )

    # Update real-time gauges
    try:
        from backend.api.routes.ws import manager
        update_websocket_count(manager.active_count)
    except Exception:
        pass

    try:
        _update_celery_depths()
    except Exception:
        pass

    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


def _update_celery_depths() -> None:
    """Poll Redis for Celery queue depths."""
    import os
    import redis

    redis_url = os.getenv("CELERY_BROKER_URL", "")
    if not redis_url:
        return

    try:
        r = redis.from_url(redis_url, socket_connect_timeout=1)
        for q in ["default", "processing", "ml", "reports"]:
            depth = r.llen(q)
            update_celery_queue_depth(q, depth)
    except Exception:
        pass
