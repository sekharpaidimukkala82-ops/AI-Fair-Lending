"""
Upload routes – v2 with Celery task dispatch and WebSocket progress.

Key changes from v1:
  - Dataset processing dispatched to Celery queue (not BackgroundTasks)
  - /upload/status/{file_id} now reads from DB (not in-memory dict)
  - Dataset list reads from DB for persistence across restarts
  - Document uploads still use BackgroundTasks (lighter workload)
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Config
from backend.database.connection import get_db
from backend.database.crud import log_action
from backend.database.models import Dataset
from backend.models.schemas import StatusResponse, UploadResponse
from backend.auth.dependencies import get_current_user_optional

logger = logging.getLogger("fair_lending.upload_v2")
router = APIRouter(prefix="/upload", tags=["Upload"])

# ── Celery availability detection ──────────────────────────────────────────
try:
    from backend.workers.tasks.dataset_tasks import process_dataset as _celery_process
    _CELERY_AVAILABLE = True
    logger.info("Celery worker available — using queue for dataset processing")
except ImportError:
    _CELERY_AVAILABLE = False
    logger.info("Celery not available — falling back to BackgroundTasks")


# ── Helpers ────────────────────────────────────────────────────────────────

def _read_dataframe(file_path: str, filename: str) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        return pd.read_csv(file_path)
    elif ext == "xlsx":
        return pd.read_excel(file_path, engine="openpyxl")
    elif ext == "json":
        return pd.read_json(file_path)
    raise ValueError(f"Unsupported tabular format: {ext}")


async def _create_dataset_record(db: AsyncSession, file_id: str, filename: str,
                                  original_filename: str, file_size: int, owner_id: Optional[str]) -> Dataset:
    dataset = Dataset(
        file_id=file_id,
        filename=filename,
        original_filename=original_filename,
        file_size=file_size,
        status="queued",
        owner_id=owner_id,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def _fallback_process_bg(file_id: str, file_path: str, filename: str) -> None:
    """Fallback when Celery is unavailable — full processing pipeline with DB updates."""
    from backend.database.connection import AsyncSessionLocal
    from backend.database.crud import update_dataset_status
    from backend.core.schema_discovery import SchemaDiscovery
    from backend.core.data_processor import DataProcessor
    from backend.core.narrative_generator import NarrativeGenerator
    from backend.core.embedder import Embedder
    from backend.core.vector_store import VectorStore
    import uuid as _uuid

    try:
        logger.info(f"[{file_id}] Starting processing: {filename}")

        # Update status to processing
        async with AsyncSessionLocal() as db:
            await update_dataset_status(db, file_id, "processing")
            await db.commit()

        # Read file — handle both local paths and supabase:// refs
        if file_path.startswith("supabase://"):
            from backend.core.storage import download_file as storage_download
            local_path = storage_download(file_path, filename)
            if not local_path:
                raise ValueError(f"Could not download file from storage: {file_path}")
            df = _read_dataframe(local_path, filename)
        else:
            df = _read_dataframe(file_path, filename)
        logger.info(f"[{file_id}] Read {len(df)} rows")
        # Schema discovery
        sd = SchemaDiscovery()
        discovery = sd.generate_discovery_report(df)

        # Data processing
        dp = DataProcessor()
        df_clean, proc_report = dp.process(df, discovery.field_mappings)

        # Generate narratives and index — skip for large files to avoid OOM
        try:
            if len(df_clean) <= 500:  # only embed small datasets on free tier
                ng = NarrativeGenerator()
                narratives = ng.generate_batch(df_clean, discovery.field_mappings)
                embedder = Embedder()
                vs = VectorStore()
                from backend.models.schemas import DocumentChunk
                # Process in small batches to avoid memory issues
                batch_size = 50
                all_chunks = []
                all_embeddings = []
                for i in range(0, len(narratives), batch_size):
                    batch = narratives[i:i+batch_size]
                    chunks = [DocumentChunk(
                        chunk_id=str(_uuid.uuid4()), text=n.text,
                        metadata={**{k: str(v) for k, v in n.metadata.items()}, "dataset_id": file_id, "type": "narrative"},
                        source=filename,
                    ) for n in batch]
                    embs = embedder.embed_batch([c.text for c in chunks])
                    all_chunks.extend(chunks)
                    all_embeddings.extend(embs)
                if all_chunks:
                    vs.add_documents(all_chunks, all_embeddings)
                logger.info(f"[{file_id}] Indexed {len(all_chunks)} vectors")
            else:
                logger.info(f"[{file_id}] Skipping vector indexing for large dataset ({len(df_clean)} rows) — search may be limited")
        except Exception as e:
            logger.warning(f"[{file_id}] Vector indexing failed (non-fatal): {e}")

        # Register in fairness module
        try:
            from backend.api.routes import fairness as fairness_route
            fairness_route._datasets[file_id] = df_clean
            fairness_route._dataset_field_maps[file_id] = discovery.field_mappings or {}
        except Exception as e:
            logger.warning(f"[{file_id}] Fairness registration failed: {e}")

        # Update DB to completed
        async with AsyncSessionLocal() as db:
            await update_dataset_status(
                db, file_id, "completed",
                total_rows=len(df_clean),
                total_columns=len(df_clean.columns),
                mapped_columns=discovery.mapped_columns,
                quality_score=proc_report.quality_score,
                duplicates_removed=proc_report.duplicates_removed,
                field_mappings=discovery.field_mappings,
                schema_discovery=discovery.model_dump(),
            )
            await db.commit()

        logger.info(f"[{file_id}] Complete ✓ ({len(df_clean)} rows)")

    except Exception as exc:
        logger.exception(f"[{file_id}] Processing failed: {exc}")
        try:
            async with AsyncSessionLocal() as db:
                await update_dataset_status(db, file_id, "failed", error_message=str(exc))
                await db.commit()
        except Exception:
            pass


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/dataset", response_model=UploadResponse, status_code=202)
async def upload_dataset_v2(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """
    Upload a tabular dataset (CSV / XLSX / JSON).

    Processing runs in Celery (if available) or FastAPI BackgroundTasks.
    Subscribe to /ws/{file_id} for real-time progress.
    """
    if not Config.is_allowed_file(file.filename or ""):
        raise HTTPException(status_code=400, detail=f"File type not supported: {file.filename}")

    # Check size
    content = await file.read()
    if len(content) > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 100 MB limit")

    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}_{file.filename}"

    # Use storage abstraction (Supabase in prod, local disk in dev)
    from backend.core.storage import upload_file as storage_upload
    storage_ref = storage_upload(content, file.filename or "upload", file_id)
    save_path = Path(storage_ref) if not storage_ref.startswith("supabase://") else Path(storage_ref)

    owner_id = current_user.id if current_user else None
    dataset = await _create_dataset_record(
        db, file_id, safe_name, file.filename or "upload", len(content), owner_id
    )

    await log_action(db, "dataset.upload", user_id=owner_id, resource_type="dataset", resource_id=file_id,
                     details={"filename": file.filename, "size": len(content)})

    # Dispatch processing
    if _CELERY_AVAILABLE:
        _celery_process.apply_async(
            args=[file_id, str(save_path), file.filename or ""],
            queue="processing",
        )
        logger.info(f"Dataset {file_id} queued for Celery processing")
    else:
        background_tasks.add_task(_fallback_process_bg, file_id, str(save_path), file.filename or "")
        logger.info(f"Dataset {file_id} queued for BackgroundTasks processing")

    return UploadResponse(
        file_id=file_id,
        filename=file.filename or "upload",
        file_size=len(content),
        status="queued",
        message=f"Dataset queued. Subscribe to /ws/{file_id} for real-time progress.",
    )


@router.get("/status/{file_id}")
async def get_upload_status(file_id: str, db: AsyncSession = Depends(get_db)):
    """Get processing status from database."""
    from sqlalchemy import select
    row = await db.execute(select(Dataset).where(Dataset.file_id == file_id))
    dataset = row.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset '{file_id}' not found")
    return {
        "file_id": file_id,
        "filename": dataset.filename,
        "original_filename": dataset.original_filename,
        "status": dataset.status,
        "total_rows": dataset.total_rows,
        "total_columns": dataset.total_columns,
        "mapped_columns": dataset.mapped_columns,
        "quality_score": dataset.quality_score,
        "dataset_type": dataset.dataset_type,
        "field_mappings": dataset.field_mappings,
        "error": dataset.error_message,
        "uploaded_at": dataset.uploaded_at.isoformat() if dataset.uploaded_at else None,
    }


@router.get("/datasets")
async def list_datasets(db: AsyncSession = Depends(get_db)):
    """List all datasets from the database."""
    from sqlalchemy import select
    rows = await db.execute(select(Dataset).order_by(Dataset.uploaded_at.desc()))
    datasets = rows.scalars().all()
    return [
        {
            "file_id": d.file_id,
            "filename": d.filename,
            "original_filename": d.original_filename,
            "file_size": d.file_size,
            "status": d.status,
            "dataset_type": d.dataset_type,
            "total_rows": d.total_rows,
            "total_columns": d.total_columns,
            "mapped_columns": d.mapped_columns,
            "quality_score": d.quality_score,
            "field_mappings": d.field_mappings,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in datasets
    ]


@router.delete("/dataset/{file_id}", response_model=StatusResponse)
async def delete_dataset(file_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a dataset record and its file."""
    from sqlalchemy import select, delete as sql_delete
    row = await db.execute(select(Dataset).where(Dataset.file_id == file_id))
    dataset = row.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Delete file
    try:
        file_path = Config.get_upload_path(dataset.filename)
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        logger.warning(f"Could not delete file for {file_id}: {e}")

    await db.execute(sql_delete(Dataset).where(Dataset.file_id == file_id))
    await db.commit()
    return StatusResponse(status="deleted", message=f"Dataset {file_id} removed")
