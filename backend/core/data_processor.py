"""
Data Processor – cleans, standardises, and validates lending datasets.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.models.schemas import ProcessingReport


# Decision value normalisation map
DECISION_NORMALISATION: Dict[str, str] = {
    # HMDA action_taken numeric codes
    "1": "Approved",   # Loan Originated
    "2": "Approved",   # Approved, Not Accepted
    "3": "Denied",
    "4": "Withdrawn",
    "5": "Incomplete",
    "6": "Purchased",
    "7": "Denied",     # Preapproval Denied
    "8": "Approved",   # Preapproval Approved
    # German credit (0 = good/approved, 1 = bad/denied)
    "0": "Approved",
    # Text: Approved
    "approved": "Approved",
    "approve": "Approved",
    "originated": "Approved",
    "loan originated": "Approved",
    "accepted": "Approved",
    "funded": "Approved",
    "closed": "Approved",
    "approved but not accepted": "Approved",
    "preapproval approved": "Approved",
    # Text: Denied
    "denied": "Denied",
    "deny": "Denied",
    "rejected": "Denied",
    "declined": "Denied",
    "application denied": "Denied",
    "turned down": "Denied",
    "preapproval denied": "Denied",
    # Withdrawn
    "withdrawn": "Withdrawn",
    "withdrew": "Withdrawn",
    "application withdrawn": "Withdrawn",
    "voluntarily withdrawn": "Withdrawn",
    # Incomplete
    "incomplete": "Incomplete",
    "closed for incompleteness": "Incomplete",
    "file closed": "Incomplete",
    "incomplete application": "Incomplete",
    # Purchased
    "purchased": "Purchased",
    "loan purchased": "Purchased",
}


class DataProcessor:
    """Profiles, cleans, and validates lending DataFrames."""

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def profile_data(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Return per-column statistics:
        dtype, missing_count, missing_pct, unique_count, sample_values,
        min, max, mean (numeric only).
        """
        profile: Dict[str, Dict[str, Any]] = {}
        total = len(df)

        for col in df.columns:
            series = df[col]
            missing = int(series.isna().sum())
            unique = int(series.nunique(dropna=True))
            samples = series.dropna().unique()[:5].tolist()

            stat: Dict[str, Any] = {
                "dtype": str(series.dtype),
                "missing_count": missing,
                "missing_pct": round(missing / total * 100, 2) if total else 0,
                "unique_count": unique,
                "sample_values": [str(s) for s in samples],
            }

            if pd.api.types.is_numeric_dtype(series):
                stat["min"] = float(series.min()) if not series.isna().all() else None
                stat["max"] = float(series.max()) if not series.isna().all() else None
                stat["mean"] = float(series.mean()) if not series.isna().all() else None
                stat["median"] = float(series.median()) if not series.isna().all() else None
                stat["std"] = float(series.std()) if not series.isna().all() else None

            profile[col] = stat

        return profile

    # ------------------------------------------------------------------
    # Clean
    # ------------------------------------------------------------------

    def clean_data(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        - Remove exact duplicate rows.
        - Fill missing values:
            * numeric  → median of column
            * object   → mode, or "Unknown" if no mode
            * datetime → forward fill
        Returns a clean copy.
        """
        df = df.copy()
        df = df.drop_duplicates()

        for col in df.columns:
            series = df[col]
            if series.isna().sum() == 0:
                continue

            if pd.api.types.is_numeric_dtype(series):
                fill_val = series.median()
                if pd.isna(fill_val):
                    fill_val = 0.0
                df[col] = series.fillna(fill_val)

            elif pd.api.types.is_datetime64_any_dtype(series):
                df[col] = series.ffill().bfill()

            else:  # object / categorical
                mode_vals = series.mode(dropna=True)
                fill_val = mode_vals.iloc[0] if len(mode_vals) > 0 else "Unknown"
                df[col] = series.fillna(fill_val)

        return df

    # ------------------------------------------------------------------
    # Standardise categoricals
    # ------------------------------------------------------------------

    def standardize_categoricals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardise decision / outcome columns to canonical values:
        Approved | Denied | Withdrawn | Incomplete | Purchased
        Works on any column whose canonical name is 'decision'.
        """
        df = df.copy()

        # Detect decision column (canonical name or common names)
        candidate_cols = [
            c for c in df.columns
            if any(
                kw in c.lower()
                for kw in ("decision", "action_taken", "action", "outcome",
                           "status", "disposition", "default", "credit_risk",
                           "class", "target")
            )
        ]

        for col in candidate_cols:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .map(lambda v: DECISION_NORMALISATION.get(v, v.capitalize()))
            )

        return df

    # ------------------------------------------------------------------
    # Quality Validation
    # ------------------------------------------------------------------

    def validate_quality(self, df: pd.DataFrame) -> float:
        """
        Compute a quality score 0–100 based on:
        - Completeness  (50 pts): fraction of non-missing cells
        - Consistency   (30 pts): numeric columns within 3 std-devs
        - Uniqueness    (20 pts): fraction of non-duplicate rows
        """
        if df.empty:
            return 0.0

        total_cells = df.size
        missing_cells = int(df.isna().sum().sum())
        completeness_score = (1 - missing_cells / total_cells) * 50 if total_cells else 0

        # Consistency: count rows with ANY extreme outlier
        outlier_rows = set()
        for col in df.select_dtypes(include=[np.number]).columns:
            s = df[col].dropna()
            if len(s) < 4:
                continue
            mean, std = s.mean(), s.std()
            if std == 0:
                continue
            mask = ((df[col] - mean).abs() > 3 * std)
            outlier_rows.update(df[mask].index.tolist())

        consistency_score = (1 - len(outlier_rows) / len(df)) * 30

        # Uniqueness
        dup_count = int(df.duplicated().sum())
        uniqueness_score = (1 - dup_count / len(df)) * 20

        total = round(completeness_score + consistency_score + uniqueness_score, 2)
        return min(max(total, 0.0), 100.0)

    # ------------------------------------------------------------------
    # Generate Report
    # ------------------------------------------------------------------

    def generate_report(
        self,
        df_before: pd.DataFrame,
        df_after: pd.DataFrame,
        processing_time: float = 0.0,
    ) -> ProcessingReport:
        """Compare before/after DataFrames and build a ProcessingReport."""
        duplicates_removed = len(df_before) - len(df_after)
        if duplicates_removed < 0:
            duplicates_removed = 0

        # Missing values per column (before vs after)
        missing_before = df_before.isna().sum().to_dict()
        missing_after = df_after.isna().sum().to_dict()
        missing_filled: Dict[str, int] = {
            col: int(missing_before.get(col, 0) - missing_after.get(col, 0))
            for col in df_before.columns
            if missing_before.get(col, 0) > 0
        }

        quality_score = self.validate_quality(df_after)

        standardizations: List[str] = []
        # Check if any decision-like column was modified
        for col in df_after.columns:
            if "decision" in col.lower() or "action_taken" in col.lower():
                standardizations.append(f"Standardised decision values in column '{col}'")

        return ProcessingReport(
            original_rows=len(df_before),
            final_rows=len(df_after),
            duplicates_removed=duplicates_removed,
            missing_values=missing_filled,
            quality_score=quality_score,
            standardizations_applied=standardizations,
            processing_time_seconds=round(processing_time, 3),
        )

    # ------------------------------------------------------------------
    # Convenience: run full pipeline
    # ------------------------------------------------------------------

    def process(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> tuple[pd.DataFrame, ProcessingReport]:
        """Run the full cleaning pipeline and return (clean_df, report)."""
        t0 = time.time()
        df_clean = self.clean_data(df, field_map)
        df_clean = self.standardize_categoricals(df_clean)
        elapsed = time.time() - t0
        report = self.generate_report(df, df_clean, elapsed)
        return df_clean, report
