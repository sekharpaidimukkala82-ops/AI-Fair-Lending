"""
Reports routes – generate downloadable PDF and JSON compliance reports.
All routes NEVER return 404 — they always produce a report using whatever data is available.
"""
from __future__ import annotations
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
from backend.models.schemas import FairnessReport as FReport, BiasIndicator

router = APIRouter(prefix="/reports", tags=["Reports"])

# ── Singletons ──────────────────────────────────────────────────────────────

def _get_report_gen():
    if not hasattr(_get_report_gen, "_i"):
        try: _get_report_gen._i = ReportGenerator()
        except: _get_report_gen._i = None
    return _get_report_gen._i

def _get_engine():
    if not hasattr(_get_engine, "_i"):
        try: _get_engine._i = FairnessEngine()
        except: _get_engine._i = None
    return _get_engine._i

from backend.api.routes.ml import _get_ml_engine, _predictions_cache

# ── Helpers ─────────────────────────────────────────────────────────────────

def _load_df(dataset_id: str) -> Optional[pd.DataFrame]:
    """Load dataset from disk. Returns None (never raises) if not found."""
    try:
        from backend.api.routes.fairness import _load_dataset
        from fastapi import HTTPException as _H
        try:
            return _load_dataset(dataset_id)
        except _H:
            return None
    except Exception:
        return None

def _ct(fmt): return "application/pdf" if fmt == "pdf" else "application/json"
def _fn(base, fmt): return f"{base}.{fmt}"

async def _save_report(db, dataset_id, report_type, fmt, size, user):
    try:
        from backend.database.crud import create_report, get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, dataset_id)
        if ds:
            await create_report(db, {"dataset_id": ds.id, "report_type": report_type,
                                     "format": fmt, "file_size": size,
                                     "generated_by_id": user.id if user else None})
    except Exception:
        pass

# ── Request models ───────────────────────────────────────────────────────────

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

# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/fairness")
async def generate_fairness_report(
    request: FairnessReportRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate fairness PDF/JSON. Always works — uses DB cache if file missing."""
    df = _load_df(request.dataset_id)

    if df is not None:
        fairness_report = _get_engine().generate_audit(df, request.field_map, dataset_id=request.dataset_id)
    else:
        # Try DB cached audit
        try:
            from backend.database.crud import get_dataset_by_file_id, list_fairness_audits
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
                        findings=a.findings or ["Report from cached data — re-upload for fresh analysis."],
                        recommendations=a.recommendations or ["Re-upload dataset for updated results."],
                    )
                else:
                    # No file, no DB audit — generate empty report
                    fairness_report = FReport(
                        dataset_id=request.dataset_id, score=0,
                        findings=["Dataset file not available. Please re-upload and run Fairness Audit."],
                        recommendations=["Upload the dataset, then click 'Run Fairness Audit' before generating reports."],
                    )
            else:
                fairness_report = FReport(
                    dataset_id=request.dataset_id, score=0,
                    findings=["Dataset not found. Please re-upload."],
                    recommendations=["Upload the dataset to generate a full report."],
                )
        except Exception as e:
            fairness_report = FReport(
                dataset_id=request.dataset_id, score=0,
                findings=[f"Could not load data: {e}"],
                recommendations=["Re-upload the dataset and try again."],
            )

    content = _get_report_gen().generate_fairness_report(fairness_report, fmt=format)
    fname = _fn(f"fairness_report_{request.dataset_id[:8]}", format)
    await _save_report(db, request.dataset_id, "fairness", format, len(content), current_user)
    return Response(content=content, media_type=_ct(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/compliance")
async def generate_compliance_report(
    request: ComplianceReportRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate compliance report. Uses DB metadata if file missing."""
    df = _load_df(request.dataset_id)
    if df is None:
        try:
            from backend.database.crud import get_dataset_by_file_id
            ds = await get_dataset_by_file_id(db, request.dataset_id)
            if ds:
                df = pd.DataFrame({"dataset": [ds.filename], "total_rows": [ds.total_rows or 0],
                                   "total_columns": [ds.total_columns or 0],
                                   "quality_score": [ds.quality_score or 0]})
            else:
                df = pd.DataFrame({"note": ["Dataset not found — re-upload to generate full report."]})
        except Exception:
            df = pd.DataFrame({"note": ["Could not load dataset data."]})

    content = _get_report_gen().generate_compliance_report(df, None, fmt=format)
    fname = _fn(f"compliance_report_{request.dataset_id[:8]}", format)
    await _save_report(db, request.dataset_id, "compliance", format, len(content), current_user)
    return Response(content=content, media_type=_ct(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/risk")
async def generate_risk_report(
    request: RiskReportRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate risk report."""
    df = _load_df(request.dataset_id)

    if df is None:
        content = _get_report_gen().generate_risk_report_from_df(
            pd.DataFrame({"note": ["Dataset file unavailable — re-upload for full risk analysis."]}),
            None, fmt=format)
    else:
        predictions = _predictions_cache.get(request.dataset_id, [])
        if not predictions:
            try:
                ml = _get_ml_engine()
                if ml:
                    ml.train(df, None)
                    predictions = ml.predict_batch(df, None)
                    _predictions_cache[request.dataset_id] = predictions
            except Exception:
                predictions = []
        if predictions:
            content = _get_report_gen().generate_risk_report(predictions, fmt=format)
        else:
            content = _get_report_gen().generate_risk_report_from_df(df, None, fmt=format)

    fname = _fn(f"risk_report_{request.dataset_id[:8]}", format)
    await _save_report(db, request.dataset_id, "risk", format, len(content), current_user)
    return Response(content=content, media_type=_ct(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/executive-summary")
async def generate_executive_summary(
    request: ExecutiveSummaryRequest,
    format: str = Query(default="pdf", pattern="^(pdf|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Generate executive summary. ALWAYS succeeds — never returns 404."""
    summary: Dict[str, Any] = request.custom_data or {}

    if request.dataset_id:
        df = _load_df(request.dataset_id)

        # Always get filename from DB
        dataset_name = request.dataset_id[:8]
        try:
            from backend.database.crud import get_dataset_by_file_id as _get_ds
            _ds = await _get_ds(db, request.dataset_id)
            if _ds:
                dataset_name = _ds.filename
        except Exception:
            pass
        summary["dataset_name"] = dataset_name
        if df is not None:
            summary["total_records"] = len(df)
            summary["total_fields"] = len(df.columns)
            # Get actual filename from DB
            try:
                from backend.database.crud import get_dataset_by_file_id
                ds = await get_dataset_by_file_id(db, request.dataset_id)
                if ds:
                    summary["dataset_name"] = ds.filename
            except Exception:
                pass
            try:
                r = _get_engine().generate_audit(df, None, dataset_id=request.dataset_id)
                summary.update({
                    "fairness_score": r.score,
                    "disparate_impact_ratios": r.disparate_impact_ratios,
                    "approval_rates_by_group": r.approval_rates_by_group,
                    "bias_indicators": [b.model_dump() for b in r.bias_indicators],
                    "findings": r.findings,
                    "recommendations": r.recommendations,
                })
            except Exception as e:
                summary["findings"] = [f"Fairness analysis failed: {e}"]
                summary["recommendations"] = ["Re-run Fairness Audit and try again."]
        else:
            try:
                from backend.database.crud import get_dataset_by_file_id, list_fairness_audits
                ds = await get_dataset_by_file_id(db, request.dataset_id)
                if ds:
                    summary.update({"dataset_name": ds.filename, "total_records": ds.total_rows or 0,
                                    "total_fields": ds.total_columns or 0, "quality_score": ds.quality_score or 0})
                    audits = await list_fairness_audits(db, ds.id)
                    if audits:
                        a = audits[0]
                        summary.update({
                            "fairness_score": a.fairness_score or 0,
                            "disparate_impact_ratios": a.disparate_impact_ratios or {},
                            "approval_rates_by_group": a.approval_rates_by_group or {},
                            "bias_indicators": a.bias_indicators or [],
                            "findings": a.findings or [],
                            "recommendations": a.recommendations or [],
                        })
                    else:
                        summary["findings"] = ["No fairness audit found. Run Fairness Audit first."]
                        summary["recommendations"] = ["Go to Fairness Dashboard and run an audit, then generate this report."]
                else:
                    summary["findings"] = ["Dataset not found."]
                    summary["recommendations"] = ["Re-upload the dataset."]
            except Exception as e:
                summary["findings"] = [f"Error: {e}"]
                summary["recommendations"] = ["Re-upload dataset and try again."]

    if not summary:
        summary = {"findings": ["No dataset selected."],
                   "recommendations": ["Select a dataset and run Fairness Audit first."]}

    content = _get_report_gen().generate_executive_summary(summary, fmt=format)
    fname = _fn("executive_summary", format)
    await _save_report(db, request.dataset_id or "", "executive", format, len(content), current_user)
    return Response(content=content, media_type=_ct(format),
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/list")
async def list_reports(
    dataset_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """List generated reports."""
    try:
        from backend.database.models import Report
        from backend.database.crud import get_dataset_by_file_id
        from sqlalchemy import select
        q = select(Report).order_by(Report.created_at.desc())
        ds_filename = dataset_id or ""
        if dataset_id:
            ds = await get_dataset_by_file_id(db, dataset_id)
            if ds:
                q = q.where(Report.dataset_id == ds.id)
                ds_filename = ds.filename
        result = await db.execute(q.limit(20))
        reports = result.scalars().all()
        return {"reports": [{"id": r.id, "report_type": r.report_type, "format": r.format,
                              "file_size": r.file_size,
                              "created_at": r.created_at.isoformat() if r.created_at else None,
                              "dataset_filename": ds_filename}
                             for r in reports]}
    except Exception:
        return {"reports": []}
