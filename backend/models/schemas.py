"""
Pydantic schemas for the Fair Lending Intelligence Platform.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Upload / Ingestion
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    file_size: int
    status: str  # "queued" | "processing" | "completed" | "failed"
    message: str
    schema_discovery: Optional["SchemaDiscoveryResult"] = None
    processing_report: Optional["ProcessingReport"] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class SchemaDiscoveryResult(BaseModel):
    total_columns: int
    mapped_columns: int
    field_mappings: Dict[str, str]          # canonical_field -> original_column_name
    unmapped_columns: List[str]
    confidence_scores: Dict[str, float]     # canonical_field -> match confidence 0-1
    categories: Dict[str, List[str]]        # category -> list of canonical fields found
    warnings: List[str] = Field(default_factory=list)


class ProcessingReport(BaseModel):
    original_rows: int
    final_rows: int
    duplicates_removed: int
    missing_values: Dict[str, int]          # column -> count of missing values filled/dropped
    quality_score: float                    # 0-100
    standardizations_applied: List[str] = Field(default_factory=list)
    processing_time_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Narratives & Chunks
# ---------------------------------------------------------------------------

class Narrative(BaseModel):
    applicant_id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    chunk_id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: str                             # filename or dataset_id
    chunk_index: int = 0
    total_chunks: int = 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchQuery(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    id: str
    text: str
    score: float                            # similarity score 0-1
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat / RAG
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str                               # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    session_id: str = Field(default="default")
    top_k: int = Field(default=10, ge=1, le=50)
    provider: Optional[str] = Field(default=None, description="Override active provider: 'gemini' or 'openai'")
    model: Optional[str] = Field(default=None, description="Override active model")


class ChatResponse(BaseModel):
    answer: str
    sources: List[SearchResult] = Field(default_factory=list)
    session_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    response_time_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------

class BiasIndicator(BaseModel):
    field: str
    group: str
    value: float
    threshold: float
    description: str
    severity: str                           # "low" | "medium" | "high" | "critical"


class FairnessReport(BaseModel):
    dataset_id: str
    score: float                            # 0-100 (higher = fairer)
    disparate_impact_ratios: Dict[str, float] = Field(default_factory=dict)
    approval_rates_by_group: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    bias_indicators: List[BiasIndicator] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# ML Predictions
# ---------------------------------------------------------------------------

class MLPrediction(BaseModel):
    applicant_id: str
    approval_probability: float             # 0-1
    risk_score: float                       # 0-100 (higher = riskier)
    risk_category: str                      # "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH"
    features: Dict[str, float] = Field(default_factory=dict)
    predicted_at: datetime = Field(default_factory=datetime.utcnow)


class ExplanationResult(BaseModel):
    applicant_id: str
    prediction: MLPrediction
    shap_values: Dict[str, float] = Field(default_factory=dict)
    feature_importance: Dict[str, float] = Field(default_factory=dict)
    similar_cases: List[Dict[str, Any]] = Field(default_factory=list)
    explanation_text: str = ""


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

class MonitoringAlert(BaseModel):
    alert_id: str
    alert_type: str                         # "drift" | "bias" | "performance" | "anomaly"
    severity: str                           # "info" | "warning" | "critical"
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False


class DashboardData(BaseModel):
    total_queries: int
    total_datasets: int
    average_fairness_score: Optional[float]
    recent_alerts: List[MonitoringAlert] = Field(default_factory=list)
    query_volume_by_hour: Dict[str, int] = Field(default_factory=dict)
    fairness_score_trend: List[Dict[str, Any]] = Field(default_factory=list)
    dataset_stats: Dict[str, Any] = Field(default_factory=dict)
    system_status: str = "healthy"


# ---------------------------------------------------------------------------
# Training / ML Status
# ---------------------------------------------------------------------------

class TrainRequest(BaseModel):
    dataset_id: str
    target_column: Optional[str] = None    # override auto-detected decision column


class TrainResponse(BaseModel):
    model_id: str
    dataset_id: str
    accuracy: float
    features_used: List[str]
    training_rows: int
    trained_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "completed"


class SegmentResult(BaseModel):
    dataset_id: str
    num_clusters: int
    cluster_labels: List[int]
    cluster_profiles: Dict[str, Any] = Field(default_factory=dict)
    segment_sizes: Dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Generic Responses
# ---------------------------------------------------------------------------

class StatusResponse(BaseModel):
    status: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
