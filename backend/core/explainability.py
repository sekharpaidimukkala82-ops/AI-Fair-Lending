"""
Explainability Engine – SHAP-based explanations for ML predictions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.models.schemas import ExplanationResult, MLPrediction


class ExplainabilityEngine:
    """
    Provides SHAP-based feature explanations and natural-language summaries
    for individual and batch lending model predictions.
    """

    # ------------------------------------------------------------------
    # SHAP explanation for a single prediction
    # ------------------------------------------------------------------

    def explain_prediction(
        self,
        model: Any,
        record: Dict[str, Any],
        feature_names: List[str],
        prediction: Optional[MLPrediction] = None,
        applicant_id: Optional[str] = None,
    ) -> ExplanationResult:
        """
        Compute SHAP values for a single applicant record.

        Parameters
        ----------
        model        : Trained sklearn estimator (RandomForestClassifier).
        record       : Dict of {feature_name: value}.
        feature_names: List of feature names in model input order.
        prediction   : Pre-computed MLPrediction (optional).
        applicant_id : Identifier for the applicant.

        Returns
        -------
        ExplanationResult
        """
        import shap  # lazy import to keep startup fast

        app_id = str(applicant_id or record.get("applicant_id", "unknown"))

        # Build feature array
        row = np.array([[record.get(f, 0.0) for f in feature_names]], dtype=float)

        # Build a dummy prediction if none provided
        if prediction is None:
            try:
                prob = float(model.predict_proba(row)[0, 1])
            except Exception:
                prob = 0.5
            from backend.models.schemas import MLPrediction as _P
            prediction = _P(
                applicant_id=app_id,
                approval_probability=round(prob, 4),
                risk_score=round((1 - prob) * 100, 2),
                risk_category="MEDIUM",
                features={f: float(v) for f, v in zip(feature_names, row[0])},
            )

        # SHAP TreeExplainer for RandomForest
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(row)

            # For binary classification, take the positive class (index 1)
            if isinstance(shap_values, list) and len(shap_values) == 2:
                sv = shap_values[1][0]
            elif isinstance(shap_values, np.ndarray):
                if shap_values.ndim == 3:
                    sv = shap_values[0, :, 1]
                else:
                    sv = shap_values[0]
            else:
                sv = np.zeros(len(feature_names))

            shap_dict = {
                feature_names[i]: round(float(sv[i]), 5)
                for i in range(min(len(feature_names), len(sv)))
            }

        except Exception:
            # Fall back to permutation importance proxy
            shap_dict = self.get_feature_importance(model, feature_names)

        # Feature importance from model
        fi = self.get_feature_importance(model, feature_names)

        # Generate explanation text
        explanation_text = self.generate_explanation_text(
            ExplanationResult(
                applicant_id=app_id,
                prediction=prediction,
                shap_values=shap_dict,
                feature_importance=fi,
            )
        )

        return ExplanationResult(
            applicant_id=app_id,
            prediction=prediction,
            shap_values=shap_dict,
            feature_importance=fi,
            explanation_text=explanation_text,
        )

    # ------------------------------------------------------------------
    # Feature importance
    # ------------------------------------------------------------------

    def get_feature_importance(
        self,
        model: Any,
        feature_names: List[str],
    ) -> Dict[str, float]:
        """
        Extract normalised feature importance scores from a sklearn estimator.

        Returns
        -------
        Dict[str, float] sorted descending by importance.
        """
        try:
            importances = model.feature_importances_
            total = importances.sum() or 1.0
            normed = importances / total
            result = {
                feature_names[i]: round(float(normed[i]), 5)
                for i in range(min(len(feature_names), len(normed)))
            }
            return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
        except AttributeError:
            # Model doesn't expose feature_importances_
            return {f: round(1 / max(len(feature_names), 1), 5) for f in feature_names}

    # ------------------------------------------------------------------
    # Similar cases
    # ------------------------------------------------------------------

    def find_similar_cases(
        self,
        df: pd.DataFrame,
        record: Dict[str, Any],
        top_k: int = 5,
        feature_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find the *top_k* most similar applicants in *df* using Euclidean distance
        on numeric features.

        Parameters
        ----------
        df           : Reference DataFrame.
        record       : Target record dict.
        top_k        : Number of similar cases to return.
        feature_names: Features to use for distance; defaults to all numeric cols.

        Returns
        -------
        List of dicts (row records) sorted by similarity.
        """
        if df.empty:
            return []

        if feature_names is None:
            feature_names = list(df.select_dtypes(include=[np.number]).columns)

        # Filter to features that exist in both df and record
        valid_features = [f for f in feature_names if f in df.columns]
        if not valid_features:
            return df.head(top_k).to_dict(orient="records")

        numeric_df = df[valid_features].apply(pd.to_numeric, errors="coerce").fillna(0)
        target_vec = np.array(
            [float(record.get(f, 0.0)) for f in valid_features], dtype=float
        )

        # Min-max normalise
        col_min = numeric_df.min().values
        col_max = numeric_df.max().values
        rng = np.where(col_max - col_min > 0, col_max - col_min, 1)

        normed_df = (numeric_df.values - col_min) / rng
        normed_target = (target_vec - col_min) / rng

        distances = np.linalg.norm(normed_df - normed_target, axis=1)
        closest_idx = np.argsort(distances)[: top_k]

        results = []
        for i in closest_idx:
            row_dict = df.iloc[int(i)].to_dict()
            row_dict["_similarity_distance"] = round(float(distances[i]), 4)
            results.append(row_dict)

        return results

    # ------------------------------------------------------------------
    # Natural-language explanation
    # ------------------------------------------------------------------

    def generate_explanation_text(self, explanation: ExplanationResult) -> str:
        """
        Convert SHAP values and feature importances into a plain-English
        explanation suitable for compliance reports.
        """
        pred = explanation.prediction
        prob = pred.approval_probability
        risk = pred.risk_category

        lines: List[str] = [
            f"Prediction Summary for Applicant {explanation.applicant_id}:",
            f"  Approval Probability : {prob:.1%}",
            f"  Risk Category        : {risk}",
            "",
        ]

        # Top positive contributors (increase approval)
        shap = explanation.shap_values
        if shap:
            sorted_shap = sorted(shap.items(), key=lambda x: x[1], reverse=True)

            top_pos = [(k, v) for k, v in sorted_shap if v > 0][:3]
            top_neg = [(k, v) for k, v in sorted_shap if v < 0][-3:]

            if top_pos:
                lines.append("Key Factors Supporting Approval:")
                for feat, val in top_pos:
                    lines.append(f"  + {feat}: contributes +{val:.4f} to approval likelihood")

            if top_neg:
                lines.append("Key Risk Factors:")
                for feat, val in top_neg:
                    lines.append(f"  - {feat}: reduces approval likelihood by {abs(val):.4f}")

            lines.append("")

        # Feature importance context
        fi = explanation.feature_importance
        if fi:
            top_fi = list(fi.items())[:5]
            lines.append("Most Influential Model Features (overall):")
            for feat, imp in top_fi:
                lines.append(f"  {feat}: {imp:.1%} importance")
            lines.append("")

        # Overall assessment
        if risk == "LOW":
            lines.append("Assessment: This application presents a LOW risk profile and is a "
                         "strong candidate for approval under standard guidelines.")
        elif risk == "MEDIUM":
            lines.append("Assessment: This application presents a MEDIUM risk profile. "
                         "Standard underwriting review is recommended with attention to the "
                         "risk factors listed above.")
        elif risk == "HIGH":
            lines.append("Assessment: This application presents a HIGH risk profile. "
                         "Enhanced underwriting scrutiny is recommended. Consider requesting "
                         "additional documentation to mitigate identified risk factors.")
        else:
            lines.append("Assessment: This application presents a VERY HIGH risk profile. "
                         "Careful review is required. Compensating factors should be documented "
                         "if approval is considered.")

        # Similar cases
        if explanation.similar_cases:
            lines.append("")
            lines.append(f"Reference: {len(explanation.similar_cases)} similar historical "
                         f"applications were identified for comparative analysis.")

        return "\n".join(lines)
