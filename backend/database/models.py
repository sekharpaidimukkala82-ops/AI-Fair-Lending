"""Database ORM models for all persistent entities."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database.connection import Base

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="analyst")  # admin/analyst/auditor
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    institution: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # relationships
    datasets: Mapped[list["Dataset"]] = relationship("Dataset", back_populates="owner")
    audits: Mapped[list["FairnessAudit"]] = relationship("FairnessAudit", back_populates="analyst")
    api_keys: Mapped[list["UserAPIKey"]] = relationship("UserAPIKey", back_populates="user", cascade="all, delete-orphan")


class UserAPIKey(Base):
    """Stores per-user AI provider API keys (encrypted at rest)."""
    __tablename__ = "user_api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)   # gemini / openai / groq
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)    # base64-encoded encrypted value
    active_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    file_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    dataset_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_columns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mapped_columns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duplicates_removed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    field_mappings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    schema_discovery: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # relationships
    owner: Mapped[Optional["User"]] = relationship("User", back_populates="datasets")
    audits: Mapped[list["FairnessAudit"]] = relationship("FairnessAudit", back_populates="dataset")
    ml_models: Mapped[list["MLModel"]] = relationship("MLModel", back_populates="dataset")
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="dataset")

class FairnessAudit(Base):
    __tablename__ = "fairness_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    analyst_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    fairness_score: Mapped[float] = mapped_column(Float, nullable=False)
    disparate_impact_ratios: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    approval_rates_by_group: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    bias_indicators: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    findings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    outcome_column: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    protected_columns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="audits")
    analyst: Mapped[Optional["User"]] = relationship("User", back_populates="audits")

class MLModel(Base):
    __tablename__ = "ml_models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    features_used: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    training_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    model_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="ml_models")

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)  # fairness/compliance/risk/executive
    format: Mapped[str] = mapped_column(String(10), default="pdf")
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="reports")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
#  Priority 3 — Enterprise Models
# ══════════════════════════════════════════════════════════════════════════════

class Case(Base):
    """Bias case management — created when a fairness violation is detected."""
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    audit_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("fairness_audits.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), default="medium")   # low/medium/high/critical
    status: Mapped[str] = mapped_column(String(50), default="open")        # open/investigating/resolved/closed
    assigned_to: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    fairness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bias_indicators: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    remediation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class CaseComment(Base):
    """Timeline comments on a bias case."""
    __tablename__ = "case_comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DataLineage(Base):
    """Tracks every transformation applied to a dataset."""
    __tablename__ = "data_lineage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(200), nullable=False)
    step_type: Mapped[str] = mapped_column(String(100), nullable=False)  # upload/clean/schema/embed/train/predict
    operator: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # who/what ran the step
    input_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ScheduledAudit(Base):
    """Configuration for recurring fairness audits."""
    __tablename__ = "scheduled_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), default="0 2 * * *")  # default: 2 AM daily
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.70)
    alert_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
