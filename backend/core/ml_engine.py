"""
ML Engine – trains and serves approval-prediction and anomaly-detection models.
"""

from __future__ import annotations

import os
import pickle
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import accuracy_score

from backend.config import Config
from backend.models.schemas import MLPrediction


# Decision values considered "approved"
APPROVAL_VALUES = {"approved", "originated", "loan originated", "approved but not accepted"}

# Risk threshold mapping (probability of approval → risk category)
RISK_THRESHOLDS = Config.RISK_THRESHOLDS


class MLEngine:
    """
    Manages RandomForest (approval prediction), IsolationForest (anomaly detection),
    and KMeans (applicant segmentation) models.
    """

    def __init__(self) -> None:
        self._rf_model: Optional[RandomForestClassifier] = None
        self._iso_model: Optional[IsolationForest] = None
        self._kmeans_model: Optional[KMeans] = None
        self._scaler: Optional[StandardScaler] = None
        self._label_encoders: Dict[str, LabelEncoder] = {}
        self._feature_names: List[str] = []
        self._model_id: Optional[str] = None
        self._trained_at: Optional[datetime] = None
        self._accuracy: float = 0.0

        # Try to load persisted models
        self._load_models()

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def _numeric_features(self, df: pd.DataFrame) -> List[str]:
        """Return numeric column names (excluding obvious ID columns)."""
        return [
            c for c in df.select_dtypes(include=[np.number]).columns
            if not any(kw in c.lower() for kw in ("id", "index"))
        ]

    def _prepare_features(
        self,
        df: pd.DataFrame,
        fit: bool = False,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Encode categoricals, fill missing values, scale.

        Returns (X_array, feature_names).
        """
        df = df.copy()

        # Determine numeric and categorical columns
        num_cols = self._numeric_features(df)
        cat_cols = [
            c for c in df.select_dtypes(include=["object", "category"]).columns
            if not any(kw in c.lower() for kw in ("id", "decision", "action", "outcome", "status"))
            and df[c].nunique() <= 50
        ]

        feature_parts: List[pd.Series] = []
        feature_names: List[str] = []

        # Numeric features
        for col in num_cols:
            series = pd.to_numeric(df[col], errors="coerce").fillna(0)
            feature_parts.append(series)
            feature_names.append(col)

        # Categorical features (label encoded)
        for col in cat_cols:
            series = df[col].astype(str).fillna("Unknown")
            if fit:
                le = LabelEncoder()
                encoded = le.fit_transform(series)
                self._label_encoders[col] = le
            else:
                le = self._label_encoders.get(col)
                if le is None:
                    continue
                # Handle unseen labels
                known = set(le.classes_)
                series = series.map(lambda v: v if v in known else le.classes_[0])
                encoded = le.transform(series)
            feature_parts.append(pd.Series(encoded, index=df.index, name=col))
            feature_names.append(col)

        if not feature_parts:
            return np.zeros((len(df), 1)), ["dummy"]

        X = np.column_stack([s.values for s in feature_parts])

        if fit:
            self._scaler = StandardScaler()
            X = self._scaler.fit_transform(X)
        elif self._scaler is not None:
            # Align columns (may differ from training)
            if X.shape[1] == len(self._feature_names):
                X = self._scaler.transform(X)

        return X, feature_names

    def _encode_target(self, series: pd.Series) -> np.ndarray:
        """Convert decision strings to binary (1 = approved, 0 = denied/other).
        Uses the same universal approval check as the fairness engine."""
        from backend.core.fairness_engine import FairnessEngine
        engine = FairnessEngine()
        return series.apply(engine._is_approval).astype(int).values

    def _resolve_target_col(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
        override: Optional[str] = None,
    ) -> Optional[str]:
        if override and override in df.columns:
            return override
        if field_map and "decision" in field_map:
            return field_map["decision"]
        # Use the fairness engine's smarter detection
        from backend.core.fairness_engine import FairnessEngine
        return FairnessEngine()._detect_outcome_col(df, field_map)

    def _resolve_id_col(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        if field_map and "applicant_id" in field_map:
            return field_map["applicant_id"]
        if "applicant_id" in df.columns:
            return "applicant_id"
        return None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
        target_col_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Train RandomForest (approval prediction) and IsolationForest (anomaly detection).

        Returns a dict of training metrics.
        """
        target_col = self._resolve_target_col(df, field_map, target_col_override)
        if target_col is None:
            raise ValueError("Could not find a decision/outcome column for training.")

        # Drop non-feature columns — outcome, IDs, and outcome-correlated columns
        # Denial reason columns directly leak the outcome — must be excluded
        LEAKAGE_KEYWORDS = (
            "denial", "deny", "rejection", "action_taken", "action_name",
            "outcome", "decision", "status", "purchaser", "preapproval",
        )
        drop_cols = [target_col]
        id_col = self._resolve_id_col(df, field_map)
        if id_col:
            drop_cols.append(id_col)
        # Also drop any column that would leak the outcome
        for col in df.columns:
            cl = col.lower()
            if any(kw in cl for kw in LEAKAGE_KEYWORDS) and col not in drop_cols:
                drop_cols.append(col)

        feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        y = self._encode_target(df[target_col])

        X, feature_names = self._prepare_features(feature_df, fit=True)
        self._feature_names = feature_names

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if y.sum() > 1 else None
        )

        # RandomForest
        self._rf_model = RandomForestClassifier(
            n_estimators=Config.RANDOM_FOREST_ESTIMATORS,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced",
        )
        self._rf_model.fit(X_train, y_train)
        self._accuracy = float(accuracy_score(y_test, self._rf_model.predict(X_test)))

        # IsolationForest (unsupervised)
        self._iso_model = IsolationForest(
            n_estimators=100,
            contamination=Config.ANOMALY_CONTAMINATION,
            random_state=42,
            n_jobs=-1,
        )
        self._iso_model.fit(X)

        # KMeans
        n_clusters = min(Config.KMEANS_CLUSTERS, len(df) // 10 + 1)
        self._kmeans_model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        self._kmeans_model.fit(X)

        self._model_id = str(uuid.uuid4())
        self._trained_at = datetime.utcnow()

        # Persist
        self._save_models()

        return {
            "model_id": self._model_id,
            "accuracy": round(self._accuracy, 4),
            "training_rows": len(X_train),
            "test_rows": len(X_test),
            "features_used": feature_names,
            "trained_at": self._trained_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def _risk_category(self, prob_approval: float) -> str:
        if prob_approval >= Config.RISK_THRESHOLDS["LOW"]:
            return "LOW"
        elif prob_approval >= Config.RISK_THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        elif prob_approval >= Config.RISK_THRESHOLDS["HIGH"]:
            return "HIGH"
        return "VERY_HIGH"

    def predict_approval(
        self,
        record: Dict[str, Any],
        applicant_id: Optional[str] = None,
    ) -> MLPrediction:
        """Predict approval probability for a single applicant record."""
        if self._rf_model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        df_single = pd.DataFrame([record])
        X, _ = self._prepare_features(df_single, fit=False)

        prob = float(self._rf_model.predict_proba(X)[0, 1])
        risk_score = round((1 - prob) * 100, 2)
        risk_cat = self._risk_category(prob)

        features = {
            name: float(val)
            for name, val in zip(self._feature_names, X[0])
            if not np.isnan(val)
        }

        return MLPrediction(
            applicant_id=str(applicant_id or record.get("applicant_id", uuid.uuid4())),
            approval_probability=round(prob, 4),
            risk_score=risk_score,
            risk_category=risk_cat,
            features=features,
        )

    def predict_batch(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> List[MLPrediction]:
        """Predict approval probabilities for every row in a DataFrame."""
        if self._rf_model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        id_col = self._resolve_id_col(df, field_map)
        target_col = self._resolve_target_col(df, field_map)

        drop_cols = []
        if id_col:
            drop_cols.append(id_col)
        if target_col:
            drop_cols.append(target_col)

        feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        X, _ = self._prepare_features(feature_df, fit=False)

        probs = self._rf_model.predict_proba(X)[:, 1]

        predictions: List[MLPrediction] = []
        for i, prob in enumerate(probs):
            app_id = str(df[id_col].iloc[i]) if id_col and id_col in df.columns else str(i)
            prob_f = float(prob)
            features = {
                name: float(val)
                for name, val in zip(self._feature_names, X[i])
                if not np.isnan(val)
            }
            predictions.append(
                MLPrediction(
                    applicant_id=app_id,
                    approval_probability=round(prob_f, 4),
                    risk_score=round((1 - prob_f) * 100, 2),
                    risk_category=self._risk_category(prob_f),
                    features=features,
                )
            )

        return predictions

    # ------------------------------------------------------------------
    # Segmentation
    # ------------------------------------------------------------------

    def segment_applicants(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        Assign cluster labels to every applicant.
        Returns df with an added 'cluster' column.
        """
        if self._kmeans_model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        id_col = self._resolve_id_col(df, field_map)
        target_col = self._resolve_target_col(df, field_map)

        drop_cols = [c for c in [id_col, target_col] if c]
        feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        X, _ = self._prepare_features(feature_df, fit=False)

        labels = self._kmeans_model.predict(X)
        result = df.copy()
        result["cluster"] = labels
        return result

    # ------------------------------------------------------------------
    # Anomaly Detection
    # ------------------------------------------------------------------

    def detect_anomalies(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> List[int]:
        """
        Return a list of row indices that are flagged as anomalous.
        """
        if self._iso_model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        id_col = self._resolve_id_col(df, field_map)
        target_col = self._resolve_target_col(df, field_map)

        drop_cols = [c for c in [id_col, target_col] if c]
        feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        X, _ = self._prepare_features(feature_df, fit=False)

        predictions = self._iso_model.predict(X)
        # IsolationForest returns -1 for anomalies, +1 for inliers
        return [int(i) for i, p in enumerate(predictions) if p == -1]

    # ------------------------------------------------------------------
    # Model Persistence
    # ------------------------------------------------------------------

    def _model_path(self, name: str) -> str:
        return os.path.join(Config.MODELS_DIR, f"{name}.pkl")

    def _save_models(self) -> None:
        os.makedirs(Config.MODELS_DIR, exist_ok=True)
        payload = {
            "rf_model": self._rf_model,
            "iso_model": self._iso_model,
            "kmeans_model": self._kmeans_model,
            "scaler": self._scaler,
            "label_encoders": self._label_encoders,
            "feature_names": self._feature_names,
            "model_id": self._model_id,
            "accuracy": self._accuracy,
            "trained_at": self._trained_at,
        }
        with open(self._model_path("lending_models"), "wb") as f:
            pickle.dump(payload, f)

    def _load_models(self) -> None:
        path = self._model_path("lending_models")
        if not os.path.exists(path):
            return
        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)
            self._rf_model       = payload.get("rf_model")
            self._iso_model      = payload.get("iso_model")
            self._kmeans_model   = payload.get("kmeans_model")
            self._scaler         = payload.get("scaler")
            self._label_encoders = payload.get("label_encoders", {})
            self._feature_names  = payload.get("feature_names", [])
            self._model_id       = payload.get("model_id")
            self._accuracy       = payload.get("accuracy", 0.0)
            self._trained_at     = payload.get("trained_at")
        except Exception:
            pass  # If loading fails, start fresh

    @property
    def is_trained(self) -> bool:
        return self._rf_model is not None

    @property
    def model_id(self) -> Optional[str]:
        return self._model_id

    @property
    def feature_names(self) -> List[str]:
        return list(self._feature_names)

    @property
    def accuracy(self) -> float:
        return self._accuracy
