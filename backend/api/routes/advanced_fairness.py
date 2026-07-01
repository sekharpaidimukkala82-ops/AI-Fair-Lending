"""
Advanced Fairness Routes — Priority 3 Enterprise Methods.

Extends base fairness with:
  - Equalized Odds analysis
  - Calibration by group
  - Counterfactual fairness
  - Intersectional analysis
  - ECOA denial letter generation
  - Scheduled audit management
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Config
from backend.core.advanced_fairness import AdvancedFairnessEngine, ECOADenialLetterGenerator
from backend.core.fairness_engine import FairnessEngine
from backend.core.data_lineage import get_lineage_tracker
from backend.database.connection import get_db
from backend.database.models import Dataset, FairnessAudit, ScheduledAudit, User
from backend.database.crud import log_action
from backend.auth.dependencies import get_current_user

router = APIRouter(prefix="/fairness-advanced", tags=["Advanced Fairness"])

_advanced = AdvancedFairnessEngine()
_ecoa_gen = ECOADenialLetterGenerator()
_lineage  = get_lineage_tracker()


def _load_df(file_id: str) -> pd.DataFrame:
    """Load dataset from disk — uses same stateless loader as fairness route."""
    from backend.api.routes.fairness import _load_dataset
    return _load_dataset(file_id)


def _auto_outcome_col(df: pd.DataFrame, override: Optional[str] = None) -> str:
    """Auto-detect outcome column using the fairness engine."""
    if override and override in df.columns:
        return override
    from backend.core.fairness_engine import FairnessEngine
    col = FairnessEngine()._detect_outcome_col(df)
    if not col:
        raise HTTPException(400, "Could not detect outcome column. Please specify outcome_col.")
    return col


def _auto_protected_cols(df: pd.DataFrame, override: Optional[List[str]] = None) -> List[str]:
    """Auto-detect protected attribute columns using the fairness engine."""
    if override:
        return [c for c in override if c in df.columns]
    from backend.core.fairness_engine import FairnessEngine
    detected = FairnessEngine()._detect_all_protected_cols(df)
    cols = list(detected.values())
    if not cols:
        raise HTTPException(400, "No protected attribute columns found. Please specify protected_cols.")
    return cols


def _encode_outcome(df: pd.DataFrame, outcome_col: str) -> pd.DataFrame:
    """Encode outcome column to binary 0/1 for ML-based analysis."""
    from backend.core.fairness_engine import FairnessEngine
    engine = FairnessEngine()
    df = df.copy()
    df[outcome_col] = df[outcome_col].apply(lambda x: 1 if engine._is_approval(x) else 0)
    return df


# ── Full Advanced Analysis ────────────────────────────────────────────────────

class AdvancedAnalysisRequest(BaseModel):
    dataset_id: str
    outcome_col: Optional[str] = None
    protected_cols: Optional[List[str]] = None
    pred_col: Optional[str] = None
    prob_col: Optional[str] = None

@router.post("/full-analysis")
async def run_full_analysis(
    req: AdvancedAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run all advanced fairness methods on a dataset."""
    df = _load_df(req.dataset_id)
    outcome_col = _auto_outcome_col(df, req.outcome_col)
    protected_cols = _auto_protected_cols(df, req.protected_cols)
    df_work = _encode_outcome(df, outcome_col)

    report = _advanced.full_analysis(
        df=df_work,
        outcome_col=outcome_col,
        protected_cols=protected_cols,
        pred_col=req.pred_col,
        prob_col=req.prob_col,
        positive_label=1,
    )

    await log_action(db, "fairness.advanced.full", user_id=current_user.id,
                     resource_type="dataset", resource_id=req.dataset_id)
    return report


# ── Equalized Odds ────────────────────────────────────────────────────────────

class EqualizedOddsRequest(BaseModel):
    dataset_id: str
    outcome_col: str
    pred_col: str
    protected_col: str
    tolerance: float = 0.10

@router.post("/equalized-odds")
async def equalized_odds(req: EqualizedOddsRequest, current_user: User = Depends(get_current_user)):
    """Check equalized odds (equal TPR/FPR) across protected groups."""
    df = _load_df(req.dataset_id)
    for col in [req.outcome_col, req.pred_col, req.protected_col]:
        if col not in df.columns:
            raise HTTPException(400, f"Column '{col}' not found in dataset")
    result = _advanced.equalized_odds.analyze(
        df, req.outcome_col, req.pred_col, req.protected_col, tolerance=req.tolerance
    )
    return result


# ── Calibration ───────────────────────────────────────────────────────────────

class CalibrationRequest(BaseModel):
    dataset_id: str
    outcome_col: str
    prob_col: str
    protected_col: str

@router.post("/calibration")
async def calibration(req: CalibrationRequest, current_user: User = Depends(get_current_user)):
    """Check if prediction probabilities are calibrated within each group."""
    df = _load_df(req.dataset_id)
    result = _advanced.calibration.analyze(df, req.outcome_col, req.prob_col, req.protected_col)
    return result


# ── Intersectional ────────────────────────────────────────────────────────────

class IntersectionalRequest(BaseModel):
    dataset_id: str
    outcome_col: str
    protected_cols: List[str] = Field(..., min_length=2)
    threshold: float = 0.80

@router.post("/intersectional")
async def intersectional(req: IntersectionalRequest, current_user: User = Depends(get_current_user)):
    """Analyze fairness at the intersection of multiple protected attributes."""
    df = _load_df(req.dataset_id)
    outcome_col = _auto_outcome_col(df, req.outcome_col)
    df_work = _encode_outcome(df, outcome_col)
    result = _advanced.intersectional.analyze(
        df_work, outcome_col, req.protected_cols, threshold=req.threshold
    )
    return result


# ── ECOA Denial Letter ────────────────────────────────────────────────────────

class DenialLetterRequest(BaseModel):
    applicant_features: Dict[str, Any]
    shap_values: Optional[Dict[str, float]] = None
    feature_importance: Optional[Dict[str, float]] = None
    top_n: int = 4
    institution_name: str = "Fair Lending Institution"
    loan_type: str = "mortgage"

@router.post("/denial-letter")
async def generate_denial_letter(req: DenialLetterRequest, current_user: User = Depends(get_current_user)):
    """Generate an ECOA-compliant adverse action notice for a denied applicant."""
    letter = _ecoa_gen.generate(
        applicant_features=req.applicant_features,
        shap_values=req.shap_values,
        feature_importance=req.feature_importance,
        top_n=req.top_n,
        institution_name=req.institution_name,
        loan_type=req.loan_type,
    )
    return {"letter": letter, "type": "adverse_action_notice", "regulation": "ECOA 12 CFR Part 1002"}


# ── Data Lineage ──────────────────────────────────────────────────────────────

@router.get("/lineage/{dataset_id}")
async def get_lineage(dataset_id: str, current_user: User = Depends(get_current_user)):
    """Get the full data transformation lineage for a dataset."""
    entries = await _lineage.get_lineage(dataset_id)
    return {"dataset_id": dataset_id, "steps": entries, "total_steps": len(entries)}


# ── Scheduled Audits ──────────────────────────────────────────────────────────

class ScheduleAuditRequest(BaseModel):
    dataset_id: str
    name: str
    cron_expression: str = "0 2 * * *"
    alert_threshold: float = 0.70
    alert_email: Optional[str] = None

@router.post("/schedule-audit")
async def schedule_audit(
    req: ScheduleAuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a scheduled recurring fairness audit."""
    row = await db.execute(select(Dataset).where(Dataset.file_id == req.dataset_id))
    ds = row.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, "Dataset not found")

    sched = ScheduledAudit(
        dataset_id=ds.id,
        name=req.name,
        cron_expression=req.cron_expression,
        alert_threshold=req.alert_threshold,
        alert_email=req.alert_email,
        created_by=current_user.id,
    )
    db.add(sched)
    await db.commit()
    await db.refresh(sched)
    return {"id": sched.id, "name": sched.name, "cron": sched.cron_expression, "status": "scheduled"}


@router.get("/scheduled-audits")
async def list_scheduled_audits(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await db.execute(select(ScheduledAudit).order_by(ScheduledAudit.created_at.desc()))
    audits = rows.scalars().all()
    return [
        {
            "id": a.id, "name": a.name, "dataset_id": a.dataset_id,
            "cron_expression": a.cron_expression, "alert_threshold": a.alert_threshold,
            "is_active": a.is_active, "last_run_at": a.last_run_at,
            "last_score": a.last_score, "created_at": a.created_at,
        }
        for a in audits
    ]
