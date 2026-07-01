"""
Fairness routes – stateless disparate impact analysis and fair lending audits.

ARCHITECTURE: Every request reads the dataset fresh from disk.
No in-memory caching — this ensures each dataset_id always gets its own data,
regardless of server restarts, multiple uploads, or switching between datasets.
"""

from __future__ import annotations

import logging
import uuid
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user_optional
from backend.config import Config
from backend.core.fairness_engine import FairnessEngine
from backend.core.monitoring import get_monitoring_engine
from backend.database.connection import get_db
from backend.database.models import User
from backend.models.schemas import FairnessReport, StatusResponse
from typing import Optional as _Optional

logger = logging.getLogger("fair_lending.fairness")
router = APIRouter(prefix="/fairness", tags=["Fairness"])

_monitor = get_monitoring_engine()

# Singleton engine — stateless, thread-safe
_engine: Optional[FairnessEngine] = None

def _get_engine() -> FairnessEngine:
    global _engine
    if _engine is None:
        _engine = FairnessEngine()
    return _engine


# ---------------------------------------------------------------------------
# Core: load dataset from disk by dataset_id — always fresh, never cached
# ---------------------------------------------------------------------------

def _load_dataset(dataset_id: str) -> pd.DataFrame:
    """
    Load a dataset from disk by its file_id.
    Always reads fresh from disk — no in-memory state.
    
    Lookup order:
    1. <upload_dir>/<dataset_id>_processed.csv  (saved after processing)
    2. Any file in upload_dir starting with dataset_id (original upload)
    3. storage_ref from DB
    """
    upload_dir = Path(Config.UPLOAD_DIR)

    # 1. Processed CSV (fastest — already cleaned)
    processed = upload_dir / f"{dataset_id}_processed.csv"
    if processed.exists():
        try:
            df = pd.read_csv(processed)
            logger.info(f"Loaded processed CSV for {dataset_id}: {len(df)} rows")
            return df
        except Exception as e:
            logger.warning(f"Failed to read processed CSV {processed}: {e}")

    # 2. Scan for original file
    if upload_dir.exists():
        for f in sorted(upload_dir.iterdir()):
            if f.name.startswith(dataset_id) and f.suffix.lower() in (".csv", ".xlsx", ".json"):
                try:
                    ext = f.suffix.lower()
                    if ext == ".csv":
                        df = pd.read_csv(f)
                    elif ext == ".xlsx":
                        df = pd.read_excel(f, engine="openpyxl")
                    elif ext == ".json":
                        df = pd.read_json(f)
                    else:
                        continue
                    logger.info(f"Loaded original file for {dataset_id}: {f.name} ({len(df)} rows)")
                    return df
                except Exception as e:
                    logger.warning(f"Failed to read {f}: {e}")

    # 3. DB storage_ref fallback
    try:
        import concurrent.futures
        import asyncio as _asyncio
        from backend.database.connection import AsyncSessionLocal
        from backend.database.crud import get_dataset_by_file_id
        from backend.core.storage import download_file

        def _get_ref():
            async def _q():
                async with AsyncSessionLocal() as db:
                    ds = await get_dataset_by_file_id(db, dataset_id)
                    return (ds.storage_ref, ds.filename) if ds else (None, None)
            loop = _asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_q())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            storage_ref, filename = ex.submit(_get_ref).result(timeout=5)

        if storage_ref:
            local_path = download_file(storage_ref, filename or "")
            if local_path:
                ext = Path(local_path).suffix.lower()
                if ext == ".csv":
                    df = pd.read_csv(local_path)
                elif ext == ".xlsx":
                    df = pd.read_excel(local_path, engine="openpyxl")
                elif ext == ".json":
                    df = pd.read_json(local_path)
                else:
                    df = pd.read_csv(local_path)
                logger.info(f"Loaded from storage_ref for {dataset_id}: {len(df)} rows")
                return df
    except Exception as e:
        logger.warning(f"DB/storage fallback failed for {dataset_id}: {e}")

    raise HTTPException(
        status_code=404,
        detail=(
            f"Dataset '{dataset_id}' not found on disk. "
            "Please re-upload the file — it may have been cleared."
        ),
    )


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class AuditRequest(BaseModel):
    dataset_id: str
    field_map: Optional[Dict[str, str]] = None
    protected_columns: Optional[Dict[str, str]] = Field(
        default=None,
        description="Override: {field_name: column_name} e.g. {'race': 'applicant_race_1'}"
    )
    outcome_column: Optional[str] = Field(
        default=None,
        description="Override: name of the outcome/decision column"
    )
    approval_values: Optional[List[str]] = Field(
        default=None,
        description="Override: values that count as approved"
    )


class SimilarOutcomesRequest(BaseModel):
    dataset_id: str
    applicant_id: str
    top_k: int = Field(default=10, ge=1, le=50)


class DatasetRegisterRequest(BaseModel):
    dataset_id: Optional[str] = None
    csv_data: str
    field_map: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/audit", response_model=FairnessReport)
async def run_fairness_audit(
    request: AuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: _Optional[User] = Depends(get_current_user_optional),
):
    """Run a complete fairness audit on a dataset. Always reads fresh from disk."""
    df = _load_dataset(request.dataset_id)
    logger.info(f"Audit: dataset={request.dataset_id} rows={len(df)} cols={list(df.columns)}")

    report = _get_engine().generate_audit(
        df,
        field_map=request.field_map,
        dataset_id=request.dataset_id,
        protected_columns=request.protected_columns,
        outcome_column=request.outcome_column,
        approval_values=request.approval_values,
    )
    _monitor.record_fairness_score(report.score, request.dataset_id)

    # Persist audit result to DB
    try:
        from backend.database.crud import create_fairness_audit, get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, request.dataset_id)
        if ds:
            await create_fairness_audit(db, ds.id, {
                "analyst_id": current_user.id if current_user else None,
                "fairness_score": report.score,
                "disparate_impact_ratios": report.disparate_impact_ratios,
                "approval_rates_by_group": report.approval_rates_by_group,
                "bias_indicators": [b.model_dump() for b in report.bias_indicators],
                "findings": report.findings,
                "recommendations": report.recommendations,
                "outcome_column": request.outcome_column,
                "protected_columns": request.protected_columns,
            })
    except Exception as e:
        logger.warning(f"DB audit persist failed: {e}")

    return report


@router.get("/detect-columns/{dataset_id}")
async def detect_columns(dataset_id: str):
    """Auto-detect outcome and protected class columns. Always reads fresh from disk."""
    df = _load_dataset(dataset_id)
    engine = _get_engine()

    from backend.core.dataset_profiler import DatasetProfiler
    dataset_type = DatasetProfiler().detect_type(df)
    outcome_col = engine._detect_outcome_col(df)
    protected_cols = engine._detect_all_protected_cols(df)

    return {
        "dataset_id": dataset_id,
        "dataset_type": dataset_type,
        "detected_outcome_column": outcome_col,
        "detected_protected_columns": protected_cols,
        "all_columns": list(df.columns),
        "total_rows": len(df),
    }


@router.get("/disparate-impact/{dataset_id}")
async def get_disparate_impact(
    dataset_id: str,
    protected_col: Optional[str] = Query(None),
    outcome_col: Optional[str] = Query(None),
):
    """Compute disparate impact. Reads fresh from disk."""
    df = _load_dataset(dataset_id)
    engine = _get_engine()

    if protected_col and outcome_col:
        ratio = engine.analyze_disparate_impact(df, protected_col, outcome_col)
        return {
            "dataset_id": dataset_id,
            "protected_col": protected_col,
            "outcome_col": outcome_col,
            "disparate_impact_ratio": ratio,
            "threshold": 0.80,
            "pass": ratio >= 0.80,
        }

    results: Dict[str, Any] = {}
    detected_protected = engine._detect_all_protected_cols(df)
    detected_outcome = engine._detect_outcome_col(df)
    for field, col in detected_protected.items():
        if detected_outcome:
            ratio = engine.analyze_disparate_impact(df, col, detected_outcome)
            results[field] = {"column": col, "disparate_impact_ratio": ratio, "pass": ratio >= 0.80}

    return {"dataset_id": dataset_id, "results": results, "threshold": 0.80}


@router.get("/approval-rates/{dataset_id}")
async def get_approval_rates(
    dataset_id: str,
    group_col: Optional[str] = Query(None),
):
    """Return approval rates by group. Reads fresh from disk."""
    df = _load_dataset(dataset_id)
    engine = _get_engine()
    outcome_col = engine._detect_outcome_col(df)

    if outcome_col is None:
        raise HTTPException(status_code=422, detail="No outcome column detected.")

    if group_col:
        if group_col not in df.columns:
            raise HTTPException(status_code=422, detail=f"Column '{group_col}' not found.")
        rates = engine.compute_approval_rates_by_group(df, group_col, outcome_col)
        return {"dataset_id": dataset_id, "group_col": group_col, "approval_rates": rates}

    all_rates: Dict[str, Any] = {}
    for field, col in engine._detect_all_protected_cols(df).items():
        rates = engine.compute_approval_rates_by_group(df, col, outcome_col, field_name=field)
        all_rates[field] = {"column": col, "rates": rates}

    return {"dataset_id": dataset_id, "approval_rates_by_group": all_rates}


@router.get("/score/{dataset_id}")
async def get_fairness_score(dataset_id: str):
    """Return fairness score 0-100. Reads fresh from disk."""
    df = _load_dataset(dataset_id)
    score = _get_engine().compute_fairness_score(df)
    return {
        "dataset_id": dataset_id,
        "fairness_score": score,
        "interpretation": (
            "Acceptable" if score >= 80 else
            "Needs Attention" if score >= 60 else
            "High Risk"
        ),
    }


@router.post("/similar-outcomes")
async def compare_similar_outcomes(request: SimilarOutcomesRequest):
    """Find similar applicants. Reads fresh from disk."""
    df = _load_dataset(request.dataset_id)
    result = _get_engine().find_similar_applicant_outcomes(
        df, applicant_id=request.applicant_id, top_k=request.top_k
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/ai-explain")
async def ai_explain_audit(request: AuditRequest):
    """Run fairness audit + AI explanation. Reads fresh from disk."""
    df = _load_dataset(request.dataset_id)
    engine = _get_engine()

    report = engine.generate_audit(
        df,
        field_map=request.field_map,
        dataset_id=request.dataset_id,
        protected_columns=request.protected_columns,
        outcome_column=request.outcome_column,
        approval_values=request.approval_values,
    )
    ai_explanation = engine.generate_ai_explanation(report)
    _monitor.record_fairness_score(report.score, request.dataset_id)

    from backend.core.ai_provider import get_active_provider, get_active_model
    return {
        "report": report.model_dump(),
        "ai_explanation": ai_explanation,
        "provider": get_active_provider(),
        "model": get_active_model(),
    }


@router.post("/register-dataset", response_model=StatusResponse)
async def register_dataset(request: DatasetRegisterRequest):
    """Register inline CSV data (for testing/API clients). Saves to disk."""
    try:
        df = pd.read_csv(StringIO(request.csv_data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}")

    dataset_id = request.dataset_id or str(uuid.uuid4())

    # Save to disk so _load_dataset can find it
    save_path = Config.get_upload_path(f"{dataset_id}_processed.csv")
    Path(Config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    df.to_csv(save_path, index=False)

    return StatusResponse(
        status="registered",
        message=f"Dataset '{dataset_id}' saved ({len(df)} rows).",
        details={"dataset_id": dataset_id, "rows": len(df), "columns": list(df.columns)},
    )


# ---------------------------------------------------------------------------
# Keep backward-compat in-memory store for any legacy code that imports these
# ---------------------------------------------------------------------------
_datasets: Dict[str, pd.DataFrame] = {}
_dataset_field_maps: Dict[str, Dict[str, str]] = {}

def _register_dataset(df: pd.DataFrame, dataset_id: str, field_map: Optional[Dict[str, str]] = None) -> None:
    """Legacy: save dataset to disk instead of memory."""
    save_path = Config.get_upload_path(f"{dataset_id}_processed.csv")
    Path(Config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    df.to_csv(save_path, index=False)
    logger.info(f"Registered dataset {dataset_id} → {save_path}")
