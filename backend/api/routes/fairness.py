"""
Fairness routes – disparate impact analysis and fair lending audits.
"""

from __future__ import annotations

import uuid
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user_optional
from backend.core.fairness_engine import FairnessEngine
from backend.core.monitoring import get_monitoring_engine
from backend.database.connection import get_db
from backend.database.models import User
from backend.models.schemas import FairnessReport, StatusResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional as _Optional

router = APIRouter(prefix="/fairness", tags=["Fairness"])

def _get_fairness_engine():
    if not hasattr(_get_fairness_engine, "_instance"):
        try:
            _get_fairness_engine._instance = FairnessEngine()
        except Exception:
            _get_fairness_engine._instance = None
    return _get_fairness_engine._instance

_monitor = get_monitoring_engine()

# In-memory dataset store (populated by upload route processing)
_datasets: Dict[str, pd.DataFrame] = {}
_dataset_field_maps: Dict[str, Dict[str, str]] = {}


def _try_load_from_disk(dataset_id: str) -> Optional[pd.DataFrame]:
    """
    Try to reload a dataset from local disk after a server restart.

    Strategy (in order):
    1. Look for a processed CSV saved alongside the original file
       (written by _process_dataset_bg as <dataset_id>_processed.csv)
    2. Scan uploads dir for any file starting with dataset_id and reprocess it
    3. Try storage_ref from DB (local path or Supabase download)
    """
    import logging as _logging
    _log = _logging.getLogger("fair_lending.fairness")

    from backend.config import Config
    upload_dir = Path(Config.UPLOAD_DIR)

    def _read_and_process(file_path: Path) -> Optional[pd.DataFrame]:
        try:
            ext = file_path.suffix.lower()
            if ext == ".csv":
                df = pd.read_csv(file_path)
            elif ext == ".xlsx":
                df = pd.read_excel(file_path, engine="openpyxl")
            elif ext == ".json":
                df = pd.read_json(file_path)
            else:
                return None
            # Re-apply data processor to normalize
            from backend.core.data_processor import DataProcessor
            df_clean, _ = DataProcessor().process(df)
            _log.info(f"Reloaded dataset {dataset_id} from {file_path} ({len(df_clean)} rows)")
            return df_clean
        except Exception as e:
            _log.warning(f"Failed to read {file_path}: {e}")
            return None

    # 1. Check for pre-saved processed CSV
    processed_path = upload_dir / f"{dataset_id}_processed.csv"
    if processed_path.exists():
        try:
            df = pd.read_csv(processed_path)
            _log.info(f"Loaded processed CSV for {dataset_id}: {len(df)} rows")
            return df
        except Exception as e:
            _log.warning(f"Failed to read processed CSV: {e}")

    # 2. Scan uploads dir for original file
    if upload_dir.exists():
        for f in upload_dir.iterdir():
            if f.name.startswith(dataset_id) and not f.name.endswith("_processed.csv"):
                df = _read_and_process(f)
                if df is not None:
                    return df

    # 3. Try storage_ref from DB (runs in a new event loop to avoid conflicts)
    try:
        from backend.core.storage import download_file as storage_download
        import asyncio

        # Use run_in_executor pattern to avoid event loop conflicts
        import concurrent.futures

        def _get_storage_ref_sync():
            """Get storage_ref from DB synchronously."""
            import asyncio as _asyncio
            from backend.database.connection import AsyncSessionLocal
            from backend.database.crud import get_dataset_by_file_id

            async def _query():
                async with AsyncSessionLocal() as db:
                    ds = await get_dataset_by_file_id(db, dataset_id)
                    return ds.storage_ref if ds else None

            loop = _asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_query())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_get_storage_ref_sync)
            storage_ref = future.result(timeout=5)

        if storage_ref:
            local_path = storage_download(storage_ref)
            if local_path:
                return _read_and_process(Path(local_path))
    except Exception as e:
        _log.warning(f"Could not load dataset {dataset_id} from DB/storage: {e}")

    return None


def _get_dataset(dataset_id: str) -> pd.DataFrame:
    df = _datasets.get(dataset_id)
    if df is None:
        # Try to reload from disk (handles server restarts)
        df = _try_load_from_disk(dataset_id)
        if df is not None:
            _datasets[dataset_id] = df  # cache it
            return df
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset_id}' not found. Please re-upload your dataset — the server was restarted and lost in-memory data.",
        )
    return df


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class AuditRequest(BaseModel):
    dataset_id: str
    field_map: Optional[Dict[str, str]] = None
    # New: let user specify which columns to use
    protected_columns: Optional[Dict[str, str]] = Field(
        default=None,
        description="Map of {field_name: column_name} for protected classes. E.g. {'gender': 'applicant_sex', 'race': 'applicant_race_1'}"
    )
    outcome_column: Optional[str] = Field(
        default=None,
        description="Name of the outcome/decision column"
    )
    approval_values: Optional[List[str]] = Field(
        default=None,
        description="List of values that count as 'approved'. E.g. ['1', 'Originated', 'Approved']"
    )


class SimilarOutcomesRequest(BaseModel):
    dataset_id: str
    applicant_id: str
    top_k: int = Field(default=10, ge=1, le=50)


class DatasetRegisterRequest(BaseModel):
    """Allows inline CSV data to be registered for analysis (for demo/testing)."""
    dataset_id: Optional[str] = None
    csv_data: str = Field(..., description="CSV content as a string")
    field_map: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _register_dataset(df: pd.DataFrame, dataset_id: str, field_map: Optional[Dict[str, str]] = None) -> None:
    """Register a DataFrame for fairness analysis."""
    _datasets[dataset_id] = df
    if field_map:
        _dataset_field_maps[dataset_id] = field_map


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register-dataset", response_model=StatusResponse)
async def register_dataset(request: DatasetRegisterRequest):
    """
    Register a dataset (as CSV string) for fairness analysis.
    Useful for API clients that want to push data without file upload.
    """
    try:
        df = pd.read_csv(StringIO(request.csv_data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}")

    dataset_id = request.dataset_id or str(uuid.uuid4())
    _register_dataset(df, dataset_id, request.field_map)

    return StatusResponse(
        status="registered",
        message=f"Dataset '{dataset_id}' registered ({len(df)} rows).",
        details={"dataset_id": dataset_id, "rows": len(df), "columns": list(df.columns)},
    )


@router.post("/audit", response_model=FairnessReport)
async def run_fairness_audit(
    request: AuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: _Optional[User] = Depends(get_current_user_optional),
):
    """Run a complete fairness audit. Auth optional — records analyst if logged in."""
    df = _get_dataset(request.dataset_id)
    field_map = request.field_map or _dataset_field_maps.get(request.dataset_id)

    report = _get_fairness_engine().generate_audit(
        df, field_map=field_map, dataset_id=request.dataset_id,
        protected_columns=request.protected_columns,
        outcome_column=request.outcome_column,
        approval_values=request.approval_values,
    )
    _monitor.record_fairness_score(report.score, request.dataset_id)

    # Persist audit to DB
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
            if current_user:
                from backend.database.crud import log_action
                await log_action(db, "fairness.audit", user_id=current_user.id,
                                 resource_type="dataset", resource_id=request.dataset_id,
                                 details={"score": report.score})
    except Exception as e:
        import logging; logging.getLogger("fair_lending.fairness").warning(f"DB audit persist: {e}")

    return report


@router.get("/detect-columns/{dataset_id}")
async def detect_columns(dataset_id: str):
    """Auto-detect outcome and protected class columns in a dataset."""
    df = _get_dataset(dataset_id)
    field_map = _dataset_field_maps.get(dataset_id)
    engine = _get_fairness_engine()

    from backend.core.dataset_profiler import DatasetProfiler
    profiler = DatasetProfiler()
    dataset_type = profiler.detect_type(df)

    outcome_col = engine._detect_outcome_col(df, field_map)
    protected_cols = engine._detect_all_protected_cols(df, field_map)

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
    protected_col: Optional[str] = Query(None, description="Protected class column name"),
    outcome_col: Optional[str] = Query(None, description="Outcome/decision column name"),
):
    """
    Compute disparate impact ratio for a specific protected class column.
    If columns are not specified, all detected protected classes are analysed.
    """
    df = _get_dataset(dataset_id)
    field_map = _dataset_field_maps.get(dataset_id)

    if protected_col and outcome_col:
        ratio = _get_fairness_engine().analyze_disparate_impact(df, protected_col, outcome_col)
        return {
            "dataset_id": dataset_id,
            "protected_col": protected_col,
            "outcome_col": outcome_col,
            "disparate_impact_ratio": ratio,
            "threshold": 0.80,
            "pass": ratio >= 0.80,
        }

    # Auto-detect and analyse all protected classes
    from backend.core.fairness_engine import PROTECTED_CLASSES
    results: Dict[str, Any] = {}
    for field in PROTECTED_CLASSES:
        col = _get_fairness_engine()._detect_protected_col(df, field, field_map)
        oc = _get_fairness_engine()._detect_outcome_col(df, field_map)
        if col and oc:
            ratio = _get_fairness_engine().analyze_disparate_impact(df, col, oc)
            results[field] = {
                "column": col,
                "disparate_impact_ratio": ratio,
                "pass": ratio >= 0.80,
            }

    return {"dataset_id": dataset_id, "results": results, "threshold": 0.80}


@router.get("/approval-rates/{dataset_id}")
async def get_approval_rates(
    dataset_id: str,
    group_col: Optional[str] = Query(None, description="Grouping column"),
):
    """
    Return approval rates broken down by demographic group.
    """
    df = _get_dataset(dataset_id)
    field_map = _dataset_field_maps.get(dataset_id)
    outcome_col = _get_fairness_engine()._detect_outcome_col(df, field_map)

    if outcome_col is None:
        raise HTTPException(status_code=422, detail="No outcome column detected in this dataset.")

    if group_col:
        if group_col not in df.columns:
            raise HTTPException(status_code=422, detail=f"Column '{group_col}' not found.")
        rates = _get_fairness_engine().compute_approval_rates_by_group(df, group_col, outcome_col)
        return {"dataset_id": dataset_id, "group_col": group_col, "approval_rates": rates}

    # Return all protected classes
    from backend.core.fairness_engine import PROTECTED_CLASSES
    all_rates: Dict[str, Any] = {}
    for field in PROTECTED_CLASSES:
        col = _get_fairness_engine()._detect_protected_col(df, field, field_map)
        if col:
            rates = _get_fairness_engine().compute_approval_rates_by_group(df, col, outcome_col)
            all_rates[field] = {"column": col, "rates": rates}

    return {"dataset_id": dataset_id, "approval_rates_by_group": all_rates}


@router.post("/similar-outcomes")
async def compare_similar_outcomes(request: SimilarOutcomesRequest):
    """
    Find applicants with similar financial profiles and compare their loan outcomes.
    Useful for identifying potential disparate treatment.
    """
    df = _get_dataset(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)

    result = _get_fairness_engine().find_similar_applicant_outcomes(
        df,
        applicant_id=request.applicant_id,
        field_map=field_map,
        top_k=request.top_k,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/score/{dataset_id}")
async def get_fairness_score(dataset_id: str):
    """Return the overall fairness score for a dataset (0-100)."""
    df = _get_dataset(dataset_id)
    field_map = _dataset_field_maps.get(dataset_id)
    score = _get_fairness_engine().compute_fairness_score(df, field_map)
    return {
        "dataset_id": dataset_id,
        "fairness_score": score,
        "interpretation": (
            "Acceptable" if score >= 80
            else "Needs Attention" if score >= 60
            else "High Risk"
        ),
    }


@router.post("/ai-explain")
async def ai_explain_audit(request: AuditRequest):
    """
    Run a fairness audit then send results to the configured LLM
    (Gemini or OpenAI) for an AI-generated compliance explanation.
    """
    df = _get_dataset(request.dataset_id)
    field_map = request.field_map or _dataset_field_maps.get(request.dataset_id)

    report = _get_fairness_engine().generate_audit(
        df,
        field_map=field_map,
        dataset_id=request.dataset_id,
        protected_columns=request.protected_columns,
        outcome_column=request.outcome_column,
        approval_values=request.approval_values,
    )

    ai_explanation = _get_fairness_engine().generate_ai_explanation(report)
    _monitor.record_fairness_score(report.score, request.dataset_id)

    return {
        "report": report.model_dump(),
        "ai_explanation": ai_explanation,
        "provider": __import__("backend.core.ai_provider", fromlist=["get_active_provider"]).get_active_provider(),
        "model": __import__("backend.core.ai_provider", fromlist=["get_active_model"]).get_active_model(),
    }
