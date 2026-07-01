"""
Upload routes – v2 supplementary endpoints.

Provides:
  - GET    /upload/status/{file_id}  — DB-backed status check
  - GET    /upload/datasets           — full dataset list from DB
  - DELETE /upload/dataset/{file_id} — delete a single dataset

NOTE: POST /upload/dataset is handled by upload.py (the primary route).
      All upload processing (background task, processed CSV save, fairness
      registration) is done in upload.py's _process_dataset_bg.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete

from backend.config import Config
from backend.database.connection import get_db
from backend.database.models import Dataset
from backend.models.schemas import StatusResponse

logger = logging.getLogger("fair_lending.upload_v2")
router = APIRouter(prefix="/upload", tags=["Upload"])


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/status/{file_id}")
async def get_upload_status_v2(file_id: str, db: AsyncSession = Depends(get_db)):
    """Get processing status from database (DB-backed, survives restarts)."""
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
async def list_datasets_v2(db: AsyncSession = Depends(get_db)):
    """List all datasets from the database (DB-backed, survives restarts)."""
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
    """Delete a single dataset record and its associated files."""
    row = await db.execute(select(Dataset).where(Dataset.file_id == file_id))
    dataset = row.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Delete original + processed files from disk
    for fname in [dataset.filename, f"{file_id}_processed.csv"]:
        try:
            fp = Config.get_upload_path(fname)
            if fp.exists():
                fp.unlink()
        except Exception as e:
            logger.warning(f"Could not delete file {fname}: {e}")

    # Also clean up storage_ref if it's a local path
    if dataset.storage_ref and not dataset.storage_ref.startswith("supabase://"):
        try:
            from pathlib import Path
            p = Path(dataset.storage_ref)
            if p.exists():
                p.unlink()
        except Exception:
            pass

    await db.execute(sql_delete(Dataset).where(Dataset.file_id == file_id))
    await db.commit()

    # Remove from in-memory fairness cache
    try:
        from backend.api.routes import fairness as fairness_route
        fairness_route._datasets.pop(file_id, None)
        fairness_route._dataset_field_maps.pop(file_id, None)
    except Exception:
        pass

    return StatusResponse(status="deleted", message=f"Dataset {file_id} removed successfully.")
