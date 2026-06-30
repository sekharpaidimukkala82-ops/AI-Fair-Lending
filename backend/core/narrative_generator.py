"""
Narrative Generator – converts structured lending records into natural-language
descriptions suitable for embedding and semantic search.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from backend.models.schemas import Narrative


# ---------------------------------------------------------------------------
# Field formatters
# ---------------------------------------------------------------------------

def _fmt_currency(value: Any) -> str:
    try:
        v = float(value)
        if v >= 1_000:
            return f"${v:,.0f}"
        return f"${v:.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_percent(value: Any) -> str:
    try:
        v = float(value)
        return f"{v:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_number(value: Any) -> str:
    try:
        v = float(value)
        if v == int(v):
            return str(int(v))
        return f"{v:.2f}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Sentence builders per canonical field
# ---------------------------------------------------------------------------

FIELD_SENTENCE_BUILDERS: Dict[str, Any] = {
    "applicant_income":    lambda v: f"Applicant income is {_fmt_currency(v)}.",
    "co_applicant_income": lambda v: f"Co-applicant income is {_fmt_currency(v)}.",
    "loan_amount":         lambda v: f"Requested loan amount is {_fmt_currency(v)}.",
    "dti_ratio":           lambda v: f"Debt-to-income ratio is {_fmt_percent(v)}.",
    "credit_score":        lambda v: f"Credit score is {_fmt_number(v)}.",
    "interest_rate":       lambda v: f"Interest rate is {_fmt_percent(v)}.",
    "age":                 lambda v: f"Applicant age group is {v}.",
    "race":                lambda v: f"Applicant race is {v}.",
    "gender":              lambda v: f"Applicant sex/gender is {v}.",
    "state":               lambda v: f"Property is located in {v}.",
    "county":              lambda v: f"County is {v}.",
    "property_type":       lambda v: f"Property type is {v}.",
    "loan_type":           lambda v: f"Loan type is {v}.",
    "loan_purpose":        lambda v: f"Loan purpose is {v}.",
    "employment":          lambda v: f"Employment status is {v}.",
    "lien_status":         lambda v: f"Lien status is {v}.",
    "tract_income":        lambda v: f"Census tract income ratio is {_fmt_number(v)}.",
    "decision":            lambda v: f"Application was {str(v).lower()}.",
    "denial_reason":       lambda v: f"Denial reason: {v}.",
    "applicant_id":        lambda v: f"Application ID: {v}.",
}

# Fields that carry the decision context (rendered last)
DECISION_FIELDS = {"decision", "denial_reason"}

# Fields to render first (identity / context)
PRIORITY_FIELDS = [
    "applicant_id", "loan_purpose", "loan_type", "property_type",
    "state", "county",
]


class NarrativeGenerator:
    """Converts a lending record dict into a natural-language narrative string."""

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and (value != value):  # NaN
            return True
        if str(value).strip().lower() in ("", "nan", "none", "null", "unknown", "n/a"):
            return True
        return False

    def generate(
        self,
        record: Dict[str, Any],
        field_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Build a natural-language sentence from an applicant record.

        Parameters
        ----------
        record    : dict mapping column names (canonical or original) to values.
        field_map : optional dict {canonical_field: original_column_name} to
                    resolve original column names back to canonical keys.

        Returns
        -------
        A human-readable narrative string.
        """
        # Resolve original column names to canonical keys
        resolved: Dict[str, Any] = {}
        if field_map:
            reverse_map = {v: k for k, v in field_map.items()}
            for col, val in record.items():
                canonical = reverse_map.get(col, col)
                resolved[canonical] = val
        else:
            resolved = dict(record)

        sentences: List[str] = []

        def _add(key: str) -> None:
            val = resolved.get(key)
            if not self._is_missing(val) and key in FIELD_SENTENCE_BUILDERS:
                sentences.append(FIELD_SENTENCE_BUILDERS[key](val))

        # Priority fields first
        for key in PRIORITY_FIELDS:
            _add(key)

        # Remaining non-decision fields
        for key in FIELD_SENTENCE_BUILDERS:
            if key not in PRIORITY_FIELDS and key not in DECISION_FIELDS:
                _add(key)

        # Decision fields last
        for key in DECISION_FIELDS:
            _add(key)

        if not sentences:
            return "No structured information available for this application."

        return " ".join(sentences)

    def generate_batch(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> List[Narrative]:
        """
        Generate Narrative objects for every row in a DataFrame.

        Parameters
        ----------
        df        : DataFrame (may use original or canonical column names).
        field_map : optional {canonical_field: original_column_name}.

        Returns
        -------
        List[Narrative]
        """
        narratives: List[Narrative] = []

        # Determine the applicant_id column
        id_col: Optional[str] = None
        if field_map and "applicant_id" in field_map:
            id_col = field_map["applicant_id"]
        elif "applicant_id" in df.columns:
            id_col = "applicant_id"

        for idx, row in df.iterrows():
            record = row.to_dict()
            text = self.generate(record, field_map)

            if id_col and id_col in record:
                app_id = str(record[id_col])
            else:
                app_id = str(idx)

            # Build metadata from all resolved canonical fields
            metadata: Dict[str, Any] = {}
            if field_map:
                for canonical, orig in field_map.items():
                    val = record.get(orig)
                    if not self._is_missing(val):
                        metadata[canonical] = val
            else:
                metadata = {k: v for k, v in record.items() if not self._is_missing(v)}

            narratives.append(
                Narrative(applicant_id=app_id, text=text, metadata=metadata)
            )

        return narratives
