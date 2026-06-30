"""
Celery application — background task processing for Fair Lending Platform.

Queues:
  default    — general tasks
  processing — dataset upload & indexing (CPU-heavy)
  ml         — model training & batch prediction (CPU-heavy)
  reports    — PDF report generation
"""
from __future__ import annotations

import os
import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://:FairLend@Redis2024@localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://:FairLend@Redis2024@localhost:6379/1")

celery_app = Celery(
    "fair_lending",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "backend.workers.tasks.dataset_tasks",
        "backend.workers.tasks.ml_tasks",
        "backend.workers.tasks.report_tasks",
        "backend.workers.tasks.audit_tasks",
    ],
)

celery_app.conf.update(
    # ── Serialization ──────────────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # ── Result expiry ──────────────────────────────────────────────────────
    result_expires=86_400,          # 24 hours

    # ── Task routing ──────────────────────────────────────────────────────
    task_routes={
        "backend.workers.tasks.dataset_tasks.*": {"queue": "processing"},
        "backend.workers.tasks.ml_tasks.*":      {"queue": "ml"},
        "backend.workers.tasks.report_tasks.*":  {"queue": "reports"},
        "backend.workers.tasks.audit_tasks.*":   {"queue": "default"},
    },

    # ── Concurrency ────────────────────────────────────────────────────────
    worker_prefetch_multiplier=1,   # one task at a time per worker (for heavy jobs)
    task_acks_late=True,            # ack after completion, not pickup
    task_reject_on_worker_lost=True,

    # ── Retry policy (default) ────────────────────────────────────────────
    task_max_retries=3,
    task_default_retry_delay=60,

    # ── Scheduled tasks ───────────────────────────────────────────────────
    beat_schedule={
        # Run fairness audit on all datasets every day at 2 AM
        "daily-fairness-audit": {
            "task": "backend.workers.tasks.audit_tasks.scheduled_fairness_audit",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "default"},
        },
        # Drift check every 6 hours
        "drift-check": {
            "task": "backend.workers.tasks.audit_tasks.check_model_drift",
            "schedule": crontab(minute=0, hour="*/6"),
            "options": {"queue": "default"},
        },
        # Cleanup old temp files weekly
        "weekly-cleanup": {
            "task": "backend.workers.tasks.dataset_tasks.cleanup_temp_files",
            "schedule": crontab(day_of_week=0, hour=3, minute=0),
            "options": {"queue": "default"},
        },
    },
)
