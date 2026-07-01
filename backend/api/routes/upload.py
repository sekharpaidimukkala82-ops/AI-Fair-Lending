"""
Upload routes – ingest datasets and policy documents into the platform.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user_optional
from backend.config import Config
from backend.core.chunker import TextChunker
from backend.core.data_processor import DataProcessor
from backend.core.embedder import Embedder
from backend.core.narrative_generator import NarrativeGenerator
from backend.core.schema_discovery import SchemaDiscovery
from backend.core.vector_store import VectorStore
from backend.database.connection import get_db
from backend.database.crud import create_dataset, update_dataset_status, list_datasets, log_action
from backend.database.models import User
from backend.models.schemas import StatusResponse, UploadResponse

logger = logging.getLogger("fair_lending.upload")
router = APIRouter(prefix="/upload", tags=["Upload"])

# In-memory status store (still needed for fast polling; DB is the source of truth)
_upload_status: dict[str, dict] = {}

_schema_discovery = None
_data_processor = None
_chunker = None
_embedder = None
_vector_store = None
_narrative_gen = None


def _get_singletons():
    global _schema_discovery, _data_processor, _chunker, _embedder, _vector_store, _narrative_gen
    if _schema_discovery is None:
        _schema_discovery = SchemaDiscovery()
        _data_processor = DataProcessor()
        _chunker = TextChunker()
        _narrative_gen = NarrativeGenerator()
        try:
            _embedder = Embedder()
        except Exception as e:
            logger.warning(f"Embedder init failed, using fallback: {e}")
            _embedder = None
        try:
            _vector_store = VectorStore()
        except Exception as e:
            logger.warning(f"VectorStore init: {e}")
            _vector_store = None
    return _schema_discovery, _data_processor, _chunker, _embedder, _vector_store, _narrative_gen


def _read_dataframe(file_path: str, filename: str) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":   return pd.read_csv(file_path)
    if ext == "xlsx":  return pd.read_excel(file_path, engine="openpyxl")
    if ext == "json":  return pd.read_json(file_path)
    raise ValueError(f"Unsupported format: {ext}")


async def _persist_completed(file_id: str, data: dict) -> None:
    """Write completed processing results to the database."""
    try:
        from backend.database.connection import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await update_dataset_status(
                db, file_id, "completed",
                total_rows=data.get("rows"),
                mapped_columns=data.get("schema_discovery", {}).get("mapped_columns"),
                total_columns=data.get("schema_discovery", {}).get("total_columns"),
                quality_score=data.get("processing_report", {}).get("quality_score"),
                duplicates_removed=data.get("processing_report", {}).get("duplicates_removed"),
                field_mappings=data.get("schema_discovery", {}).get("field_mappings"),
                schema_discovery=data.get("schema_discovery"),
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"DB persist failed for {file_id}: {e}")


async def _process_dataset_bg(file_id: str, file_path: str, filename: str) -> None:
    """Background task: process dataset, index narratives, persist to DB."""
    try:
        sd, dp, chunker, embedder, vs, ng = _get_singletons()
        logger.info(f"[{file_id}] Processing: {filename}")
        _upload_status[file_id]["status"] = "processing"

        df = _read_dataframe(file_path, filename)        discovery = sd.generate_discovery_report(df)
        df_clean, proc_report = dp.process(df, discovery.field_mappings)
        narratives = ng.generate_batch(df_clean, discovery.field_mappings)

        if narratives and vs is not None and embedder is not None:
            from backend.models.schemas import DocumentChunk
            chunks, texts = [], []
            # Limit to 500 rows on free tier to avoid OOM kills
            max_rows = 500
            narratives_to_index = narratives[:max_rows]
            for narr in narratives_to_index:
                cid = str(uuid.uuid4())
                chunks.append(DocumentChunk(
                    chunk_id=cid, text=narr.text,
                    metadata={**{k: str(v) for k, v in narr.metadata.items()}, "dataset_id": file_id, "type": "narrative"},
                    source=filename,
                ))
                texts.append(narr.text)
            try:
                # Process in batches of 50 to avoid memory spikes
                batch_size = 50
                for i in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[i:i+batch_size]
                    batch_texts = texts[i:i+batch_size]
                    vs.add_documents(batch_chunks, embedder.embed_batch(batch_texts))
            except Exception as e:
                logger.warning(f"[{file_id}] Vector indexing failed (non-fatal): {e}")

        completed_data = {
            "status": "completed",
            "schema_discovery": discovery.model_dump(),
            "processing_report": proc_report.model_dump(),
            "rows": len(df_clean),
            "columns": list(df_clean.columns),
        }
        _upload_status[file_id].update(completed_data)
        await _persist_completed(file_id, completed_data)

        # Bridge: register the cleaned dataset in the fairness module
        try:
            from backend.api.routes import fairness as fairness_route
            fairness_route._datasets[file_id] = df_clean
            fairness_route._dataset_field_maps[file_id] = discovery.field_mappings or {}
            logger.info(f"[{file_id}] Registered in fairness module ✓")
        except Exception as e:
            logger.warning(f"[{file_id}] Fairness registration failed (non-fatal): {e}")

        logger.info(f"[{file_id}] Complete ✓")

    except Exception as exc:
        logger.exception(f"[{file_id}] Processing failed: {exc}")
        _upload_status[file_id].update({"status": "failed", "error": str(exc)})
        try:
            from backend.database.connection import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                await update_dataset_status(db, file_id, "failed", error_message=str(exc))
                await db.commit()
        except Exception:
            pass


async def _process_document_bg(file_id: str, file_path: str, filename: str) -> None:
    """Background task: chunk and index a policy document."""
    try:
        _, _, chunker, embedder, vs, _ = _get_singletons()
        _upload_status[file_id]["status"] = "processing"
        ext = filename.rsplit(".", 1)[-1].lower()
        text = ""
        if ext in ("txt", "md"):
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = await f.read()
        elif ext == "pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                text = f"[PDF: {filename}]"
        elif ext == "docx":
            try:
                import docx
                doc = docx.Document(file_path)
                text = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                text = f"[DOCX: {filename}]"
        else:
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = await f.read()

        if not text.strip():
            text = f"Document: {filename}"
        chunks = chunker.chunk_batch(
            [{"text": text, "metadata": {"source": filename, "file_id": file_id, "type": "document"}}],
            chunk_size=Config.DEFAULT_CHUNK_SIZE,
        )
        if chunks and vs is not None:
            vs.add_documents(chunks, embedder.embed_batch([c.text for c in chunks]))
        _upload_status[file_id].update({"status": "completed"})
    except Exception as exc:
        _upload_status[file_id].update({"status": "failed", "error": str(exc)})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/dataset", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Upload a tabular lending dataset. Auth optional — records owner if logged in."""
    if not Config.is_allowed_file(file.filename or ""):
        raise HTTPException(status_code=400, detail=f"File type not allowed. Supported: {Config.ALLOWED_EXTENSIONS}")

    content = await file.read()
    if len(content) > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds {Config.MAX_FILE_SIZE // (1024*1024)} MB limit")

    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}_{file.filename}"

    # Use storage abstraction (Supabase in prod, local disk in dev)
    from backend.core.storage import upload_file as storage_upload
    storage_ref = storage_upload(content, file.filename or "upload", file_id)
    save_path = storage_ref  # may be supabase:// or local path

    # Persist to DB
    owner_id = current_user.id if current_user else None
    await create_dataset(db, file_id=file_id, filename=file.filename or "",
                         original_filename=file.filename or "",
                         file_size=len(content), owner_id=owner_id,
                         storage_ref=storage_ref)
    if current_user:
        await log_action(db, "dataset.upload", user_id=current_user.id,
                         resource_type="dataset", resource_id=file_id,
                         details={"filename": file.filename, "size": len(content)})

    _upload_status[file_id] = {
        "status": "queued", "filename": file.filename,
        "file_id": file_id, "file_size": len(content),
    }
    background_tasks.add_task(_process_dataset_bg, file_id, save_path, file.filename or "")

    return UploadResponse(file_id=file_id, filename=file.filename or "",
                          file_size=len(content), status="queued",
                          message="Dataset received and queued for processing.")


@router.post("/document", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Upload a policy or compliance document."""
    if not Config.is_allowed_file(file.filename or ""):
        raise HTTPException(status_code=400, detail="File type not allowed.")
    content = await file.read()
    if len(content) > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large.")

    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}_{file.filename}"
    save_path = str(Config.get_upload_path(safe_name))
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    _upload_status[file_id] = {
        "status": "queued", "filename": file.filename,
        "file_id": file_id, "file_size": len(content),
    }
    background_tasks.add_task(_process_document_bg, file_id, save_path, file.filename or "")

    return UploadResponse(file_id=file_id, filename=file.filename or "",
                          file_size=len(content), status="queued",
                          message="Document received and queued for indexing.")


@router.get("/status/{file_id}", response_model=StatusResponse)
async def get_upload_status(file_id: str, db: AsyncSession = Depends(get_db)):
    """Return the current processing status of an uploaded file."""
    # Check in-memory first (fastest), fall back to DB
    info = _upload_status.get(file_id)
    if not info:
        from backend.database.crud import get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, file_id)
        if ds:
            info = {
                "file_id": ds.file_id, "filename": ds.filename,
                "status": ds.status, "file_size": ds.file_size,
                "rows": ds.total_rows, "schema_discovery": ds.schema_discovery,
                "processing_report": {"quality_score": ds.quality_score,
                                       "duplicates_removed": ds.duplicates_removed or 0},
            }
        else:
            raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")
    return StatusResponse(
        status=info.get("status", "unknown"),
        message=f"File {info.get('filename', file_id)} is {info.get('status', 'unknown')}.",
        details=info,
    )


@router.get("/list")
async def list_uploads(db: AsyncSession = Depends(get_db)):
    """Return all uploaded datasets — from DB + disk fallback for legacy files."""
    uploads = {}

    # 1. From database (authoritative source)
    try:
        db_datasets = await list_datasets(db)
        for ds in db_datasets:
            uploads[ds.file_id] = {
                "file_id": ds.file_id,
                "filename": ds.filename,
                "status": ds.status,
                "file_size": ds.file_size,
                "total_rows": ds.total_rows,
                "total_columns": ds.total_columns,
                "mapped_columns": ds.mapped_columns,
                "quality_score": ds.quality_score,
                "dataset_type": ds.dataset_type,
                "uploaded_at": ds.uploaded_at.isoformat() if ds.uploaded_at else None,
            }
    except Exception as e:
        logger.warning(f"DB list failed: {e}")

    # 2. In-memory entries not yet in DB
    for fid, info in _upload_status.items():
        if fid not in uploads:
            uploads[fid] = {
                "file_id": fid,
                "filename": info.get("filename"),
                "status": info.get("status"),
                "file_size": info.get("file_size"),
                "uploaded_at": datetime.utcnow().isoformat(),
            }

    # 3. Disk scan for legacy files
    try:
        upload_dir = Path(Config.UPLOAD_DIR)
        if upload_dir.exists():
            for f in sorted(upload_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.suffix.lower() in {".csv", ".xlsx", ".json"}:
                    parts = f.name.split("_", 1)
                    if len(parts) == 2:
                        fid, orig = parts
                        if fid not in uploads:
                            mtime = f.stat().st_mtime
                            uploads[fid] = {
                                "file_id": fid,
                                "filename": orig,
                                "status": "completed",
                                "file_size": f.stat().st_size,
                                "uploaded_at": datetime.fromtimestamp(mtime).isoformat(),
                            }
    except Exception:
        pass

    return {"uploads": list(uploads.values()), "total": len(uploads)}


@router.delete("/all", response_model=StatusResponse)
async def delete_all_datasets(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Delete all dataset records (admin cleanup) — cascades dependents."""
    from sqlalchemy import delete as sql_delete
    from backend.database.models import (Dataset, FairnessAudit, MLModel, Report,
                                          AuditLog, Case, CaseComment, DataLineage, ScheduledAudit)
    try:
        # Delete in dependency order
        for model in [CaseComment, Case, DataLineage, ScheduledAudit,
                      FairnessAudit, MLModel, Report, AuditLog, Dataset]:
            try:
                await db.execute(sql_delete(model))
            except Exception:
                pass
        await db.commit()
        _upload_status.clear()
        try:
            vs = VectorStore()
            vs.delete_collection()
        except Exception:
            pass
        return StatusResponse(status="cleared", message="All datasets deleted successfully.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear datasets: {e}")
