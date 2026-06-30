"""Scheduled fairness audits and drift detection tasks."""
from __future__ import annotations

import logging
from typing import Any, Dict
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(name="backend.workers.tasks.audit_tasks.scheduled_fairness_audit")
def scheduled_fairness_audit() -> Dict[str, Any]:
    """
    Runs nightly fairness audit on all processed datasets.
    Sends alert if fairness score drops below threshold.
    """
    try:
        import asyncio
        from sqlalchemy import select
        from backend.database.connection import AsyncSessionLocal
        from backend.database.models import Dataset, FairnessAudit as FairnessAuditModel
        from backend.core.fairness_engine import FairnessEngine
        from backend.config import Config

        results = []

        async def _run():
            async with AsyncSessionLocal() as db:
                rows = await db.execute(
                    select(Dataset).where(Dataset.status == "completed")
                )
                datasets = rows.scalars().all()

            import pandas as pd
            from pathlib import Path

            fe = FairnessEngine()
            for ds in datasets:
                try:
                    # Find file on disk
                    upload_dir = Path(Config.UPLOAD_DIR)
                    files = list(upload_dir.glob(f"{ds.file_id}*"))
                    if not files:
                        continue

                    ext = files[0].suffix.lower()
                    df = pd.read_csv(files[0]) if ext == ".csv" else pd.read_excel(files[0])
                    audit = fe.run_audit(df, ds.field_mappings or {})
                    score = audit.get("fairness_score", 1.0)

                    # Persist audit result
                    async with AsyncSessionLocal() as db:
                        record = FairnessAuditModel(
                            dataset_id=ds.id,
                            fairness_score=score,
                            disparate_impact_ratios=audit.get("disparate_impact_ratios"),
                            bias_indicators=audit.get("bias_indicators"),
                            findings=audit.get("findings"),
                            recommendations=audit.get("recommendations"),
                            status="completed",
                        )
                        db.add(record)
                        await db.commit()

                    # Alert if below threshold
                    if score < 0.70:
                        _send_fairness_alert(ds.original_filename, score)

                    results.append({"dataset": ds.original_filename, "score": score})
                    logger.info(f"Scheduled audit: {ds.original_filename} → score={score:.2f}")

                except Exception as e:
                    logger.warning(f"Scheduled audit failed for {ds.file_id}: {e}")

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()

        return {"audits_run": len(results), "results": results}

    except Exception as exc:
        logger.exception(f"Scheduled audit task failed: {exc}")
        return {"error": str(exc)}


@shared_task(name="backend.workers.tasks.audit_tasks.check_model_drift")
def check_model_drift() -> Dict[str, Any]:
    """
    Every 6 hours: compare recent prediction distributions against baseline.
    Fires monitoring alert if drift exceeds threshold.
    """
    try:
        from backend.core.monitoring import get_monitoring_engine
        monitor = get_monitoring_engine()
        alerts = monitor.check_alerts()
        fired = len([a for a in alerts if "drift" in a.alert_type.lower()])
        logger.info(f"Drift check: {fired} drift alerts")
        return {"drift_alerts": fired}
    except Exception as exc:
        logger.exception(f"Drift check failed: {exc}")
        return {"error": str(exc)}


def _send_fairness_alert(dataset_name: str, score: float) -> None:
    """Send alert email / Slack / webhook when fairness drops below threshold."""
    # In production: integrate with SendGrid, PagerDuty, or Slack webhook
    logger.warning(
        f"⚠️  FAIRNESS ALERT: dataset '{dataset_name}' scored {score:.2%} "
        f"(below 70% threshold). Immediate review recommended."
    )
