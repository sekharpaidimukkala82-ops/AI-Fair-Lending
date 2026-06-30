"""
Advanced Fairness Analysis — Priority 3 Enterprise Methods.

Implements beyond the 4/5ths rule:
  - Equalized Odds (equal TPR/FPR across groups)
  - Calibration (predicted probabilities match actual outcomes per group)
  - Counterfactual Fairness (would the decision change if only protected attributes changed?)
  - Intersectional Analysis (race AND gender combined, not just separately)
  - ECOA-compliant denial letter generation
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


# ── Equalized Odds ────────────────────────────────────────────────────────────

class EqualizedOddsAnalyzer:
    """
    Checks whether TPR (True Positive Rate) and FPR (False Positive Rate)
    are approximately equal across protected groups.

    Regulatory basis: Aequitas / CFPB fairness framework
    """

    def analyze(
        self,
        df: pd.DataFrame,
        outcome_col: str,
        pred_col: str,
        protected_col: str,
        positive_label: Any = 1,
        tolerance: float = 0.10,
    ) -> Dict[str, Any]:
        results: Dict[str, Dict[str, float]] = {}
        groups = df[protected_col].dropna().unique()

        for group in groups:
            mask = df[protected_col] == group
            sub = df[mask]
            if len(sub) < 10:
                continue

            actual   = (sub[outcome_col] == positive_label).astype(int)
            pred     = (sub[pred_col]    == positive_label).astype(int)

            tp = ((actual == 1) & (pred == 1)).sum()
            fn = ((actual == 1) & (pred == 0)).sum()
            fp = ((actual == 0) & (pred == 1)).sum()
            tn = ((actual == 0) & (pred == 0)).sum()

            tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
            results[str(group)] = {"tpr": round(tpr, 4), "fpr": round(fpr, 4), "count": int(len(sub))}

        # Compute violations
        if len(results) < 2:
            return {"groups": results, "violations": [], "status": "insufficient_data"}

        tprs = [v["tpr"] for v in results.values()]
        fprs = [v["fpr"] for v in results.values()]

        violations: List[str] = []
        tpr_range = max(tprs) - min(tprs)
        fpr_range = max(fprs) - min(fprs)

        if tpr_range > tolerance:
            violations.append(
                f"TPR disparity of {tpr_range:.1%} across {protected_col} groups exceeds {tolerance:.0%} tolerance"
            )
        if fpr_range > tolerance:
            violations.append(
                f"FPR disparity of {fpr_range:.1%} across {protected_col} groups exceeds {tolerance:.0%} tolerance"
            )

        return {
            "groups": results,
            "tpr_range": round(tpr_range, 4),
            "fpr_range": round(fpr_range, 4),
            "violations": violations,
            "status": "violation" if violations else "pass",
        }


# ── Calibration Analysis ──────────────────────────────────────────────────────

class CalibrationAnalyzer:
    """
    Checks whether predicted approval probabilities match actual outcomes
    within each protected group (calibration by group).

    A well-calibrated model's predicted P(approval=0.7) should lead to
    actual approval ~70% of the time — within each demographic group.
    """

    def analyze(
        self,
        df: pd.DataFrame,
        outcome_col: str,
        prob_col: str,
        protected_col: str,
        positive_label: Any = 1,
        n_bins: int = 5,
    ) -> Dict[str, Any]:
        groups = df[protected_col].dropna().unique()
        group_results: Dict[str, Any] = {}

        for group in groups:
            mask = df[protected_col] == group
            sub = df[mask].dropna(subset=[prob_col, outcome_col])
            if len(sub) < 20:
                continue

            probs  = sub[prob_col].values.astype(float)
            actual = (sub[outcome_col] == positive_label).astype(int).values

            # Clip probs to [0,1]
            probs = np.clip(probs, 0.0, 1.0)

            bins = np.linspace(0, 1, n_bins + 1)
            bin_indices = np.digitize(probs, bins[1:-1])

            calibration_curve: List[Dict] = []
            max_error = 0.0

            for b in range(n_bins):
                in_bin = bin_indices == b
                if in_bin.sum() == 0:
                    continue
                mean_pred   = float(probs[in_bin].mean())
                mean_actual = float(actual[in_bin].mean())
                error       = abs(mean_pred - mean_actual)
                max_error   = max(max_error, error)
                calibration_curve.append({
                    "bin": b,
                    "mean_predicted": round(mean_pred, 3),
                    "mean_actual": round(mean_actual, 3),
                    "error": round(error, 3),
                    "count": int(in_bin.sum()),
                })

            group_results[str(group)] = {
                "calibration_curve": calibration_curve,
                "max_calibration_error": round(max_error, 4),
                "status": "miscalibrated" if max_error > 0.15 else "calibrated",
            }

        return {"groups": group_results, "protected_attribute": protected_col}


# ── Counterfactual Fairness ───────────────────────────────────────────────────

class CounterfactualAnalyzer:
    """
    Tests counterfactual fairness: would the decision change if only
    the protected attribute changed, holding all other features constant?

    This is the most direct test of whether a protected attribute
    causally influences the lending decision.
    """

    def analyze(
        self,
        df: pd.DataFrame,
        outcome_col: str,
        protected_col: str,
        feature_cols: List[str],
        model_predict_fn,   # callable(df) -> array of predicted labels
        positive_label: Any = 1,
        sample_size: int = 500,
    ) -> Dict[str, Any]:
        """
        For each applicant, flip their protected attribute and re-predict.
        Count how many predictions change.
        """
        groups = df[protected_col].dropna().unique()
        if len(groups) < 2:
            return {"status": "insufficient_groups", "flip_rate": 0.0}

        # Sample for performance
        sample = df.dropna(subset=[protected_col] + feature_cols).head(sample_size).copy()
        if len(sample) < 10:
            return {"status": "insufficient_data", "flip_rate": 0.0}

        original_preds = model_predict_fn(sample)

        flip_rates: Dict[str, float] = {}
        for group in groups:
            counterfactual = sample.copy()
            # Swap this group with the first other group
            other = [g for g in groups if g != group]
            if not other:
                continue
            counterfactual[protected_col] = other[0]
            cf_preds = model_predict_fn(counterfactual)

            in_group = sample[protected_col] == group
            n_group = in_group.sum()
            if n_group == 0:
                continue

            orig_group = pd.Series(original_preds)[in_group.values]
            cf_group   = pd.Series(cf_preds)[in_group.values]
            flipped = (orig_group.values != cf_group.values).sum()
            flip_rates[str(group)] = round(float(flipped / n_group), 4)

        overall_flip = float(np.mean(list(flip_rates.values()))) if flip_rates else 0.0

        return {
            "flip_rates_by_group": flip_rates,
            "overall_flip_rate": round(overall_flip, 4),
            "status": "concern" if overall_flip > 0.05 else "pass",
            "interpretation": (
                f"{overall_flip:.1%} of applicants would receive a different decision "
                f"if only their {protected_col} changed. "
                + ("This indicates the protected attribute is causally influencing decisions."
                   if overall_flip > 0.05 else
                   "No significant counterfactual effect detected.")
            ),
        }


# ── Intersectional Analysis ───────────────────────────────────────────────────

class IntersectionalAnalyzer:
    """
    Analyzes fairness at the intersection of multiple protected attributes
    (e.g., Black women vs White men — not just race OR gender separately).

    CFPB guidance recognizes that intersectional discrimination can be
    missed by single-attribute analysis.
    """

    def analyze(
        self,
        df: pd.DataFrame,
        outcome_col: str,
        protected_cols: List[str],
        positive_label: Any = 1,
        min_group_size: int = 20,
        threshold: float = 0.80,
    ) -> Dict[str, Any]:
        if len(protected_cols) < 2:
            return {"status": "need_at_least_2_attributes"}

        # Create combined intersection column
        df = df.copy()
        df["_intersection"] = df[protected_cols].astype(str).agg(" × ".join, axis=1)

        groups = df["_intersection"].value_counts()
        eligible = groups[groups >= min_group_size].index.tolist()

        if not eligible:
            return {"status": "insufficient_data", "groups_analyzed": 0}

        total_approval = (df[outcome_col] == positive_label).mean()
        results: Dict[str, Any] = {}
        violations: List[str] = []

        for group in eligible:
            mask = df["_intersection"] == group
            sub = df[mask]
            rate = (sub[outcome_col] == positive_label).mean()
            di = rate / total_approval if total_approval > 0 else 0.0

            results[group] = {
                "approval_rate": round(float(rate), 4),
                "disparate_impact": round(float(di), 4),
                "count": int(mask.sum()),
                "status": "violation" if di < threshold else "pass",
            }

            if di < threshold:
                violations.append(
                    f"Intersectional group '{group}': DI ratio {di:.3f} < {threshold} threshold "
                    f"(approval rate {rate:.1%} vs overall {total_approval:.1%})"
                )

        return {
            "protected_attributes": protected_cols,
            "overall_approval_rate": round(float(total_approval), 4),
            "groups": results,
            "violations": violations,
            "groups_analyzed": len(results),
            "status": "violations_found" if violations else "pass",
        }


# ── ECOA Denial Letter Generator ─────────────────────────────────────────────

class ECOADenialLetterGenerator:
    """
    Generates ECOA-compliant adverse action notice text for denied applications.
    Uses SHAP values (or feature importances) to identify the top denial reasons
    and maps them to regulatory language.
    """

    # Mapping from feature names to ECOA-compliant denial reason language
    _REASON_MAP: Dict[str, str] = {
        "debt_to_income_ratio":    "Excessive obligations in relation to income",
        "dti":                     "Excessive obligations in relation to income",
        "credit_score":            "Credit score below minimum threshold",
        "credit_history":          "Insufficient credit history",
        "loan_to_value_ratio":     "Collateral value insufficient for loan amount",
        "ltv":                     "Collateral value insufficient for loan amount",
        "income":                  "Insufficient income to support requested loan",
        "annual_income":           "Insufficient income to support requested loan",
        "employment_length":       "Insufficient employment history",
        "delinquency":             "Delinquent past or present credit obligations",
        "collections":             "Collection action or judgment",
        "bankruptcy":              "Bankruptcy, foreclosure, repossession, or charge-off",
        "months_since_delinquency":"Recent delinquency on credit obligations",
        "loan_amount":             "Requested loan amount exceeds guidelines",
        "property_value":          "Unacceptable property condition/type",
        "missing_info":            "Incomplete application — information not provided",
    }

    def generate(
        self,
        applicant_features: Dict[str, Any],
        shap_values: Optional[Dict[str, float]] = None,
        feature_importance: Optional[Dict[str, float]] = None,
        top_n: int = 4,
        institution_name: str = "Fair Lending Institution",
        loan_type: str = "mortgage",
    ) -> str:
        """
        Generate a full ECOA-compliant adverse action notice.

        Args:
            applicant_features: The applicant's feature dict
            shap_values: Dict of feature -> SHAP contribution (negative = denial reason)
            feature_importance: Fallback if no SHAP values
            top_n: Number of denial reasons to include (ECOA requires at most 4)
            institution_name: Lender name for the letter
            loan_type: Type of loan (mortgage, auto, personal, etc.)
        """
        # Select top denial reasons
        reasons = self._select_reasons(shap_values or feature_importance or {}, top_n)

        from datetime import date
        today = date.today().strftime("%B %d, %Y")

        letter = f"""ADVERSE ACTION NOTICE
Equal Credit Opportunity Act (ECOA) — 15 U.S.C. § 1691 et seq.
Regulation B — 12 C.F.R. Part 1002

Date: {today}
Institution: {institution_name}

RE: Notice of Credit Decision — {loan_type.title()} Loan Application

Dear Applicant,

Thank you for your recent application for a {loan_type} loan. After careful review and consideration of your application, we regret to inform you that we are unable to approve your request at this time.

PRINCIPAL REASON(S) FOR ADVERSE ACTION:

"""
        for i, reason in enumerate(reasons, 1):
            letter += f"  {i}. {reason}\n"

        letter += f"""
IMPORTANT NOTICES:

The Equal Credit Opportunity Act prohibits creditors from discriminating against credit applicants on the basis of race, color, religion, national origin, sex, marital status, age (provided the applicant has the capacity to enter into a binding contract), because all or part of the applicant's income derives from any public assistance program, or because the applicant has in good faith exercised any right under the Consumer Credit Protection Act.

You have the right to:
  • Request a statement of specific reasons within 60 days of receiving this notice.
  • Contact us at the address below to request this statement.
  • File a complaint with the Consumer Financial Protection Bureau (CFPB) at 1-855-411-CFPB (2372) or consumerfinance.gov if you believe we have discriminated against you.

If you believe you have been discriminated against, you may contact:
  Consumer Financial Protection Bureau (CFPB)
  P.O. Box 4503, Iowa City, Iowa 52244
  Telephone: 1-855-411-2372

This notice was provided in compliance with the Equal Credit Opportunity Act (ECOA), Regulation B (12 C.F.R. Part 1002), and the Fair Credit Reporting Act (FCRA) where applicable.

Sincerely,
{institution_name}
Fair Lending Compliance Department

— This is an automated adverse action notice generated in accordance with 12 C.F.R. § 1002.9 —
"""
        return letter

    def _select_reasons(self, scores: Dict[str, float], top_n: int) -> List[str]:
        """Pick the top-N negative contributors and map to regulatory language."""
        # Sort by most negative SHAP or lowest feature importance
        sorted_features = sorted(scores.items(), key=lambda x: x[1])[:top_n]
        reasons: List[str] = []
        for feat, _ in sorted_features:
            feat_lower = feat.lower().replace(" ", "_")
            # Try exact match, then partial match
            reason = self._REASON_MAP.get(feat_lower)
            if not reason:
                for key, val in self._REASON_MAP.items():
                    if key in feat_lower or feat_lower in key:
                        reason = val
                        break
            if not reason:
                reason = f"Unsatisfactory {feat.replace('_', ' ')}"
            if reason not in reasons:
                reasons.append(reason)

        return reasons[:top_n] if reasons else ["Application did not meet underwriting guidelines"]


# ── Unified Advanced Fairness Report ─────────────────────────────────────────

class AdvancedFairnessEngine:
    """Orchestrates all advanced fairness methods into a single analysis report."""

    def __init__(self):
        self.equalized_odds   = EqualizedOddsAnalyzer()
        self.calibration      = CalibrationAnalyzer()
        self.counterfactual   = CounterfactualAnalyzer()
        self.intersectional   = IntersectionalAnalyzer()
        self.denial_letters   = ECOADenialLetterGenerator()

    def full_analysis(
        self,
        df: pd.DataFrame,
        outcome_col: str,
        protected_cols: List[str],
        pred_col: Optional[str] = None,
        prob_col: Optional[str] = None,
        model_predict_fn=None,
        positive_label: Any = 1,
    ) -> Dict[str, Any]:
        """Run all available advanced fairness analyses."""
        report: Dict[str, Any] = {
            "outcome_column": outcome_col,
            "protected_attributes": protected_cols,
            "total_records": len(df),
        }

        # Intersectional (always available)
        if len(protected_cols) >= 2:
            report["intersectional"] = self.intersectional.analyze(
                df, outcome_col, protected_cols, positive_label=positive_label
            )

        # Per-attribute analyses
        per_attribute: Dict[str, Any] = {}
        for col in protected_cols:
            if col not in df.columns:
                continue
            attr: Dict[str, Any] = {}

            # Equalized Odds (needs predictions)
            if pred_col and pred_col in df.columns:
                attr["equalized_odds"] = self.equalized_odds.analyze(
                    df, outcome_col, pred_col, col, positive_label=positive_label
                )

            # Calibration (needs probabilities)
            if prob_col and prob_col in df.columns:
                attr["calibration"] = self.calibration.analyze(
                    df, outcome_col, prob_col, col, positive_label=positive_label
                )

            # Counterfactual (needs a trained model)
            if model_predict_fn is not None:
                numeric_features = [c for c in df.select_dtypes(include="number").columns
                                    if c not in [outcome_col] + protected_cols]
                attr["counterfactual"] = self.counterfactual.analyze(
                    df, outcome_col, col, numeric_features,
                    model_predict_fn, positive_label=positive_label
                )

            per_attribute[col] = attr

        report["per_attribute"] = per_attribute
        report["methods_run"] = list({k for a in per_attribute.values() for k in a.keys()}
                                     | ({"intersectional"} if "intersectional" in report else set()))

        return report
