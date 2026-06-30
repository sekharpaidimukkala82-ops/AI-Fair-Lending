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
    """Fallback when Celery is unavailable — delegates to upload.py's proven pipeline."""
    from backend.api.routes.upload import _process_dataset_bg
    await _process_dataset_bg(file_id, file_path, filename)


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/dataset", response_model=UploadResponse, status_code=202)
async def upload_dataset(
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
    save_path = Config.get_upload_path(safe_name)

    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

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
