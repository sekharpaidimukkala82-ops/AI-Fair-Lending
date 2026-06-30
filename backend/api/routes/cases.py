"""
Case Management Routes — Priority 3 Enterprise Feature.

When bias is detected, a Case is created. Analysts track remediation
from detection → investigation → resolution with full comment timeline.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_db
from backend.database.models import Case, CaseComment, Dataset, FairnessAudit, User
from backend.auth.dependencies import get_current_user
from backend.database.crud import log_action

router = APIRouter(prefix="/cases", tags=["Case Management"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateCaseRequest(BaseModel):
    dataset_id: str
    audit_id: Optional[str] = None
    title: str = Field(..., min_length=5, max_length=500)
    description: Optional[str] = None
    severity: str = Field(default="medium")   # low / medium / high / critical
    assigned_to: Optional[str] = None

class UpdateCaseRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    remediation_notes: Optional[str] = None
    resolution_notes: Optional[str] = None

class AddCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

class CaseResponse(BaseModel):
    id: str
    dataset_id: str
    audit_id: Optional[str]
    title: str
    description: Optional[str]
    severity: str
    status: str
    assigned_to: Optional[str]
    created_by: Optional[str]
    fairness_score: Optional[float]
    bias_indicators: Optional[list]
    remediation_notes: Optional[str]
    resolution_notes: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

class CommentResponse(BaseModel):
    id: str
    case_id: str
    user_id: Optional[str]
    content: str
    created_at: datetime


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _resolve_dataset_id(file_id: str, db: AsyncSession) -> str:
    """Resolve file_id → Dataset.id (primary key)."""
    row = await db.execute(select(Dataset).where(Dataset.file_id == file_id))
    ds = row.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, f"Dataset '{file_id}' not found")
    return ds.id


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(
    req: CreateCaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new bias case (manual or auto-created from audit)."""
    ds_pk = await _resolve_dataset_id(req.dataset_id, db)

    # Pull fairness score and bias indicators from audit if provided
    fairness_score = None
    bias_indicators = None
    if req.audit_id:
        row = await db.execute(select(FairnessAudit).where(FairnessAudit.id == req.audit_id))
        audit = row.scalar_one_or_none()
        if audit:
            fairness_score = audit.fairness_score
            bias_indicators = audit.bias_indicators

    case = Case(
        dataset_id=ds_pk,
        audit_id=req.audit_id,
        title=req.title,
        description=req.description,
        severity=req.severity,
        assigned_to=req.assigned_to,
        created_by=current_user.id,
        fairness_score=fairness_score,
        bias_indicators=bias_indicators,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    await log_action(db, "case.create", user_id=current_user.id, resource_type="case", resource_id=case.id)
    return _case_to_response(case)


@router.get("", response_model=List[CaseResponse])
async def list_cases(
    dataset_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    severity: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all cases, optionally filtered."""
    q = select(Case).order_by(Case.created_at.desc())
    if dataset_id:
        ds_pk = await _resolve_dataset_id(dataset_id, db)
        q = q.where(Case.dataset_id == ds_pk)
    if status_filter:
        q = q.where(Case.status == status_filter)
    if severity:
        q = q.where(Case.severity == severity)
    rows = await db.execute(q)
    return [_case_to_response(c) for c in rows.scalars().all()]


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.execute(select(Case).where(Case.id == case_id))
    case = row.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    return _case_to_response(case)


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    req: UpdateCaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update case details / status / assignment."""
    row = await db.execute(select(Case).where(Case.id == case_id))
    case = row.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")

    updates = {k: v for k, v in req.model_dump(exclude_none=True).items()}
    updates["updated_at"] = datetime.utcnow()

    if req.status == "resolved" and case.status != "resolved":
        updates["resolved_at"] = datetime.utcnow()

    await db.execute(update(Case).where(Case.id == case_id).values(**updates))
    await db.commit()
    await db.refresh(case)
    await log_action(db, "case.update", user_id=current_user.id, resource_type="case",
                     resource_id=case_id, details=updates)
    return _case_to_response(case)


@router.delete("/{case_id}", status_code=204)
async def delete_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(CaseComment).where(CaseComment.case_id == case_id))
    await db.execute(sql_delete(Case).where(Case.id == case_id))
    await db.commit()


# ── Comments ───────────────────────────────────────────────────────────────────

@router.post("/{case_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    case_id: str,
    req: AddCommentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.execute(select(Case).where(Case.id == case_id))
    if not row.scalar_one_or_none():
        raise HTTPException(404, "Case not found")

    comment = CaseComment(case_id=case_id, user_id=current_user.id, content=req.content)
    db.add(comment)
    # Update case timestamp
    await db.execute(update(Case).where(Case.id == case_id).values(updated_at=datetime.utcnow()))
    await db.commit()
    await db.refresh(comment)
    return CommentResponse(
        id=comment.id, case_id=comment.case_id, user_id=comment.user_id,
        content=comment.content, created_at=comment.created_at,
    )


@router.get("/{case_id}/comments", response_model=List[CommentResponse])
async def list_comments(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await db.execute(
        select(CaseComment).where(CaseComment.case_id == case_id)
        .order_by(CaseComment.created_at.asc())
    )
    return [
        CommentResponse(id=c.id, case_id=c.case_id, user_id=c.user_id,
                        content=c.content, created_at=c.created_at)
        for c in rows.scalars().all()
    ]


# ── Auto-create case from audit ────────────────────────────────────────────────

async def auto_create_case_from_audit(
    audit_id: str,
    dataset_file_id: str,
    fairness_score: float,
    bias_indicators: list,
    db: AsyncSession,
    created_by: Optional[str] = None,
) -> Optional[Case]:
    """Automatically create a case when a fairness audit finds violations."""
    if fairness_score >= 0.75:
        return None   # No case needed

    severity = "critical" if fairness_score < 0.60 else "high" if fairness_score < 0.70 else "medium"
    title = f"Fairness Violation Detected — Score {fairness_score:.1%}"
    description = (
        f"Automated case created by fairness audit {audit_id[:8]}. "
        f"Score {fairness_score:.1%} is below compliance threshold. "
        f"Bias indicators: {', '.join(bias_indicators[:3]) if bias_indicators else 'None specified'}."
    )

    try:
        ds_pk = await _resolve_dataset_id(dataset_file_id, db)
        case = Case(
            dataset_id=ds_pk,
            audit_id=audit_id,
            title=title,
            description=description,
            severity=severity,
            created_by=created_by,
            fairness_score=fairness_score,
            bias_indicators=bias_indicators,
        )
        db.add(case)
        await db.commit()
        await db.refresh(case)
        return case
    except Exception as e:
        import logging
        logging.getLogger("fair_lending.cases").warning(f"Auto case creation failed: {e}")
        return None


def _case_to_response(c: Case) -> CaseResponse:
    return CaseResponse(
        id=c.id, dataset_id=c.dataset_id, audit_id=c.audit_id,
        title=c.title, description=c.description, severity=c.severity,
        status=c.status, assigned_to=c.assigned_to, created_by=c.created_by,
        fairness_score=c.fairness_score, bias_indicators=c.bias_indicators,
        remediation_notes=c.remediation_notes, resolution_notes=c.resolution_notes,
        resolved_at=c.resolved_at, created_at=c.created_at, updated_at=c.updated_at,
    )
