"""
Dataset processing tasks — runs in Celery workers.

Replaces the in-request BackgroundTasks with proper async queue jobs.
Progress is broadcast via WebSocket to the frontend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def _broadcast_progress(file_id: str, event: str, data: Dict[str, Any]) -> None:
    """Push a progress update to all WebSocket subscribers for this file_id."""
    try:
        from backend.api.routes.ws import manager
        payload = {"event": event, "file_id": file_id, **data}
        # Run in a new event loop since Celery workers are synchronous
        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.broadcast(file_id, payload))
        loop.close()
    except Exception as e:
        logger.warning(f"WS broadcast failed: {e}")


@shared_task(
    name="backend.workers.tasks.dataset_tasks.process_dataset",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_dataset(self, file_id: str, file_path: str, filename: str) -> Dict[str, Any]:
    """
    Full dataset processing pipeline:
      1. Schema discovery
      2. Data cleaning
      3. Narrative generation
      4. Embedding
      5. Vector store indexing
      6. Database record update
    """
    try:
        _broadcast_progress(file_id, "processing.started", {"status": "processing", "step": "Schema Discovery", "progress": 5})

        # Import here to avoid circular imports at module load
        import pandas as pd
        from backend.core.schema_discovery import SchemaDiscovery
        from backend.core.data_processor import DataProcessor
        from backend.core.narrative_generator import NarrativeGenerator
        from backend.core.embedder import Embedder
        from backend.core.vector_store import VectorStore
        from backend.config import Config

        # ── Step 1: Load data ─────────────────────────────────────────────
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            df = pd.read_csv(file_path)
        elif ext == "xlsx":
            df = pd.read_excel(file_path, engine="openpyxl")
        elif ext == "json":
            df = pd.read_json(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

        _broadcast_progress(file_id, "processing.progress", {"status": "processing", "step": "Schema Discovery", "progress": 15})

        # ── Step 2: Schema discovery ──────────────────────────────────────
        sd = SchemaDiscovery()
        schema_result = sd.discover(df)
        field_mappings = schema_result.get("field_mappings", {})
        dataset_type  = schema_result.get("dataset_type", "unknown")

        _broadcast_progress(file_id, "processing.progress", {"status": "processing", "step": "Data Cleaning", "progress": 30})

        # ── Step 3: Data cleaning ─────────────────────────────────────────
        dp = DataProcessor()
        result = dp.process(df, field_mappings)
        df_clean = result.get("dataframe", df)
        quality_score    = result.get("quality_score", 0.0)
        duplicates_removed = result.get("duplicates_removed", 0)

        _broadcast_progress(file_id, "processing.progress", {"status": "processing", "step": "Generating Narratives", "progress": 50})

        # ── Step 4: Narrative generation ──────────────────────────────────
        ng = NarrativeGenerator()
        narratives = ng.generate_batch(df_clean, field_mappings, max_records=2000)

        _broadcast_progress(file_id, "processing.progress", {"status": "processing", "step": "Generating Embeddings", "progress": 70})

        # ── Step 5: Embedding + Vector store ─────────────────────────────
        try:
            embedder = Embedder()
            vs = VectorStore()
            for i, (narrative, meta) in enumerate(narratives):
                embedding = embedder.embed(narrative)
                doc_id = f"{file_id}_row_{i}"
                vs.add(doc_id, narrative, {**meta, "file_id": file_id, "dataset_type": dataset_type}, embedding)
        except Exception as e:
            logger.warning(f"Vector store indexing failed (non-fatal): {e}")

        _broadcast_progress(file_id, "processing.progress", {"status": "processing", "step": "Saving to Database", "progress": 90})

        # ── Step 6: Update database record ────────────────────────────────
        _update_dataset_db(
            file_id=file_id,
            status="completed",
            total_rows=len(df_clean),
            total_columns=len(df_clean.columns),
            mapped_columns=len(field_mappings),
            quality_score=quality_score,
            duplicates_removed=duplicates_removed,
            field_mappings=field_mappings,
            schema_discovery=schema_result,
            dataset_type=dataset_type,
        )

        _broadcast_progress(file_id, "processing.completed", {
            "status": "completed",
            "step": "Complete",
            "progress": 100,
            "total_rows": len(df_clean),
            "quality_score": quality_score,
        })

        logger.info(f"Dataset {file_id} processed: {len(df_clean)} rows, quality={quality_score:.2f}")
        return {"status": "completed", "file_id": file_id, "rows": len(df_clean)}

    except Exception as exc:
        logger.exception(f"Dataset processing failed for {file_id}: {exc}")
        _broadcast_progress(file_id, "processing.failed", {"status": "failed", "error": str(exc)})
        _update_dataset_db(file_id=file_id, status="failed", error_message=str(exc))
        raise self.retry(exc=exc)


def _update_dataset_db(file_id: str, **kwargs) -> None:
    """Synchronously update the Dataset row in the database."""
    try:
        import asyncio
        from backend.database.connection import AsyncSessionLocal
        from backend.database.models import Dataset
        from sqlalchemy import select, update

        async def _do():
            async with AsyncSessionLocal() as db:
                stmt = (
                    update(Dataset)
                    .where(Dataset.file_id == file_id)
                    .values(**{k: v for k, v in kwargs.items() if v is not None})
                )
                await db.execute(stmt)
                await db.commit()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_do())
        loop.close()
    except Exception as e:
        logger.warning(f"DB update failed for {file_id}: {e}")


@shared_task(name="backend.workers.tasks.dataset_tasks.cleanup_temp_files")
def cleanup_temp_files() -> Dict[str, Any]:
    """Weekly cleanup of orphaned temp files older than 7 days."""
    import time
    from backend.config import Config
    upload_dir = Path(Config.UPLOAD_DIR)
    cutoff = time.time() - 7 * 86_400
    removed = 0
    for f in upload_dir.iterdir():
        if f.stat().st_mtime < cutoff and f.suffix in {".tmp", ".part"}:
            f.unlink()
            removed += 1
    logger.info(f"Cleanup: removed {removed} temp files")
    return {"removed": removed}
