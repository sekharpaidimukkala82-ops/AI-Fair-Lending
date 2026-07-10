"""
Reports routes – generate downloadable PDF and JSON compliance reports.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user_optional
from backend.core.fairness_engine import FairnessEngine
from backend.core.report_generator import ReportGenerator
from backend.database.connection import get_db
from backend.database.models import User
from backend.models.schemas import FairnessReport, MLPrediction

router = APIRouter(prefix="/reports", tags=["Reports"])

def _get_report_gen():
    if not hasattr(_get_report_gen, "_instance"):
        try:
            _get_report_gen._instance = ReportGenerator()
        except Exception:
            _get_report_gen._instance = None
    return _get_report_gen._instance

def _get_fairness_engine():
    if not hasattr(_get_fairness_engine, "_instance"):
        try:
            _get_fairness_engine._instance = FairnessEngine()
        except Exception:
            _get_fairness_engine._instance = None
    return _get_fairness_engine._instance

# Stateless — no shared in-memory dicts needed
from backend.api.routes.ml import _get_ml_engine, _predictions_cache


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class FairnessReportRequest(BaseModel):
    dataset_id: str
    field_map: Optional[Dict[str, str]] = None


class ComplianceReportRequest(BaseModel):
    dataset_id: str


class RiskReportRequest(BaseModel):
    dataset_id: str


class ExecutiveSummaryRequest(BaseModel):
    dataset_id: Optional[str] = None
    custom_data: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_df(dataset_id: str) -> pd.DataFrame:
    """Stateless disk loader — same as fairness route."""
    from backend.api.routes.fairness import _load_dataset
    return _load_dataset(dataset_id)


def _get_df_safe(dataset_id: str):
    """Stateless disk loader that returns None instead of raising any error."""
    try:
        from backend.api.routes.fairness import _load_dataset
        from fastapi import HTTPException as _HTTPException
        try:
            return _load_dataset(dataset_id)
        except _HTTPException:
            return None
    except Exception:
        return None


def _content_type(fmt: str) -> str:
    return "application/pdf" if fmt == "pdf" else "application/json"


def _filename(base: str, fmt: str) -> str:
    return f"{base}.{fmt}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/fairness")
async def generate_fairness_report(
    request: FairnessReportRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate a fairness audit report. Never fails — uses DB fallback if file missing."""
    df = _get_df_safe(request.dataset_id)

    if df is not None:
        # Fresh analysis from file
        field_map = request.field_map
        fairness_report = _get_fairness_engine().generate_audit(df, field_map, dataset_id=request.dataset_id)
    else:
        # Fallback: use last saved audit from DB
        try:
            from backend.database.crud import get_dataset_by_file_id, list_fairness_audits
            from backend.models.schemas import FairnessReport as FReport, BiasIndicator
            ds = await get_dataset_by_file_id(db, request.dataset_id)
            if ds:
                audits = await list_fairness_audits(db, ds.id)
                if audits:
                    a = audits[0]
                    fairness_report = FReport(
                        dataset_id=request.dataset_id,
                        score=a.fairness_score or 0,
                        disparate_impact_ratios=a.disparate_impact_ratios or {},
                        approval_rates_by_group=a.approval_rates_by_group or {},
                        bias_indicators=[BiasIndicator(**b) for b in (a.bias_indicators or [])],
                        findings=a.findings or ["Report generated from cached audit data."],
                        recommendations=a.recommendations or ["Re-upload dataset for fresh analysis."],
                    )
                else:
                    raise HTTPException(status_code=404,
                        detail="No fairness audit found for this dataset. Run a Fairness Audit first, then generate the report.")
            else:
                raise HTTPException(status_code=404,
                    detail="Dataset not found. Please re-upload the file.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not generate report: {e}")

    content = _get_report_gen().generate_fairness_report(fairness_report, fmt=format)
    fname = _filename(f"fairness_report_{request.dataset_id[:8]}", format)
    try:
        from backend.database.crud import create_report, get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, request.dataset_id)
        if ds:
            await create_report(db, {"dataset_id": ds.id, "report_type": "fairness", "format": format,
                                     "generated_by_id": current_user.id if current_user else None,
                                     "file_size": len(content)})
    except Exception:
        pass
    return Response(content=content, media_type=_content_type(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/compliance")
async def generate_compliance_report(
    request: ComplianceReportRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate HMDA compliance report. Uses DB metadata if file missing."""
    df = _get_df_safe(request.dataset_id)
    if df is None:
        try:
            from backend.database.crud import get_dataset_by_file_id
            ds = await get_dataset_by_file_id(db, request.dataset_id)
            if not ds:
                raise HTTPException(status_code=404, detail="Dataset not found. Please re-upload.")
            df = pd.DataFrame({"dataset": [ds.filename], "rows": [ds.total_rows or 0], "columns": [ds.total_columns or 0]})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="Dataset not found. Please re-upload.")
    content = _get_report_gen().generate_compliance_report(df, None, fmt=format)
    fname = _filename(f"compliance_report_{request.dataset_id}", format)
    try:
        from backend.database.crud import create_report, get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, request.dataset_id)
        if ds:
            await create_report(db, {"dataset_id": ds.id, "report_type": "compliance", "format": format,
                                     "generated_by_id": current_user.id if current_user else None,
                                     "file_size": len(content)})
    except Exception:
        pass
    return Response(content=content, media_type=_content_type(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/risk")
async def generate_risk_report(
    request: RiskReportRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate a risk assessment report. Works with or without prior ML training."""
    df = _get_df_safe(request.dataset_id)
    if df is None:
        # Risk report from DB metadata only
        content = _get_report_gen().generate_risk_report_from_df(
            pd.DataFrame({"note": ["Dataset file not available. Re-upload for full risk analysis."]}), None, fmt=format)
        fname = _filename(f"risk_report_{request.dataset_id[:8]}", format)
        return Response(content=content, media_type=_content_type(format),
                        headers={"Content-Disposition": f"attachment; filename={fname}"})

    # Try to use cached predictions first
    predictions = _predictions_cache.get(request.dataset_id, [])

    # If no cached predictions, try to train on-the-fly
    if not predictions:
        try:
            ml = _get_ml_engine()
            if ml:
                result = ml.train(df, None)
                predictions = ml.predict_batch(df, None)
                _predictions_cache[request.dataset_id] = predictions
        except Exception:
            predictions = []

    # If still no predictions, generate a dataset-stats-based risk report
    if not predictions:
        content = _get_report_gen().generate_risk_report_from_df(df, None, fmt=format)
    else:
        content = _get_report_gen().generate_risk_report(predictions, fmt=format)

    fname = _filename(f"risk_report_{request.dataset_id}", format)
    try:
        from backend.database.crud import create_report, get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, request.dataset_id)
        if ds:
            await create_report(db, {"dataset_id": ds.id, "report_type": "risk", "format": format,
                                     "generated_by_id": current_user.id if current_user else None,
                                     "file_size": len(content)})
    except Exception:
        pass
    return Response(content=content, media_type=_content_type(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/executive-summary")
async def generate_executive_summary(
    request: ExecutiveSummaryRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate a high-level executive summary. Always succeeds — never fails with 404."""
    summary_data: Dict[str, Any] = request.custom_data or {}

    if request.dataset_id:
        # Try to load file — but don't fail if missing
        df = _get_df_safe(request.dataset_id)

        if df is not None:
            summary_data["dataset_id"] = request.dataset_id
            summary_data["total_records"] = len(df)
            summary_data["total_fields"] = len(df.columns)
            try:
                fairness_report = _get_fairness_engine().generate_audit(df, None, dataset_id=request.dataset_id)
                summary_data["fairness_score"] = fairness_report.score
                summary_data["findings"] = fairness_report.findings
                summary_data["recommendations"] = fairness_report.recommendations
                summary_data["disparate_impact_ratios"] = fairness_report.disparate_impact_ratios
                summary_data["approval_rates_by_group"] = fairness_report.approval_rates_by_group
                summary_data["bias_indicators"] = [b.model_dump() for b in fairness_report.bias_indicators]
            except Exception as e:
                summary_data["fairness_note"] = f"Fairness analysis unavailable: {e}"
                summary_data["findings"] = []
                summary_data["recommendations"] = ["Run Fairness Audit first for detailed findings."]
            try:
                predictions = _predictions_cache.get(request.dataset_id, [])
                if predictions:
                    from collections import Counter
                    summary_data["risk_distribution"] = dict(Counter(p.risk_category for p in predictions))
                    summary_data["total_predictions"] = len(predictions)
                    approved = sum(1 for p in predictions if p.approval_probability >= 0.5)
                    summary_data["model_approval_rate"] = round(approved / len(predictions) * 100, 1)
            except Exception:
                pass
        else:
            # File not on disk — use DB metadata for a partial report
            try:
                from backend.database.crud import get_dataset_by_file_id, list_fairness_audits
                ds = await get_dataset_by_file_id(db, request.dataset_id)
                if ds:
                    summary_data["dataset_id"] = request.dataset_id
                    summary_data["dataset_name"] = ds.filename
                    summary_data["total_records"] = ds.total_rows or 0
                    summary_data["total_fields"] = ds.total_columns or 0
                    summary_data["quality_score"] = ds.quality_score or 0
                    # Use last fairness audit from DB
                    audits = await list_fairness_audits(db, ds.id)
                    if audits:
                        latest = audits[0]
                        summary_data["fairness_score"] = latest.fairness_score or 0
                        summary_data["disparate_impact_ratios"] = latest.disparate_impact_ratios or {}
                        summary_data["approval_rates_by_group"] = latest.approval_rates_by_group or {}
                        summary_data["findings"] = latest.findings or []
                        summary_data["recommendations"] = latest.recommendations or []
                        summary_data["bias_indicators"] = latest.bias_indicators or []
                    else:
                        summary_data["findings"] = ["No fairness audit found. Run a Fairness Audit first."]
                        summary_data["recommendations"] = ["Upload the dataset and run Fairness Audit for full analysis."]
            except Exception as e:
                summary_data["findings"] = [f"Could not load dataset metadata: {e}"]
                summary_data["recommendations"] = ["Re-upload the dataset to generate a full report."]

    if not summary_data:
        summary_data = {
            "platform": "Fair Lending Intelligence Platform",
            "message": "No dataset selected.",
            "findings": [],
            "recommendations": ["Upload a lending dataset to generate a full executive summary."],
        }

    content = _get_report_gen().generate_executive_summary(summary_data, fmt=format)
    fname = _filename("executive_summary", format)
    try:
        from backend.database.crud import create_report, get_dataset_by_file_id
        if request.dataset_id:
            ds = await get_dataset_by_file_id(db, request.dataset_id)
            if ds:
                await create_report(db, {
                    "dataset_id": ds.id, "report_type": "executive", "format": format,
                    "generated_by_id": current_user.id if current_user else None,
                    "file_size": len(content),
                })
    except Exception:
        pass
    return Response(content=content, media_type=_content_type(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/list")
async def list_reports(
    dataset_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """List generated reports for a dataset."""
    try:
        from backend.database.crud import list_reports as db_list_reports, get_dataset_by_file_id
        from backend.database.models import Report
        from sqlalchemy import select

        q = select(Report).order_by(Report.created_at.desc())
        if dataset_id:
            ds = await get_dataset_by_file_id(db, dataset_id)
            if ds:
                q = q.where(Report.dataset_id == ds.id)
        result = await db.execute(q.limit(20))
        reports = result.scalars().all()
        return {
            "reports": [
                {
                    "id": r.id,
                    "report_type": r.report_type,
                    "format": r.format,
                    "file_size": r.file_size,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "dataset_filename": dataset_id or "",
                }
                for r in reports
            ]
        }
    except Exception as e:
        return {"reports": []}
