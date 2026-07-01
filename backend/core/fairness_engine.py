"""
Fairness Engine – disparate impact analysis, bias detection, and fair lending auditing.
Supports HMDA official format, German Credit, Lending Club, and generic CSV datasets.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.config import Config
from backend.core.dataset_profiler import DatasetProfiler, HMDA_APPROVAL_CODES, HMDA_DENIAL_CODES
from backend.models.schemas import BiasIndicator, FairnessReport


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All possible protected class column patterns to check
PROTECTED_CLASS_PATTERNS: Dict[str, List[str]] = {
    "gender": ["applicant_sex", "derived_sex", "sex", "gender", "personal_status_sex",
               "personal_status", "co_applicant_sex", "applicant_sex_name"],
    "race":   ["applicant_race_1", "derived_race", "race", "applicant_race",
               "race_1", "co_applicant_race_1", "applicant_race_name_1", "ethnicity"],
    "age":    ["applicant_age", "age", "borrower_age", "applicant_age_above_62",
               "age_group", "age_bracket"],
    "ethnicity": ["applicant_ethnicity_1", "derived_ethnicity", "ethnicity",
                  "applicant_ethnicity_name_1"],
}

# Keep PROTECTED_CLASSES as a flat list for backward compatibility with existing routes
PROTECTED_CLASSES = list(PROTECTED_CLASS_PATTERNS.keys())

OUTCOME_PATTERNS: List[str] = [
    "action_taken", "decision", "loan_status", "default",
    "outcome", "class", "target", "label", "y",
    "credit_risk", "approval_status", "application_status",
    "action_taken_name", "loan_decision",
]

SEVERITY_LEVELS = {
    "critical": 0.60,
    "high":     0.70,
    "medium":   0.80,
    "low":      1.20,
}

_profiler = DatasetProfiler()


class FairnessEngine:
    """
    Generic fair lending auditor. Handles:
    - HMDA official LAR (numeric codes auto-translated)
    - HMDA legacy (loan_amount_000s format)
    - German Credit dataset
    - Lending Club / Fannie Mae / Freddie Mac
    - Any generic lending CSV
    """

    # ------------------------------------------------------------------
    # Column Detection
    # ------------------------------------------------------------------

    def _detect_outcome_col(
        self, df: pd.DataFrame, field_map: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        if field_map and "decision" in field_map:
            col = field_map["decision"]
            if col in df.columns:
                return col
        # Exact match first
        for col in df.columns:
            if col.lower().strip() in OUTCOME_PATTERNS:
                return col
        # Partial match
        for col in df.columns:
            cl = col.lower()
            if any(pat in cl for pat in ["action_taken", "decision", "outcome",
                                          "default", "loan_status", "target",
                                          "label", "class"]):
                return col
        return None

    def _detect_protected_col(
        self,
        df: pd.DataFrame,
        field_name: str,
        field_map: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        if field_map and field_name in field_map:
            col = field_map[field_name]
            if col in df.columns:
                return col
        patterns = PROTECTED_CLASS_PATTERNS.get(field_name, [field_name])
        # Exact match
        for pat in patterns:
            for col in df.columns:
                if col.lower().strip() == pat.lower():
                    return col
        # Substring match
        for pat in patterns:
            for col in df.columns:
                if pat in col.lower():
                    return col
        return None

    def _detect_all_protected_cols(
        self, df: pd.DataFrame, field_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Return {canonical_field: actual_column_name} for all detected protected classes."""
        found = {}
        for field_name in PROTECTED_CLASS_PATTERNS:
            col = self._detect_protected_col(df, field_name, field_map)
            if col and col in df.columns:
                found[field_name] = col
        return found

    # ------------------------------------------------------------------
    # Outcome normalization
    # ------------------------------------------------------------------

    def _is_approval(self, value: Any) -> bool:
        """Universal approval check for any dataset format."""
        return _profiler.is_approval(value)

    def _approval_rate(self, series: pd.Series) -> float:
        if len(series) == 0:
            return 0.0
        return series.apply(self._is_approval).sum() / len(series)

    # ------------------------------------------------------------------
    # Group normalization
    # ------------------------------------------------------------------

    def _normalize_group_values(self, series: pd.Series, field_name: str) -> pd.Series:
        """
        Normalize group column values for consistent grouping:
        - Translate HMDA codes to labels
        - Extract gender from compound strings like 'male : single'
        - Capitalize for display
        """
        s = series.astype(str).str.strip()

        if field_name in ("gender", "sex"):
            s = _profiler.normalize_gender_col(s)
        elif field_name in ("race", "ethnicity"):
            s = _profiler.normalize_race_col(s)
        else:
            # Generic: handle compound strings
            if s.str.contains(" : ", na=False).any():
                s = s.str.split(" : ").str[0].str.strip()
            # Capitalize
            s = s.str.title()

        # Replace codes like "Not Provided", "Not Applicable" → group as "Unknown"
        not_provided = {"Not Provided", "Not Applicable", "No Co-Applicant",
                        "Information Not Provided", "6", "7", "8", "Nan", "None", ""}
        s = s.map(lambda v: "Unknown" if v in not_provided else v)
        return s

    # ------------------------------------------------------------------
    # Backward-compatible group normalization (used by older routes)
    # ------------------------------------------------------------------

    def _normalize_group_col(self, df: pd.DataFrame, col: str) -> pd.Series:
        """
        Normalize a group column for analysis.
        Handles compound values like 'male : single' → 'male'.
        """
        series = df[col].astype(str).str.strip().str.lower()
        if series.str.contains(" : ").any():
            series = series.str.split(" : ").str[0].str.strip()
        return series

    # ------------------------------------------------------------------
    # Disparate Impact
    # ------------------------------------------------------------------

    def analyze_disparate_impact(
        self,
        df: pd.DataFrame,
        protected_col: str,
        outcome_col: str,
    ) -> float:
        if protected_col not in df.columns or outcome_col not in df.columns:
            return 1.0

        # Detect field name for normalization
        field_name = "gender" if any(kw in protected_col.lower()
                                      for kw in ["sex", "gender"]) else "race"

        group_rates = self.compute_approval_rates_by_group(
            df, protected_col, outcome_col, field_name=field_name
        )
        # Include ALL groups including those with 0% approval — that's the worst violation
        rates = [v for v in group_rates.values()
                 if v is not None and not pd.isna(v)]

        if len(rates) < 2:
            return 1.0

        highest = max(rates)
        lowest  = min(rates)
        if highest == 0:
            return 1.0

        return round(lowest / highest, 4)

    # ------------------------------------------------------------------
    # Approval Rates by Group
    # ------------------------------------------------------------------

    def compute_approval_rates_by_group(
        self,
        df: pd.DataFrame,
        group_col: str,
        outcome_col: str,
        field_name: str = "generic",
    ) -> Dict[str, float]:
        if group_col not in df.columns or outcome_col not in df.columns:
            return {}

        normalized = self._normalize_group_values(df[group_col], field_name)
        temp_df = df.copy()
        temp_df["_grp"] = normalized

        rates: Dict[str, float] = {}
        for grp_val, grp_df in temp_df.groupby("_grp"):
            if str(grp_val) == "Unknown":
                continue   # skip unknown/not-provided groups
            rate = self._approval_rate(grp_df[outcome_col])
            rates[str(grp_val)] = round(rate, 4)

        return rates

    # ------------------------------------------------------------------
    # Similar Applicant Outcomes
    # ------------------------------------------------------------------

    def find_similar_applicant_outcomes(
        self,
        df: pd.DataFrame,
        applicant_id: Any,
        field_map: Optional[Dict[str, str]] = None,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        id_col = None
        if field_map and "applicant_id" in field_map:
            id_col = field_map["applicant_id"]
        elif "applicant_id" in df.columns:
            id_col = "applicant_id"

        if id_col is None:
            return {"error": "No applicant_id column found."}

        match = df[df[id_col].astype(str) == str(applicant_id)]
        if match.empty:
            return {"error": f"Applicant {applicant_id} not found."}

        target = match.iloc[0]
        numeric_fields = [
            field_map.get(cf, cf) if field_map else cf
            for cf in ("applicant_income", "loan_amount", "credit_score", "dti_ratio")
        ]
        numeric_fields = [f for f in numeric_fields if f in df.columns]

        if not numeric_fields:
            return {"target": target.to_dict(), "similar_applicants": [], "comparison": {}}

        rest = df[df[id_col].astype(str) != str(applicant_id)].copy()
        numeric_df = rest[numeric_fields].apply(pd.to_numeric, errors="coerce").fillna(0)
        target_vec = pd.to_numeric(
            pd.Series({f: target.get(f, 0) for f in numeric_fields}), errors="coerce"
        ).fillna(0).values

        norms = numeric_df.values.copy().astype(float)
        for j in range(norms.shape[1]):
            rng = norms[:, j].max() - norms[:, j].min()
            if rng > 0:
                norms[:, j] = (norms[:, j] - norms[:, j].min()) / rng
                target_vec[j] = (target_vec[j] - numeric_df.iloc[:, j].min()) / rng

        distances = np.linalg.norm(norms - target_vec, axis=1)
        closest_idx = np.argsort(distances)[:top_k]
        similar = rest.iloc[closest_idx]

        outcome_col = self._detect_outcome_col(df, field_map)
        comparison = {}
        if outcome_col:
            comparison = {
                "target_decision": str(target.get(outcome_col, "unknown")),
                "comparator_decision_distribution": similar[outcome_col].astype(str).value_counts().to_dict(),
            }

        return {
            "target": target.to_dict(),
            "similar_applicants": similar.to_dict(orient="records"),
            "comparison": comparison,
        }

    # ------------------------------------------------------------------
    # Bias Indicators
    # ------------------------------------------------------------------

    def detect_bias_indicators(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
        protected_columns: Optional[Dict[str, str]] = None,
    ) -> List[BiasIndicator]:
        indicators: List[BiasIndicator] = []
        outcome_col = self._detect_outcome_col(df, field_map)
        if not outcome_col:
            return indicators

        threshold = Config.DISPARATE_IMPACT_THRESHOLD
        cols_to_check = protected_columns or self._detect_all_protected_cols(df, field_map)

        for field_name, col in cols_to_check.items():
            if col not in df.columns:
                continue
            group_rates = self.compute_approval_rates_by_group(
                df, col, outcome_col, field_name=field_name
            )
            if len(group_rates) < 2:
                continue

            max_rate = max(group_rates.values())
            if max_rate == 0:
                continue

            for group, rate in group_rates.items():
                di_ratio = rate / max_rate

                severity = None
                if di_ratio < SEVERITY_LEVELS["critical"]:
                    severity = "critical"
                elif di_ratio < SEVERITY_LEVELS["high"]:
                    severity = "high"
                elif di_ratio < SEVERITY_LEVELS["medium"]:
                    severity = "medium"

                if severity:
                    indicators.append(BiasIndicator(
                        field=field_name,
                        group=str(group),
                        value=round(di_ratio, 4),
                        threshold=threshold,
                        description=(
                            f"{field_name.capitalize()} group '{group}' approval rate: "
                            f"{rate:.1%} — DI ratio: {di_ratio:.2%} "
                            f"(4/5ths threshold: {threshold:.0%})"
                        ),
                        severity=severity,
                    ))

        return indicators

    # ------------------------------------------------------------------
    # Fairness Score
    # ------------------------------------------------------------------

    def compute_fairness_score(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
        protected_columns: Optional[Dict[str, str]] = None,
    ) -> float:
        indicators = self.detect_bias_indicators(df, field_map, protected_columns)
        penalties = {"critical": 30, "high": 20, "medium": 10}
        total_penalty = sum(penalties.get(ind.severity, 0) for ind in indicators)
        return round(max(0.0, 100.0 - total_penalty), 2)

    # ------------------------------------------------------------------
    # Full Audit
    # ------------------------------------------------------------------

    def generate_audit(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
        dataset_id: Optional[str] = None,
        protected_columns: Optional[Dict[str, str]] = None,
        outcome_column: Optional[str] = None,
        approval_values: Optional[List[str]] = None,
    ) -> FairnessReport:
        if dataset_id is None:
            dataset_id = str(uuid.uuid4())

        # Apply code translations (HMDA numeric → labels)
        df, meta = _profiler.prepare_for_analysis(df, apply_translations=True, sample=True)
        dataset_type = meta["dataset_type"]

        outcome_col = outcome_column or self._detect_outcome_col(df, field_map)
        cols_to_check = protected_columns or self._detect_all_protected_cols(df, field_map)

        di_ratios: Dict[str, float] = {}
        approval_rates_by_group: Dict[str, Dict[str, float]] = {}

        # Filter to only decisive outcomes (Approved/Denied) for accurate DI analysis
        # Withdrawn/Incomplete applications are excluded as they were not actually decided
        decisive_vals = {"approved", "denied", "originated", "loan originated",
                         "approved but not accepted", "preapproval approved", "preapproval denied",
                         "1", "2", "3", "7", "8"}
        if outcome_col and outcome_col in df.columns:
            df_decisive = df[df[outcome_col].astype(str).str.strip().str.lower().isin(decisive_vals)].copy()
            if len(df_decisive) < 10:
                # Not enough decisive outcomes — fall back to full dataset
                df_decisive = df
        else:
            df_decisive = df

        for field_name, col in cols_to_check.items():
            if col not in df_decisive.columns or outcome_col is None:
                continue
            di_ratios[field_name] = self.analyze_disparate_impact(df_decisive, col, outcome_col)
            approval_rates_by_group[field_name] = self.compute_approval_rates_by_group(
                df_decisive, col, outcome_col, field_name=field_name
            )

        indicators = self.detect_bias_indicators(df_decisive, field_map, cols_to_check)
        score = self.compute_fairness_score(df_decisive, field_map, cols_to_check)

        threshold = Config.DISPARATE_IMPACT_THRESHOLD
        findings: List[str] = []

        if meta.get("was_sampled"):
            findings.append(
                f"Dataset sampled: analyzed {meta['analysis_rows']:,} of "
                f"{meta['original_rows']:,} rows for performance."
            )

        findings.append(f"Dataset type detected: {dataset_type.replace('_', ' ').title()}.")

        if not di_ratios:
            findings.append("No demographic columns found for disparate impact analysis.")
            findings.append(
                "Upload a dataset with race, sex/gender, or age columns for full fair lending analysis."
            )
        else:
            for field, ratio in di_ratios.items():
                ar = approval_rates_by_group.get(field, {})
                groups_str = ", ".join(f"{g}: {r:.1%}" for g, r in ar.items())
                if ratio < threshold:
                    findings.append(
                        f"⚠ {field.capitalize()}: DI ratio {ratio:.2%} below {threshold:.0%} threshold. "
                        f"Approval rates — {groups_str}."
                    )
                else:
                    findings.append(
                        f"✓ {field.capitalize()}: DI ratio {ratio:.2%} — within acceptable range. "
                        f"Approval rates — {groups_str}."
                    )

        if score >= 80:
            findings.append(f"Overall fairness score: {score:.1f}/100 — ACCEPTABLE.")
        elif score >= 60:
            findings.append(f"Overall fairness score: {score:.1f}/100 — NEEDS ATTENTION.")
        else:
            findings.append(f"Overall fairness score: {score:.1f}/100 — HIGH RISK.")

        recommendations: List[str] = []
        if any(r < threshold for r in di_ratios.values()):
            recommendations += [
                "Conduct a comparative file analysis for affected demographic groups.",
                "Review underwriting criteria for potential disparate-impact proxies (zip code, LTV, etc.).",
                "Consider targeted outreach programs in underserved communities.",
                "Consult a fair lending attorney regarding ECOA and FHA obligations.",
            ]
        if indicators:
            recommendations += [
                "Engage a third-party fair lending consultant to review flagged indicators.",
                "Update fair lending training for loan officers and underwriters.",
            ]
        if not di_ratios:
            recommendations.append(
                "Add demographic data (race, sex, age) to enable full disparate impact analysis."
            )

        recommendations += [
            "Schedule quarterly automated fairness audits using this platform.",
            "Document all underwriting overrides with explicit business justification.",
        ]

        return FairnessReport(
            dataset_id=dataset_id,
            score=score,
            disparate_impact_ratios=di_ratios,
            approval_rates_by_group=approval_rates_by_group,
            bias_indicators=indicators,
            findings=findings,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # AI-Powered Fairness Explanation
    # ------------------------------------------------------------------

    def generate_ai_explanation(self, report: FairnessReport) -> str:
        """
        Send the fairness report to the configured LLM (Gemini or OpenAI)
        and get a plain-English compliance-focused explanation.
        Returns the AI explanation string, or a fallback message if no key configured.
        """
        from backend.core.ai_provider import call_llm

        # Build a concise summary of the report for the prompt
        di_lines = "\n".join(
            f"  - {field.capitalize()}: DI ratio = {ratio:.2%} ({'FAIL' if ratio < Config.DISPARATE_IMPACT_THRESHOLD else 'PASS'})"
            for field, ratio in (report.disparate_impact_ratios or {}).items()
        ) or "  - No demographic data available for DI analysis."

        ar_lines = []
        for field, rates in (report.approval_rates_by_group or {}).items():
            for group, rate in rates.items():
                ar_lines.append(f"  - {field.capitalize()} / {group}: {rate:.1%} approval rate")
        ar_text = "\n".join(ar_lines) or "  - No approval rate data available."

        bias_lines = "\n".join(
            f"  - [{ind.severity.upper()}] {ind.field} group '{ind.group}': DI ratio {ind.value:.2%}"
            for ind in (report.bias_indicators or [])
        ) or "  - No bias indicators flagged."

        prompt = f"""You are a senior fair lending compliance officer and AI analyst.

A statistical fairness audit has been completed on a lending dataset. Your task is to:
1. Explain the findings in plain English for both legal and business audiences
2. Identify the most significant fair lending risks under ECOA and the Fair Housing Act
3. Provide 3-5 specific, actionable AI-driven recommendations
4. Flag any patterns that may indicate systemic or algorithmic bias
5. Suggest what additional data or analysis would improve the fairness assessment

AUDIT RESULTS:
- Dataset ID: {report.dataset_id}
- Overall Fairness Score: {report.score:.1f}/100
- Total Bias Indicators Flagged: {len(report.bias_indicators or [])}

DISPARATE IMPACT RATIOS (4/5ths rule threshold: 80%):
{di_lines}

APPROVAL RATES BY DEMOGRAPHIC GROUP:
{ar_text}

BIAS INDICATORS FLAGGED:
{bias_lines}

STATISTICAL FINDINGS:
{chr(10).join(f'  - {f}' for f in (report.findings or []))}

Please provide a comprehensive AI-powered fair lending analysis. Be specific, cite the numbers, and explain what they mean legally and operationally. Format your response with clear sections: Executive Summary, Key Risks, Detailed Analysis, AI Recommendations, and Data Gaps."""

        try:
            return call_llm(prompt, max_tokens=2048, temperature=0.3)
        except ValueError as e:
            return f"AI analysis unavailable: {e}"
        except Exception as e:
            return f"AI analysis error: {e}"
