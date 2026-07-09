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
    """Generate a fairness audit report. Auth optional."""
    df = _get_df(request.dataset_id)
    field_map = request.field_map

    fairness_report = _get_fairness_engine().generate_audit(df, field_map, dataset_id=request.dataset_id)
    content = _get_report_gen().generate_fairness_report(fairness_report, fmt=format)
    fname = _filename(f"fairness_report_{request.dataset_id}", format)

    # Persist report record
    try:
        from backend.database.crud import create_report, get_dataset_by_file_id
        ds = await get_dataset_by_file_id(db, request.dataset_id)
        if ds:
            await create_report(db, {
                "dataset_id": ds.id, "report_type": "fairness", "format": format,
                "generated_by_id": current_user.id if current_user else None,
                "file_size": len(content),
            })
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
    """Generate an HMDA compliance summary report."""
    df = _get_df(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)
    content = _get_report_gen().generate_compliance_report(df, field_map, fmt=format)
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
    df = _get_df(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)

    # Try to use cached predictions first
    predictions = _predictions_cache.get(request.dataset_id, [])

    # If no cached predictions, try to train on-the-fly
    if not predictions:
        try:
            ml = _get_ml_engine()
            if ml:
                result = ml.train(df, field_map)
                predictions = ml.predict_batch(df, field_map)
                _predictions_cache[request.dataset_id] = predictions
        except Exception:
            predictions = []

    # If still no predictions, generate a dataset-stats-based risk report
    if not predictions:
        content = _get_report_gen().generate_risk_report_from_df(df, field_map, fmt=format)
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
    """Generate a high-level executive summary. Always succeeds — degrades gracefully."""
    summary_data: Dict[str, Any] = request.custom_data or {}

    if request.dataset_id:
        df = _datasets.get(request.dataset_id)

        # Load from disk if not in memory
        if df is None:
            try:
                df = _get_df(request.dataset_id)
            except Exception:
                df = None

        if df is not None:
            summary_data["dataset_id"] = request.dataset_id
            summary_data["total_records"] = len(df)
            summary_data["total_fields"] = len(df.columns)

            # Fairness analysis — resilient
            try:
                field_map = _dataset_field_maps.get(request.dataset_id)
                fairness_report = _get_fairness_engine().generate_audit(
                    df, field_map, dataset_id=request.dataset_id
                )
                summary_data["fairness_score"] = fairness_report.score
                summary_data["findings"] = fairness_report.findings
                summary_data["recommendations"] = fairness_report.recommendations
                summary_data["disparate_impact_ratios"] = fairness_report.disparate_impact_ratios
            except Exception as e:
                summary_data["fairness_note"] = f"Fairness analysis unavailable: {e}"
                summary_data["findings"] = []
                summary_data["recommendations"] = [
                    "Upload an HMDA or lending dataset and run Fairness Analysis for detailed findings."
                ]

            # ML predictions — resilient
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

    if not summary_data:
        summary_data = {
            "platform": "Fair Lending Intelligence Platform",
            "message": "No dataset selected. Upload a dataset and select it from the top bar.",
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
