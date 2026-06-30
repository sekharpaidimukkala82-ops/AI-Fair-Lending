"""
Dataset Profiler – detects dataset type, applies HMDA code mappings,
and handles large files via chunked processing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# HMDA Official Code Mappings (FFIEC/CFPB LAR format)
# ---------------------------------------------------------------------------

HMDA_ACTION_TAKEN_CODES: Dict[str, str] = {
    "1": "Originated",
    "2": "Approved Not Accepted",
    "3": "Denied",
    "4": "Withdrawn",
    "5": "Incomplete",
    "6": "Purchased",
    "7": "Preapproval Denied",
    "8": "Preapproval Approved",
}

HMDA_RACE_CODES: Dict[str, str] = {
    "1": "American Indian/Alaska Native",
    "2": "Asian",
    "3": "Black or African American",
    "4": "Native Hawaiian/Pacific Islander",
    "5": "White",
    "6": "Not Provided",
    "7": "Not Applicable",
    "8": "No Co-Applicant",
}

HMDA_SEX_CODES: Dict[str, str] = {
    "1": "Male",
    "2": "Female",
    "3": "Not Provided",
    "4": "Not Applicable",
    "5": "No Co-Applicant",
    "6": "Both",
}

HMDA_ETHNICITY_CODES: Dict[str, str] = {
    "1": "Hispanic or Latino",
    "2": "Not Hispanic or Latino",
    "3": "Not Provided",
    "4": "Not Applicable",
    "5": "No Co-Applicant",
}

HMDA_LOAN_TYPE_CODES: Dict[str, str] = {
    "1": "Conventional",
    "2": "FHA",
    "3": "VA",
    "4": "FSA/RHS",
}

HMDA_LOAN_PURPOSE_CODES: Dict[str, str] = {
    "1": "Purchase",
    "2": "Improvement",
    "31": "Refinancing",
    "32": "Cash-Out Refinancing",
    "4": "Other Purpose",
    "5": "Not Applicable",
}

HMDA_PROPERTY_TYPE_CODES: Dict[str, str] = {
    "1": "Single Family",
    "2": "Manufactured Housing",
    "3": "Multifamily",
}

HMDA_LIEN_STATUS_CODES: Dict[str, str] = {
    "1": "First Lien",
    "2": "Subordinate Lien",
}

HMDA_DENIAL_REASON_CODES: Dict[str, str] = {
    "1": "Debt-to-Income Ratio",
    "2": "Employment History",
    "3": "Credit History",
    "4": "Collateral",
    "5": "Insufficient Cash",
    "6": "Unverifiable Information",
    "7": "Credit Application Incomplete",
    "8": "Mortgage Insurance Denied",
    "9": "Other",
    "10": "Not Applicable",
}

# HMDA approval/denial sets by action_taken code
HMDA_APPROVAL_CODES = {"1", "2", "8"}   # originated, approved, preapproval approved
HMDA_DENIAL_CODES   = {"3", "7"}        # denied, preapproval denied


# ---------------------------------------------------------------------------
# Code application maps: column_name_pattern -> code_dict
# ---------------------------------------------------------------------------

COLUMN_CODE_MAPS: List[Tuple[List[str], Dict[str, str]]] = [
    (["action_taken", "loan_decision", "decision_code"], HMDA_ACTION_TAKEN_CODES),
    (["applicant_race", "race_1", "co_applicant_race"], HMDA_RACE_CODES),
    (["applicant_sex", "sex", "co_applicant_sex", "derived_sex"], HMDA_SEX_CODES),
    (["applicant_ethnicity", "ethnicity", "co_applicant_ethnicity", "derived_ethnicity"], HMDA_ETHNICITY_CODES),
    (["loan_type"], HMDA_LOAN_TYPE_CODES),
    (["loan_purpose"], HMDA_LOAN_PURPOSE_CODES),
    (["property_type"], HMDA_PROPERTY_TYPE_CODES),
    (["lien_status"], HMDA_LIEN_STATUS_CODES),
    (["denial_reason"], HMDA_DENIAL_REASON_CODES),
]


# ---------------------------------------------------------------------------
# Dataset Type Detection
# ---------------------------------------------------------------------------

DATASET_SIGNATURES: Dict[str, List[str]] = {
    "hmda_official":     ["action_taken", "applicant_race_1", "applicant_sex", "lei"],
    "hmda_legacy":       ["loan_amount_000s", "applicant_income_000s", "hud_median_family_income"],
    "hmda_derived":      ["derived_race", "derived_sex", "action_taken_name"],
    "german_credit":     ["personal_status_sex", "account_check_status", "credit_history"],
    "lending_club":      ["loan_status", "int_rate", "emp_length", "grade"],
    "fannie_mae":        ["fico_range_low", "orig_upb", "prop_type"],
    "freddie_mac":       ["original_upb", "original_interest_rate", "channel"],
    "hmda_lar_2018":     ["activity_year", "lei", "derived_msa", "conforming_loan_limit"],
}


class DatasetProfiler:
    """
    Detects dataset format, applies HMDA numeric code translations,
    and provides chunked reading for large files.
    """

    SAMPLE_SIZE = 100_000   # max rows for fairness analysis sampling
    CHUNK_SIZE  = 50_000    # rows per chunk for large file processing

    def detect_type(self, df: pd.DataFrame) -> str:
        """Detect dataset format from column names."""
        cols_lower = {c.lower().strip() for c in df.columns}
        scores: Dict[str, int] = {}
        for dtype, signatures in DATASET_SIGNATURES.items():
            score = sum(1 for sig in signatures if sig in cols_lower)
            if score > 0:
                scores[dtype] = score
        if not scores:
            return "generic"
        return max(scores, key=scores.get)

    def apply_code_translations(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Translate HMDA numeric codes to human-readable labels in-place.
        Only translates columns whose values look like numeric codes.
        """
        df = df.copy()
        for col in df.columns:
            col_lower = col.lower().strip()
            for patterns, code_map in COLUMN_CODE_MAPS:
                if any(pat in col_lower for pat in patterns):
                    # Only translate if the majority of values are numeric codes
                    sample = df[col].dropna().astype(str).str.strip()
                    if len(sample) == 0:
                        break
                    in_map = sample.isin(code_map.keys()).mean()
                    if in_map >= 0.5:   # at least 50% match → translate
                        df[col] = df[col].astype(str).str.strip().map(
                            lambda v, cm=code_map: cm.get(v, v)
                        )
                    break
        return df

    def normalize_gender_col(self, series: pd.Series) -> pd.Series:
        """
        Normalize gender/sex column:
        - 'male : single' → 'Male'
        - 'female : divorced...' → 'Female'
        - HMDA codes '1'→'Male', '2'→'Female'
        - Derived sex values pass through
        """
        s = series.astype(str).str.strip()
        # Handle 'male : single' style
        if s.str.contains(" : ", na=False).any():
            s = s.str.split(" : ").str[0].str.strip().str.title()
        # Apply HMDA sex codes
        s = s.map(lambda v: HMDA_SEX_CODES.get(v, v))
        return s

    def normalize_race_col(self, series: pd.Series) -> pd.Series:
        """Apply HMDA race codes to a series."""
        s = series.astype(str).str.strip()
        return s.map(lambda v: HMDA_RACE_CODES.get(v, v))

    def normalize_outcome_col(self, series: pd.Series) -> pd.Series:
        """
        Normalize outcome/decision to Approved/Denied/Withdrawn/Incomplete/Purchased.
        Handles HMDA codes, German credit 0/1, and text values.
        """
        NORM_MAP = {
            # HMDA codes
            "1": "Approved", "2": "Approved", "8": "Approved",
            "3": "Denied",   "7": "Denied",
            "4": "Withdrawn",
            "5": "Incomplete",
            "6": "Purchased",
            # German credit
            "0": "Approved",  # good credit = approved
            # Text values
            "approved": "Approved", "originated": "Approved",
            "approved but not accepted": "Approved",
            "loan originated": "Approved", "funded": "Approved",
            "denied": "Denied", "rejected": "Denied", "declined": "Denied",
            "withdrawn": "Withdrawn", "application withdrawn": "Withdrawn",
            "incomplete": "Incomplete", "closed for incompleteness": "Incomplete",
            "purchased": "Purchased", "loan purchased": "Purchased",
        }
        return series.astype(str).str.strip().str.lower().map(
            lambda v: NORM_MAP.get(v, v.title())
        )

    def is_approval(self, value: Any) -> bool:
        """Unified approval check covering all dataset formats."""
        v = str(value).strip().lower()
        # HMDA codes
        if v in HMDA_APPROVAL_CODES:
            return True
        if v in HMDA_DENIAL_CODES:
            return False
        # German credit
        if v == "0":
            return True
        if v == "1":
            return False
        # Normalized text
        return v in {"approved", "originated", "loan originated",
                     "approved but not accepted", "funded", "preapproval approved"}

    def get_strategic_sample(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a stratified sample capped at SAMPLE_SIZE rows.
        Preserves decision distribution for fairness analysis accuracy.
        Detects outcome column automatically.
        """
        if len(df) <= self.SAMPLE_SIZE:
            return df

        # Try to find outcome column for stratified sampling
        outcome_col = None
        for col in df.columns:
            if any(kw in col.lower() for kw in ("decision", "action_taken", "default", "outcome", "status")):
                outcome_col = col
                break

        if outcome_col and df[outcome_col].nunique() < 20:
            try:
                return df.groupby(outcome_col, group_keys=False).apply(
                    lambda x: x.sample(
                        n=min(len(x), int(self.SAMPLE_SIZE * len(x) / len(df))),
                        random_state=42,
                    )
                ).reset_index(drop=True)
            except Exception:
                pass

        return df.sample(n=self.SAMPLE_SIZE, random_state=42).reset_index(drop=True)

    def read_large_csv(self, filepath: str, max_rows: int = 500_000) -> pd.DataFrame:
        """
        Read a potentially large CSV in chunks, collecting stats.
        Returns a DataFrame of up to max_rows rows.
        """
        chunks = []
        rows_read = 0
        try:
            for chunk in pd.read_csv(filepath, chunksize=self.CHUNK_SIZE, low_memory=False):
                chunks.append(chunk)
                rows_read += len(chunk)
                if rows_read >= max_rows:
                    break
        except Exception as e:
            raise ValueError(f"Failed to read CSV in chunks: {e}")

        if not chunks:
            raise ValueError("CSV file appears to be empty.")

        return pd.concat(chunks, ignore_index=True)

    def prepare_for_analysis(
        self,
        df: pd.DataFrame,
        apply_translations: bool = True,
        sample: bool = True,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Full preparation pipeline:
        1. Detect dataset type
        2. Apply code translations
        3. Sample if needed
        Returns (prepared_df, metadata_dict)
        """
        dataset_type = self.detect_type(df)
        original_rows = len(df)

        if apply_translations:
            df = self.apply_code_translations(df)

        if sample:
            df = self.get_strategic_sample(df)

        return df, {
            "dataset_type": dataset_type,
            "original_rows": original_rows,
            "analysis_rows": len(df),
            "was_sampled": len(df) < original_rows,
        }
