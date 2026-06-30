"""ML training and prediction Celery tasks."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    name="backend.workers.tasks.ml_tasks.train_model",
    bind=True,
    max_retries=1,
    time_limit=1800,      # 30 min hard limit
    soft_time_limit=1500, # 25 min soft limit
)
def train_model(
    self,
    dataset_id: str,
    file_path: str,
    target_column: Optional[str] = None,
    notify_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Train approval prediction model in background."""
    try:
        import pandas as pd
        from backend.core.ml_engine import MLEngine
        from backend.workers.tasks.dataset_tasks import _broadcast_progress

        _broadcast_progress(dataset_id, "ml.training.started", {"status": "training", "progress": 5})

        ext = file_path.rsplit(".", 1)[-1].lower()
        df = pd.read_csv(file_path) if ext == "csv" else pd.read_excel(file_path)

        _broadcast_progress(dataset_id, "ml.training.progress", {"status": "training", "progress": 30, "step": "Feature Engineering"})

        engine = MLEngine()
        result = engine.train(df, target_column=target_column)

        _broadcast_progress(dataset_id, "ml.training.completed", {
            "status": "completed",
            "progress": 100,
            "model_id": result.get("model_id"),
            "accuracy": result.get("accuracy"),
        })

        # Notify by email if requested
        if notify_email:
            _send_completion_email(
                notify_email,
                subject="FairLend AI — Model Training Complete",
                body=f"Model {result.get('model_id')} trained with accuracy {result.get('accuracy', 0):.2%}",
            )

        logger.info(f"Model trained for dataset {dataset_id}: accuracy={result.get('accuracy'):.3f}")
        return result

    except Exception as exc:
        logger.exception(f"ML training failed for {dataset_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name="backend.workers.tasks.ml_tasks.batch_predict",
    bind=True,
    time_limit=600,
)
def batch_predict(self, dataset_id: str, file_path: str) -> Dict[str, Any]:
    """Run batch predictions for an entire dataset."""
    try:
        import pandas as pd
        from backend.core.ml_engine import MLEngine

        ext = file_path.rsplit(".", 1)[-1].lower()
        df = pd.read_csv(file_path) if ext == "csv" else pd.read_excel(file_path)

        engine = MLEngine()
        predictions = engine.batch_predict(df)

        return {"dataset_id": dataset_id, "count": len(predictions), "predictions": predictions}

    except Exception as exc:
        logger.exception(f"Batch prediction failed for {dataset_id}: {exc}")
        raise self.retry(exc=exc)


def _send_completion_email(to: str, subject: str, body: str) -> None:
    """Stub email sender — replace with SMTP/SendGrid in production."""
    logger.info(f"[EMAIL] To: {to} | Subject: {subject} | Body: {body[:100]}")
