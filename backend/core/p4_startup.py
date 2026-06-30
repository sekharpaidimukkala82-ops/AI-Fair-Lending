"""
Priority 4 startup hook — injected into backend/main.py at app startup.

Initializes:
  1. Structured JSON logging
  2. Sentry error tracking
  3. Prometheus metrics middleware + /metrics route
"""
from __future__ import annotations

import logging

logger = logging.getLogger("fair_lending.p4_startup")


def init_priority4(app) -> None:
    """
    Call this from the FastAPI lifespan or at module level after app creation.

    Usage in main.py:
        from backend.core.p4_startup import init_priority4
        init_priority4(app)
    """
    # 1. Structured logging
    from backend.core.logging_config import configure_logging
    configure_logging()

    # 2. Sentry
    from backend.core.sentry_integration import init_sentry
    init_sentry()

    # 3. Prometheus middleware
    try:
        from backend.core.metrics import prometheus_middleware, router as metrics_router
        app.middleware("http")(prometheus_middleware)
        app.include_router(metrics_router)
        logger.info("Prometheus metrics enabled at /metrics")
    except Exception as e:
        logger.warning(f"Prometheus metrics not enabled: {e}")

    logger.info("Priority 4 observability stack initialized")
