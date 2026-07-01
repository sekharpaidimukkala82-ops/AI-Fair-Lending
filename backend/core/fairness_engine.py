"""
Fairness Engine – disparate impact analysis, bias detection, and fair lending auditing.

Designed to work with ANY tabular dataset — not just HMDA.
Auto-detects outcome columns and demographic columns using broad heuristics.
Supports: HMDA, German Credit, Lending Club, Fannie/Freddie, and any generic CSV.
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
# Generic column detection patterns — broad enough for any dataset
# ---------------------------------------------------------------------------

# Protected class patterns: ordered by priority (exact → partial)
PROTECTED_CLASS_PATTERNS: Dict[str, List[str]] = {
    "race": [
        # HMDA official
        "applicant_race_1", "derived_race", "applicant_race", "race_1",
        "co_applicant_race_1", "applicant_race_name_1",
        # Generic
        "race", "ethnicity", "racial_group", "minority_status",
        "borrower_race", "race_ethnicity", "demographic_race",
    ],
    "gender": [
        # HMDA official
        "applicant_sex", "derived_sex", "co_applicant_sex", "applicant_sex_name",
        # Generic
        "sex", "gender", "borrower_sex", "borrower_gender",
        "personal_status_sex", "personal_status", "applicant_gender",
    ],
    "ethnicity": [
        "applicant_ethnicity_1", "derived_ethnicity", "applicant_ethnicity_name_1",
        "ethnicity", "hispanic", "national_origin",
    ],
    "age": [
        "applicant_age", "borrower_age", "age", "age_group",
        "age_bracket", "applicant_age_above_62", "age_band",
    ],
}

# Backward-compatible flat list
PROTECTED_CLASSES = list(PROTECTED_CLASS_PATTERNS.keys())

# Outcome column patterns — any of these signal a decision/approval column
OUTCOME_PATTERNS: List[str] = [
    # Exact names
    "action_taken", "decision", "loan_status", "default", "outcome",
    "class", "target", "label", "y", "credit_risk", "approval_status",
    "application_status", "action_taken_name", "loan_decision",
    "approved", "status", "result", "approved_denied", "pass_fail",
    "credit_decision", "underwriting_decision", "final_decision",
    # Partial keywords (checked as substrings)
]
OUTCOME_KEYWORDS = [
    "action_taken", "decision", "outcome", "default", "loan_status",
    "target", "label", "approved", "denied", "status", "result",
    "credit_risk", "pass_fail",
]

SEVERITY_LEVELS = {
    "critical": 0.60,
    "high":     0.70,
    "medium":   0.80,
}

# Values that indicate "not available" for a demographic field — skip these groups
UNKNOWN_VALUES = {
    "not provided", "not applicable", "no co-applicant",
    "information not provided", "free form text only",
    "race not available", "sex not available", "ethnicity not available",
    "nan", "none", "", "na", "n/a", "unknown", "other",
    "6", "7", "8",       # HMDA not-provided codes
    "8888", "9999",      # HMDA age not-applicable codes
    "exempt",            # HMDA exempt institutions
}

_profiler = DatasetProfiler()


class FairnessEngine:
    """
    Generic fair lending auditor.
    Works with any CSV — auto-detects outcome and demographic columns.
    """

    # ------------------------------------------------------------------
    # Outcome column detection
    # ------------------------------------------------------------------

    def _detect_outcome_col(
        self, df: pd.DataFrame, field_map: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Find the outcome/decision column in any dataset.
        Strategy:
        1. Use field_map if provided
        2. Exact name match against known patterns (validated)
        3. Partial keyword match (validated)
        4. Heuristic: binary/low-cardinality column with approval-like values
        A column is only accepted if it actually contains approval/denial signals.
        """
        if field_map and "decision" in field_map:
            col = field_map["decision"]
            if col in df.columns:
                return col

        # Columns to skip — these are never outcomes
        SKIP_COLS = {
            "activity_year", "year", "census_tract", "tract", "lei",
            "respondent_id", "sequence_number", "id", "msa_md",
            "state_code", "county_code", "zip_code", "loan_id",
            "application_date", "date",
        }

        approval_signals = {
            "approved", "originated", "funded", "yes", "true", "pass",
            "denied", "rejected", "declined", "no", "false", "fail",
            "1", "0",  # binary only if other signals present
        }
        hmda_outcome_vals = {"1", "2", "3", "4", "5", "6", "7", "8"}

        def _col_has_outcome_values(col: str) -> bool:
            """Return True if this column contains approval/denial-like values."""
            cl = col.lower().strip()
            if cl in SKIP_COLS:
                return False
            vals = set(df[col].dropna().astype(str).str.strip().str.lower().unique())
            if not vals:
                return False
            # HMDA action_taken codes: must include both approvals (1/2/8) and denials (3/7)
            if vals.issubset(hmda_outcome_vals):
                return bool(vals & {"1", "2", "8"}) and bool(vals & {"3", "7"})
            # Text signals: must include at least one approval AND one denial word
            approvals = {"approved", "originated", "funded", "yes", "true", "pass", "1"}
            denials = {"denied", "rejected", "declined", "no", "false", "fail", "0"}
            has_approval = bool(vals & approvals)
            has_denial = bool(vals & denials)
            return has_approval and has_denial

        cols_lower = {c: c.lower().strip() for c in df.columns}

        # Exact name match — validated
        for col, cl in cols_lower.items():
            if cl in OUTCOME_PATTERNS and _col_has_outcome_values(col):
                return col

        # Partial keyword match — validated
        for col, cl in cols_lower.items():
            if cl in SKIP_COLS:
                continue
            if any(kw in cl for kw in OUTCOME_KEYWORDS) and _col_has_outcome_values(col):
                return col

        # Heuristic: low-cardinality column with approval/denial signals
        for col in df.columns:
            cl = col.lower().strip()
            if cl in SKIP_COLS:
                continue
            vals = df[col].dropna().astype(str).str.strip().str.lower().unique()
            if 2 <= len(vals) <= 10 and _col_has_outcome_values(col):
                return col

        return None

    # ------------------------------------------------------------------
    # Protected class column detection
    # ------------------------------------------------------------------

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
        cols_lower = {c: c.lower().strip() for c in df.columns}

        # Exact match
        for pat in patterns:
            for col, cl in cols_lower.items():
                if cl == pat.lower():
                    return col

        # Substring match
        for pat in patterns:
            for col, cl in cols_lower.items():
                if pat.lower() in cl:
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
    # Approval detection — generic for any dataset
    # ------------------------------------------------------------------

    def _is_approval(self, value: Any) -> bool:
        """
        Determine if a value represents an approval/positive outcome.
        Works for: HMDA codes, text values, binary 0/1, True/False, Pass/Fail.
        """
        v = str(value).strip().lower()

        # HMDA numeric codes
        if v in HMDA_APPROVAL_CODES:
            return True
        if v in HMDA_DENIAL_CODES:
            return False

        # Binary numeric
        if v in ("1", "1.0"):
            return True
        if v in ("0", "0.0"):
            return False

        # Boolean
        if v in ("true", "yes", "y", "pass", "passed"):
            return True
        if v in ("false", "no", "n", "fail", "failed"):
            return False

        # Text approval signals
        approval_vals = {
            "approved", "originated", "loan originated",
            "approved but not accepted", "funded", "preapproval approved",
            "approve", "accepted", "closed", "good",
            "current", "fully paid", "does not meet credit policy. status:fully paid",
        }
        if v in approval_vals:
            return True

        # Text denial signals
        denial_vals = {
            "denied", "deny", "rejected", "declined",
            "application denied", "preapproval denied",
            "charged off", "default", "late (31-120 days)",
            "does not meet credit policy. status:charged off",
        }
        if v in denial_vals:
            return False

        return False

    def _approval_rate(self, series: pd.Series) -> float:
        if len(series) == 0:
            return 0.0
        return series.apply(self._is_approval).sum() / len(series)

    # ------------------------------------------------------------------
    # Outcome column binary check — validate it has both approvals & denials
    # ------------------------------------------------------------------

    def _validate_outcome_col(self, df: pd.DataFrame, outcome_col: str) -> bool:
        """Return True if column has at least some approvals AND some denials."""
        if outcome_col not in df.columns:
            return False
        approved = df[outcome_col].apply(self._is_approval).sum()
        total = len(df[outcome_col].dropna())
        if total == 0:
            return False
        # Need at least 5% approvals and 5% denials
        rate = approved / total
        return 0.05 <= rate <= 0.95

    # ------------------------------------------------------------------
    # Age bucketing — convert raw ages to meaningful brackets
    # ------------------------------------------------------------------

    def _bucket_age(self, series: pd.Series) -> pd.Series:
        """Convert numeric age values into age brackets for group analysis."""
        # If already bucketed (e.g. HMDA uses '<25', '25-34', '>74'), pass through
        sample = series.dropna().astype(str).str.strip()
        already_bucketed = sample.str.match(r'^[<>]?\d+(-\d+)?$').mean() < 0.5
        if already_bucketed:
            return sample

        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() < len(series) * 0.3:
            # Not mostly numeric — return as-is
            return series.astype(str).str.strip()

        def _bracket(age):
            if pd.isna(age):
                return "Unknown"
            age = float(age)
            # HMDA special codes
            if age >= 8000:
                return "Unknown"
            age = int(age)
            if age < 25:    return "<25"
            if age < 35:    return "25-34"
            if age < 45:    return "35-44"
            if age < 55:    return "45-54"
            if age < 65:    return "55-64"
            if age < 75:    return "65-74"
            return ">74"

        return numeric.map(_bracket)

    # ------------------------------------------------------------------
    # Group normalization
    # ------------------------------------------------------------------

    def _normalize_group_values(self, series: pd.Series, field_name: str) -> pd.Series:
        """
        Normalize demographic column values for consistent grouping.
        Works for any dataset format.
        """
        s = series.astype(str).str.strip()

        if field_name == "age":
            return self._bucket_age(s)

        if field_name in ("gender", "sex"):
            s = _profiler.normalize_gender_col(s)
        elif field_name in ("race", "ethnicity"):
            s = _profiler.normalize_race_col(s)
        else:
            # Generic: extract first part of compound values like 'male : single'
            if s.str.contains(" : ", na=False).any():
                s = s.str.split(" : ").str[0].str.strip()
            s = s.str.title()

        # Map all "unknown/not provided" variants to "Unknown"
        s = s.map(lambda v: "Unknown" if v.lower() in UNKNOWN_VALUES else v)
        return s

    def _normalize_group_col(self, df: pd.DataFrame, col: str) -> pd.Series:
        """Backward-compatible wrapper."""
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

        field_name = "gender" if any(
            kw in protected_col.lower() for kw in ["sex", "gender"]
        ) else ("age" if "age" in protected_col.lower() else "race")

        group_rates = self.compute_approval_rates_by_group(
            df, protected_col, outcome_col, field_name=field_name
        )
        rates = [v for v in group_rates.values() if v is not None and not pd.isna(v)]

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
            grp_str = str(grp_val)
            # Skip unknown/not-provided groups
            if grp_str == "Unknown" or grp_str.lower() in UNKNOWN_VALUES:
                continue
            # Need at least 5 records for a meaningful rate
            if len(grp_df) < 5:
                continue
            rate = self._approval_rate(grp_df[outcome_col])
            rates[grp_str] = round(rate, 4)

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
        else:
            for col in df.columns:
                if "id" in col.lower():
                    id_col = col
                    break

        if id_col is None:
            return {"error": "No ID column found."}

        match = df[df[id_col].astype(str) == str(applicant_id)]
        if match.empty:
            return {"error": f"Applicant {applicant_id} not found."}

        target = match.iloc[0]
        # Auto-detect numeric financial fields
        numeric_fields = [
            c for c in df.columns
            if pd.api.types.is_numeric_dtype(df[c])
            and c != id_col
            and any(kw in c.lower() for kw in ["income", "loan", "amount", "score", "dti", "rate", "credit"])
        ]

        if not numeric_fields:
            numeric_fields = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != id_col][:5]

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

        # Filter neutral/non-decisive outcomes
        NEUTRAL_OUTCOMES = {
            "withdrawn", "incomplete", "purchased", "file closed",
            "closed for incompleteness", "application withdrawn",
            "voluntarily withdrawn", "4", "5", "6",
            "current", "in grace period",  # Lending Club non-decisive
        }
        if outcome_col in df.columns:
            mask = ~df[outcome_col].astype(str).str.strip().str.lower().isin(NEUTRAL_OUTCOMES)
            df_work = df[mask] if mask.sum() >= 10 else df
        else:
            df_work = df

        threshold = Config.DISPARATE_IMPACT_THRESHOLD
        cols_to_check = protected_columns or self._detect_all_protected_cols(df_work, field_map)

        for field_name, col in cols_to_check.items():
            if col not in df_work.columns:
                continue
            group_rates = self.compute_approval_rates_by_group(
                df_work, col, outcome_col, field_name=field_name
            )
            # Need at least 2 valid groups with different rates to flag bias
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

        # Apply code translations (HMDA numeric → labels) and sample if large
        df, meta = _profiler.prepare_for_analysis(df, apply_translations=True, sample=True)
        dataset_type = meta["dataset_type"]

        outcome_col = outcome_column or self._detect_outcome_col(df, field_map)
        cols_to_check = protected_columns or self._detect_all_protected_cols(df, field_map)

        # Filter to only decisive outcomes (Approved/Denied)
        NEUTRAL_OUTCOMES = {
            "withdrawn", "incomplete", "purchased", "file closed",
            "closed for incompleteness", "application withdrawn",
            "voluntarily withdrawn", "4", "5", "6",
            "current", "in grace period",
        }
        df_decisive = df
        if outcome_col and outcome_col in df.columns:
            mask = ~df[outcome_col].astype(str).str.strip().str.lower().isin(NEUTRAL_OUTCOMES)
            df_filtered = df[mask]
            if len(df_filtered) >= 10:
                df_decisive = df_filtered

        di_ratios: Dict[str, float] = {}
        approval_rates_by_group: Dict[str, Dict[str, float]] = {}

        for field_name, col in cols_to_check.items():
            if col not in df_decisive.columns or outcome_col is None:
                continue
            rates = self.compute_approval_rates_by_group(
                df_decisive, col, outcome_col, field_name=field_name
            )
            # Only include fields where we have 2+ meaningful groups
            if len(rates) >= 2:
                di_ratios[field_name] = self.analyze_disparate_impact(df_decisive, col, outcome_col)
                approval_rates_by_group[field_name] = rates

        indicators = self.detect_bias_indicators(df_decisive, field_map, cols_to_check)
        score = self.compute_fairness_score(df_decisive, field_map, cols_to_check)

        threshold = Config.DISPARATE_IMPACT_THRESHOLD
        findings: List[str] = []

        if meta.get("was_sampled"):
            findings.append(
                f"Dataset sampled: analyzed {meta['analysis_rows']:,} of "
                f"{meta['original_rows']:,} rows for performance."
            )

        findings.append(f"Dataset type: {dataset_type.replace('_', ' ').title()}.")

        if outcome_col:
            findings.append(f"Outcome column used: '{outcome_col}'.")
        else:
            findings.append("No outcome/decision column detected in this dataset.")

        if not di_ratios:
            findings.append("No demographic columns with sufficient data found for disparate impact analysis.")
            findings.append(
                "For full fair lending analysis, ensure your dataset has columns for "
                "race, sex/gender, or age, and an outcome/decision column."
            )
        else:
            for field, ratio in di_ratios.items():
                ar = approval_rates_by_group.get(field, {})
                groups_str = ", ".join(f"{g}: {r:.1%}" for g, r in sorted(ar.items()))
                if ratio < threshold:
                    findings.append(
                        f"⚠ {field.capitalize()}: DI ratio {ratio:.2%} — BELOW {threshold:.0%} threshold. "
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
        from backend.core.ai_provider import call_llm

        di_lines = "\n".join(
            f"  - {field.capitalize()}: DI ratio = {ratio:.2%} "
            f"({'FAIL' if ratio < Config.DISPARATE_IMPACT_THRESHOLD else 'PASS'})"
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

Please provide a comprehensive AI-powered fair lending analysis with sections:
Executive Summary, Key Risks, Detailed Analysis, AI Recommendations, and Data Gaps."""

        try:
            return call_llm(prompt, max_tokens=2048, temperature=0.3)
        except ValueError as e:
            return f"AI analysis unavailable: {e}"
        except Exception as e:
            return f"AI analysis error: {e}"
