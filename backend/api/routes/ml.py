"""
ML routes – model training, prediction, explanation, and segmentation.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user_optional
from backend.core.explainability import ExplainabilityEngine
from backend.core.ml_engine import MLEngine
from backend.database.connection import get_db
from backend.database.models import User
from backend.models.schemas import (
    ExplanationResult,
    MLPrediction,
    SegmentResult,
    StatusResponse,
    TrainRequest,
    TrainResponse,
)

router = APIRouter(prefix="/ml", tags=["Machine Learning"])

def _get_ml_engine():
    if not hasattr(_get_ml_engine, "_instance"):
        try:
            _get_ml_engine._instance = MLEngine()
        except Exception as e:
            import logging; logging.getLogger("fair_lending.ml").error(f"MLEngine init failed: {e}")
            _get_ml_engine._instance = None
    if _get_ml_engine._instance is None:
        raise HTTPException(status_code=503, detail="ML engine unavailable.")
    return _get_ml_engine._instance

def _get_explain_engine():
    if not hasattr(_get_explain_engine, "_instance"):
        try:
            _get_explain_engine._instance = ExplainabilityEngine()
        except Exception as e:
            import logging; logging.getLogger("fair_lending.ml").error(f"ExplainEngine init failed: {e}")
            _get_explain_engine._instance = None
    if _get_explain_engine._instance is None:
        raise HTTPException(status_code=503, detail="Explainability engine unavailable.")
    return _get_explain_engine._instance

# Cache predictions by dataset_id for use by reports route
_predictions_cache: Dict[str, List[MLPrediction]] = {}

# Shared dataset store reference
from backend.api.routes.fairness import _datasets, _dataset_field_maps


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class PredictRequest(BaseModel):
    record: Dict[str, Any] = Field(..., description="Applicant feature dict")
    applicant_id: Optional[str] = None


class BatchPredictRequest(BaseModel):
    dataset_id: str


class AnomalyRequest(BaseModel):
    dataset_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_df(dataset_id: str) -> pd.DataFrame:
    df = _datasets.get(dataset_id)
    if df is None:
        # Try loading from disk on server restart
        try:
            from backend.config import Config
            upload_dir = Path(Config.UPLOAD_DIR)
            for f in upload_dir.iterdir():
                if f.name.startswith(dataset_id):
                    ext = f.suffix.lower()
                    if ext == ".csv":
                        df = pd.read_csv(f)
                    elif ext == ".xlsx":
                        df = pd.read_excel(f, engine="openpyxl")
                    elif ext == ".json":
                        df = pd.read_json(f)
                    if df is not None:
                        _datasets[dataset_id] = df
                        return df
        except Exception:
            pass
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset_id}' not found. Please re-upload your dataset.",
        )
    return df


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/train", response_model=TrainResponse)
async def train_model(
    request: TrainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Train the approval prediction model. Auth optional — records trainer if logged in."""
    df = _get_df(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)

    try:
        metrics = _get_ml_engine().train(
            df, field_map=field_map, target_col_override=request.target_column,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Persist to DB
    try:
        from backend.database.crud import upsert_ml_model, get_dataset_by_file_id, log_action
        ds = await get_dataset_by_file_id(db, request.dataset_id)
        if ds:
            await upsert_ml_model(db, {
                "model_id": metrics["model_id"],
                "dataset_id": ds.id,
                "accuracy": metrics["accuracy"],
                "features_used": metrics["features_used"],
                "training_rows": metrics["training_rows"],
                "is_active": True,
            })
            if current_user:
                await log_action(db, "ml.train", user_id=current_user.id,
                                 resource_type="dataset", resource_id=request.dataset_id,
                                 details={"accuracy": metrics["accuracy"], "model_id": metrics["model_id"]})
    except Exception as e:
        import logging; logging.getLogger("fair_lending.ml").warning(f"DB ml persist: {e}")

    return TrainResponse(
        model_id=metrics["model_id"],
        dataset_id=request.dataset_id,
        accuracy=metrics["accuracy"],
        features_used=metrics["features_used"],
        training_rows=metrics["training_rows"],
    )


@router.post("/predict", response_model=MLPrediction)
async def predict_single(request: PredictRequest):
    """Predict approval probability and risk for a single applicant record."""
    if not _get_ml_engine().is_trained:
        raise HTTPException(
            status_code=422,
            detail="Model not trained. POST to /ml/train first.",
        )

    try:
        prediction = _get_ml_engine().predict_approval(request.record, request.applicant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}")

    return prediction


@router.post("/predict-batch", response_model=List[MLPrediction])
async def predict_batch(request: BatchPredictRequest):
    """Predict approval probabilities for all applicants in a dataset."""
    if not _get_ml_engine().is_trained:
        raise HTTPException(status_code=422, detail="Model not trained. POST to /ml/train first.")

    df = _get_df(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)

    try:
        predictions = _get_ml_engine().predict_batch(df, field_map)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {exc}")

    # Cache for reports
    _predictions_cache[request.dataset_id] = predictions

    return predictions


@router.get("/explain/{applicant_id}")
async def explain_prediction(
    applicant_id: str,
    dataset_id: Optional[str] = None,
):
    """
    Generate a SHAP-based explanation for an applicant's prediction.
    Requires batch predictions to have been run first (or dataset_id provided).
    """
    if not _get_ml_engine().is_trained:
        raise HTTPException(status_code=422, detail="Model not trained.")

    # Find the prediction in the cache
    prediction: Optional[MLPrediction] = None
    if dataset_id and dataset_id in _predictions_cache:
        for p in _predictions_cache[dataset_id]:
            if p.applicant_id == applicant_id:
                prediction = p
                break

    # Build record from feature values
    if prediction is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached prediction for applicant '{applicant_id}'. "
                "Run POST /ml/predict-batch first."
            ),
        )

    record = dict(prediction.features)

    # Find similar cases from the dataset
    similar_cases: List[Dict[str, Any]] = []
    if dataset_id and dataset_id in _datasets:
        df = _datasets[dataset_id]
        similar_cases = _get_explain_engine().find_similar_cases(
            df, record, top_k=5, feature_names=_get_ml_engine().feature_names
        )

    explanation = _get_explain_engine().explain_prediction(
        model=_get_ml_engine()._rf_model,
        record=record,
        feature_names=_get_ml_engine().feature_names,
        prediction=prediction,
        applicant_id=applicant_id,
    )
    explanation.similar_cases = similar_cases
    explanation.explanation_text = _get_explain_engine().generate_explanation_text(explanation)

    return explanation


@router.get("/feature-importance")
async def get_feature_importance():
    """Return global feature importance from the trained model."""
    if not _get_ml_engine().is_trained:
        raise HTTPException(status_code=422, detail="Model not trained.")

    importance = _get_explain_engine().get_feature_importance(
        _get_ml_engine()._rf_model, _get_ml_engine().feature_names
    )
    return {
        "model_id": _get_ml_engine().model_id,
        "feature_importance": importance,
    }


@router.post("/segments", response_model=SegmentResult)
async def get_applicant_segments(request: BatchPredictRequest):
    """
    Segment applicants using KMeans clustering.
    Returns cluster assignments and profile summaries.
    """
    if not _get_ml_engine().is_trained:
        raise HTTPException(status_code=422, detail="Model not trained.")

    df = _get_df(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)

    try:
        segmented_df = _get_ml_engine().segment_applicants(df, field_map)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Build cluster profiles
    cluster_labels = segmented_df["cluster"].tolist()
    num_clusters = len(set(cluster_labels))

    cluster_profiles: Dict[str, Any] = {}
    segment_sizes: Dict[str, int] = {}

    numeric_cols = list(segmented_df.select_dtypes(include=["number"]).columns)
    numeric_cols = [c for c in numeric_cols if c != "cluster"]

    for cid in sorted(set(cluster_labels)):
        subset = segmented_df[segmented_df["cluster"] == cid]
        size = len(subset)
        segment_sizes[f"cluster_{cid}"] = size
        if numeric_cols:
            profile = subset[numeric_cols].mean().round(2).to_dict()
        else:
            profile = {}
        cluster_profiles[f"cluster_{cid}"] = {
            "size": size,
            "pct": round(size / len(df) * 100, 1),
            "avg_features": profile,
        }

    return SegmentResult(
        dataset_id=request.dataset_id,
        num_clusters=num_clusters,
        cluster_labels=cluster_labels,
        cluster_profiles=cluster_profiles,
        segment_sizes=segment_sizes,
    )


@router.post("/anomalies")
async def detect_anomalies(request: AnomalyRequest):
    """
    Detect anomalous loan applications using IsolationForest.
    Returns indices of flagged records.
    """
    if not _get_ml_engine().is_trained:
        raise HTTPException(status_code=422, detail="Model not trained.")

    df = _get_df(request.dataset_id)
    field_map = _dataset_field_maps.get(request.dataset_id)

    try:
        anomaly_indices = _get_ml_engine().detect_anomalies(df, field_map)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    anomalous_records = df.iloc[anomaly_indices].to_dict(orient="records")

    return {
        "dataset_id": request.dataset_id,
        "total_records": len(df),
        "anomaly_count": len(anomaly_indices),
        "anomaly_indices": anomaly_indices,
        "anomalous_records": anomalous_records[:50],  # limit response size
    }


@router.get("/model-info")
async def get_model_info():
    """Return metadata about the currently trained model."""
    return {
        "is_trained": _get_ml_engine().is_trained,
        "model_id": _get_ml_engine().model_id,
        "accuracy": _get_ml_engine().accuracy,
        "features": _get_ml_engine().feature_names,
        "feature_count": len(_get_ml_engine().feature_names),
    }
