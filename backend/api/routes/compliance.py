"""
Compliance Routes — Priority 3 & 5 Features.

  - HMDA LAR file validation (FFIEC edits)
  - CRA (Community Reinvestment Act) analysis  
  - Regulatory exam export package (OCC/FDIC/Fed format)
  - Audit trail export
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Config
from backend.database.connection import get_db
from backend.database.models import AuditLog, Dataset, FairnessAudit, MLModel, Report, User
from backend.auth.dependencies import get_current_user

router = APIRouter(prefix="/compliance", tags=["Compliance"])


# ── HMDA LAR Validation ───────────────────────────────────────────────────────

# Key FFIEC edits (subset of the full 200+ edit specification)
HMDA_REQUIRED_FIELDS = [
    "action_taken", "loan_type", "loan_purpose", "loan_amount",
    "applicant_race_1", "applicant_sex", "applicant_ethnicity_1",
    "income", "county_code",
]

HMDA_VALID_ACTION_TAKEN = {1, 2, 3, 4, 5, 6, 7, 8}
HMDA_VALID_LOAN_TYPE    = {1, 2, 3, 4}
HMDA_VALID_LOAN_PURPOSE = {1, 2, 3, 31, 32, 4, 5}
HMDA_VALID_RACE         = {1, 2, 21, 22, 23, 24, 25, 26, 27, 3, 4, 41, 42, 43, 44, 5, 6, 7}
HMDA_VALID_SEX          = {1, 2, 3, 4, 6}
HMDA_VALID_ETHNICITY    = {1, 11, 12, 13, 14, 2, 3, 4}


class HMDAValidationResult(BaseModel):
    total_records: int
    valid_records: int
    error_count: int
    warning_count: int
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    pass_rate: float
    ffiec_ready: bool


@router.post("/validate-hmda/{dataset_id}", response_model=HMDAValidationResult)
async def validate_hmda(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Validate a dataset against FFIEC HMDA LAR edit specifications.
    Returns errors and warnings that would fail a regulatory submission.
    """
    df = _load_dataset(dataset_id)
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # Normalize column names
    df.columns = [c.lower().strip() for c in df.columns]

    # Check required fields exist
    missing_fields = [f for f in HMDA_REQUIRED_FIELDS if f not in df.columns]
    if missing_fields:
        warnings.append({
            "type": "missing_fields",
            "message": f"HMDA required fields not found: {missing_fields}",
            "severity": "warning",
            "ffiec_edit": "S010",
        })

    # Validate each row
    for idx, row in df.iterrows():
        row_errors = _validate_hmda_row(row, int(str(idx)))
        errors.extend(row_errors)

        # Stop after 100 errors for performance
        if len(errors) >= 100:
            warnings.append({"type": "truncated", "message": "Showing first 100 errors only", "severity": "info", "ffiec_edit": "N/A"})
            break

    total    = len(df)
    err_rows = len({e["row"] for e in errors if "row" in e})
    valid    = total - err_rows
    pass_rate = valid / total if total > 0 else 0.0

    return HMDAValidationResult(
        total_records=total,
        valid_records=valid,
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors[:50],
        warnings=warnings,
        pass_rate=round(pass_rate, 4),
        ffiec_ready=len(errors) == 0 and len([w for w in warnings if w.get("severity") == "error"]) == 0,
    )


def _validate_hmda_row(row: pd.Series, idx: int) -> List[Dict]:
    errs = []

    def add(field, msg, edit):
        errs.append({"row": idx, "field": field, "message": msg, "ffiec_edit": edit, "severity": "error"})

    # action_taken
    if "action_taken" in row.index:
        try:
            val = int(row["action_taken"])
            if val not in HMDA_VALID_ACTION_TAKEN:
                add("action_taken", f"Invalid action_taken value: {val}", "V610")
        except (ValueError, TypeError):
            add("action_taken", "action_taken must be numeric", "S020")

    # loan_amount
    if "loan_amount" in row.index:
        try:
            val = float(row["loan_amount"])
            if val <= 0:
                add("loan_amount", "loan_amount must be > 0", "V630")
        except (ValueError, TypeError):
            add("loan_amount", "loan_amount must be numeric", "S030")

    # income
    if "income" in row.index and pd.notna(row["income"]):
        try:
            val = float(row["income"])
            if val < 0:
                add("income", "income cannot be negative", "V640")
        except (ValueError, TypeError):
            pass  # NA income is allowed

    # race
    if "applicant_race_1" in row.index:
        try:
            val = int(row["applicant_race_1"])
            if val not in HMDA_VALID_RACE:
                add("applicant_race_1", f"Invalid race code: {val}", "V680")
        except (ValueError, TypeError):
            add("applicant_race_1", "applicant_race_1 must be numeric", "S050")

    return errs


# ── CRA Analysis ──────────────────────────────────────────────────────────────

@router.post("/cra-analysis/{dataset_id}")
async def cra_analysis(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Community Reinvestment Act (CRA) analysis alongside HMDA.
    Analyzes lending patterns in low/moderate-income (LMI) census tracts.
    """
    df = _load_dataset(dataset_id)
    df.columns = [c.lower().strip() for c in df.columns]

    result: Dict[str, Any] = {"dataset_id": dataset_id, "total_records": len(df)}

    # Detect geography columns
    geo_cols = [c for c in df.columns if any(k in c for k in ["county", "tract", "census", "msa", "geo"])]
    result["geo_columns_found"] = geo_cols

    # Income category analysis (if income column present)
    income_col = next((c for c in df.columns if "income" in c), None)
    if income_col:
        df[income_col] = pd.to_numeric(df[income_col], errors="coerce")
        income_stats = df[income_col].describe().to_dict()
        # LMI threshold: below 80% of median
        median = df[income_col].median()
        lmi_count = (df[income_col] < median * 0.80).sum()
        result["income_analysis"] = {
            "stats": {k: round(float(v), 2) for k, v in income_stats.items() if pd.notna(v)},
            "lmi_applicants": int(lmi_count),
            "lmi_percentage": round(float(lmi_count / len(df) * 100), 2),
            "median_income": round(float(median), 2),
        }

    # Approval rates
    outcome_col = next((c for c in df.columns if c in ["action_taken", "decision", "loan_status"]), None)
    if outcome_col:
        approval_vals = {1, "1", "approved", "originated"}
        df["_approved"] = df[outcome_col].apply(lambda x: 1 if str(x).lower().strip() in {str(v) for v in approval_vals} else 0)
        result["overall_approval_rate"] = round(float(df["_approved"].mean()), 4)

    result["cra_notes"] = [
        "CRA performance context requires geographic census tract matching.",
        "Full CRA rating requires assessment area delineation and peer comparison.",
        "This analysis provides preliminary LMI lending patterns only.",
    ]

    return result


# ── Regulatory Exam Export ────────────────────────────────────────────────────

@router.post("/exam-export/{dataset_id}")
async def regulatory_exam_export(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    One-click export package formatted for OCC/FDIC/Fed examination.
    Returns a ZIP containing: methodology, statistical tests, samples, audit log.
    """
    buf = io.BytesIO()
    now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Load dataset info
    row = await db.execute(select(Dataset).where(Dataset.file_id == dataset_id))
    ds = row.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, "Dataset not found")

    # Load fairness audits
    row2 = await db.execute(
        select(FairnessAudit).where(FairnessAudit.dataset_id == ds.id)
        .order_by(FairnessAudit.created_at.desc()).limit(5)
    )
    audits = row2.scalars().all()

    # Load audit log
    row3 = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    )
    audit_log = row3.scalars().all()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Methodology document
        methodology = _build_methodology_doc(ds, audits)
        zf.writestr(f"exam_package/01_methodology.txt", methodology)

        # 2. Statistical test results
        stats_json = json.dumps(
            [_audit_to_dict(a) for a in audits],
            indent=2, default=str
        )
        zf.writestr(f"exam_package/02_statistical_results.json", stats_json)

        # 3. Audit trail
        audit_csv_rows = [
            ["timestamp", "action", "user_id", "resource_type", "resource_id", "details"]
        ] + [
            [
                str(log.created_at), log.action, str(log.user_id or ""),
                str(log.resource_type or ""), str(log.resource_id or ""),
                json.dumps(log.details or {})
            ]
            for log in audit_log
        ]
        audit_csv = _rows_to_csv(audit_csv_rows)
        zf.writestr(f"exam_package/03_audit_trail.csv", audit_csv)

        # 4. Remediation plan template
        remediation = _build_remediation_template(audits)
        zf.writestr(f"exam_package/04_remediation_plan_template.txt", remediation)

        # 5. Metadata
        meta = {
            "export_date": datetime.utcnow().isoformat(),
            "dataset": ds.original_filename,
            "dataset_id": dataset_id,
            "total_records": ds.total_rows,
            "quality_score": ds.quality_score,
            "audits_included": len(audits),
            "exported_by": current_user.username,
            "platform": "FairLend AI v2.0",
            "regulatory_framework": ["ECOA", "HMDA", "CRA", "FFIEC"],
        }
        zf.writestr(f"exam_package/00_metadata.json", json.dumps(meta, indent=2, default=str))

    buf.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename=exam_package_{dataset_id[:8]}_{now}.zip"
    }
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


# ── Audit Trail ───────────────────────────────────────────────────────────────

@router.get("/audit-trail")
async def get_audit_trail(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recent audit log entries for compliance review."""
    rows = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    logs = rows.scalars().all()
    return [
        {
            "id": log.id, "action": log.action, "user_id": log.user_id,
            "resource_type": log.resource_type, "resource_id": log.resource_id,
            "details": log.details, "ip_address": log.ip_address,
            "created_at": log.created_at,
        }
        for log in logs
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_dataset(file_id: str) -> pd.DataFrame:
    upload_dir = Path(Config.UPLOAD_DIR)
    for f in upload_dir.iterdir():
        if f.name.startswith(file_id):
            ext = f.suffix.lower()
            if ext == ".csv":   return pd.read_csv(f)
            if ext == ".xlsx":  return pd.read_excel(f, engine="openpyxl")
            if ext == ".json":  return pd.read_json(f)
    raise HTTPException(404, f"Dataset file not found for id '{file_id}'")


def _audit_to_dict(a: FairnessAudit) -> Dict:
    return {
        "audit_id": a.id,
        "created_at": str(a.created_at),
        "fairness_score": a.fairness_score,
        "disparate_impact_ratios": a.disparate_impact_ratios,
        "bias_indicators": a.bias_indicators,
        "findings": a.findings,
        "recommendations": a.recommendations,
    }


def _build_methodology_doc(ds: Dataset, audits: list) -> str:
    latest_score = audits[0].fairness_score if audits else None
    return f"""FAIR LENDING ANALYSIS METHODOLOGY
FairLend AI Platform v2.0
Generated: {datetime.utcnow().strftime('%B %d, %Y')}

DATASET
  Name: {ds.original_filename}
  Records: {ds.total_rows:,}
  Quality Score: {(ds.quality_score or 0) * 100:.1f}%
  Processing Date: {ds.processed_at or ds.uploaded_at}

FAIRNESS ANALYSIS METHODOLOGY
1. Disparate Impact Ratio (4/5ths Rule)
   Methodology: Calculated per EEOC Uniform Guidelines and CFPB examination procedures.
   Formula: Approval rate (protected group) / Approval rate (most-favored group)
   Threshold: 0.80 (values below indicate potential adverse impact)
   Reference: 29 C.F.R. § 1607.4(D); CFPB Supervision and Examination Manual

2. Statistical Significance Testing
   Method: Chi-square test of independence for categorical outcomes
   Alpha level: 0.05 (two-tailed)
   Minimum group size: 30 applicants

3. Comparable Borrower Analysis  
   Similar applicants matched on: income, loan amount, LTV, DTI, credit history
   Comparison: approval rates within matched pairs across protected classes

4. Advanced Methods Applied
   - Equalized Odds: Equal TPR/FPR across groups (tolerance ±10%)
   - Calibration: Predicted probabilities match actual outcomes per group
   - Intersectional Analysis: Combined protected attribute analysis

FINDINGS SUMMARY
  Audits Run: {len(audits)}
  Latest Fairness Score: {f'{latest_score:.1%}' if latest_score else 'Not available'}
  Overall Compliance Status: {'COMPLIANT' if latest_score and latest_score >= 0.80 else 'REQUIRES REVIEW'}

REGULATORY REFERENCES
  - Equal Credit Opportunity Act (ECOA), 15 U.S.C. § 1691 et seq.
  - Regulation B, 12 C.F.R. Part 1002
  - Home Mortgage Disclosure Act (HMDA), 12 U.S.C. § 2801 et seq.
  - Regulation C, 12 C.F.R. Part 1003
  - Fair Housing Act, 42 U.S.C. §§ 3601-3619
  - Community Reinvestment Act (CRA), 12 U.S.C. § 2901 et seq.
  - FFIEC Interagency Fair Lending Examination Procedures (2009, as updated)
"""


def _build_remediation_template(audits: list) -> str:
    return """REMEDIATION PLAN TEMPLATE
Institution: _____________________
Date: ____________________________
Prepared by: _____________________

IDENTIFIED ISSUES
[ ] Complete this section based on statistical_results.json findings

ROOT CAUSE ANALYSIS
[ ] Describe the root cause of any disparate impact findings

REMEDIATION ACTIONS
Action 1: ________________________
  Responsible Party: _______________
  Target Completion Date: __________
  Status: Open / In Progress / Complete

Action 2: ________________________
  [repeat as needed]

MONITORING PLAN
  [ ] Monthly fairness audits for 12 months post-remediation
  [ ] Quarterly review with Compliance Committee
  [ ] Annual independent fair lending review

SIGN-OFF
Chief Compliance Officer: _______________ Date: ________
Fair Lending Officer:     _______________ Date: ________
"""


def _rows_to_csv(rows: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue()
