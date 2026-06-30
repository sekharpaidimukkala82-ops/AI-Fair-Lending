"""
Schema Discovery – automatically maps arbitrary column names to canonical fields
using string-similarity fuzzy matching.
"""

from __future__ import annotations

import difflib
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backend.models.schemas import SchemaDiscoveryResult


# ---------------------------------------------------------------------------
# Canonical Field Definitions
# ---------------------------------------------------------------------------

class CanonicalField(str, Enum):
    APPLICANT_INCOME    = "applicant_income"
    LOAN_AMOUNT         = "loan_amount"
    DECISION            = "decision"
    RACE                = "race"
    GENDER              = "gender"
    AGE                 = "age"
    STATE               = "state"
    COUNTY              = "county"
    DTI_RATIO           = "dti_ratio"
    CREDIT_SCORE        = "credit_score"
    EMPLOYMENT          = "employment"
    PROPERTY_TYPE       = "property_type"
    LOAN_PURPOSE        = "loan_purpose"
    LOAN_TYPE           = "loan_type"
    APPLICANT_ID        = "applicant_id"
    CO_APPLICANT_INCOME = "co_applicant_income"
    INTEREST_RATE       = "interest_rate"
    LIEN_STATUS         = "lien_status"
    TRACT_INCOME        = "tract_income"
    DENIAL_REASON       = "denial_reason"


FIELD_CATEGORIES: Dict[CanonicalField, str] = {
    CanonicalField.APPLICANT_ID:        "applicant",
    CanonicalField.APPLICANT_INCOME:    "applicant",
    CanonicalField.CO_APPLICANT_INCOME: "applicant",
    CanonicalField.EMPLOYMENT:          "applicant",
    CanonicalField.AGE:                 "applicant",
    CanonicalField.LOAN_AMOUNT:         "loan",
    CanonicalField.LOAN_TYPE:           "loan",
    CanonicalField.LOAN_PURPOSE:        "loan",
    CanonicalField.INTEREST_RATE:       "loan",
    CanonicalField.LIEN_STATUS:         "loan",
    CanonicalField.PROPERTY_TYPE:       "loan",
    CanonicalField.DECISION:            "decision",
    CanonicalField.DENIAL_REASON:       "decision",
    CanonicalField.RACE:                "demographic",
    CanonicalField.GENDER:              "demographic",
    CanonicalField.TRACT_INCOME:        "geographic",
    CanonicalField.STATE:               "geographic",
    CanonicalField.COUNTY:              "geographic",
    CanonicalField.DTI_RATIO:           "risk",
    CanonicalField.CREDIT_SCORE:        "risk",
}


# ---------------------------------------------------------------------------
# Synonym Maps
# ---------------------------------------------------------------------------

FIELD_SYNONYMS: Dict[CanonicalField, List[str]] = {
    CanonicalField.APPLICANT_ID: [
        "applicant_id", "app_id", "application_id", "loan_application_id",
        "borrower_id", "customer_id", "client_id", "record_id", "id",
        "application_number", "loan_number", "case_id", "ref_id",
    ],
    CanonicalField.APPLICANT_INCOME: [
        "applicant_income", "income", "annual_income", "gross_income",
        "applicant_income_000s", "income_000s", "borrower_income",
        "hud_median_family_income", "applicant_gross_income",
        "annual_gross_income", "reported_income", "stated_income",
        "income_amount", "yearly_income", "total_income",
        "income_000s", "tract_to_msa_income_pct",
        "installment_as_income_perc",
    ],
    CanonicalField.CO_APPLICANT_INCOME: [
        "co_applicant_income", "co_income", "coborrower_income",
        "co_borrower_income", "joint_income", "coapplicant_income",
        "co_applicant_income_000s", "secondary_income",
    ],
    CanonicalField.LOAN_AMOUNT: [
        "loan_amount", "loan_amount_000s", "amount", "loan_size",
        "requested_amount", "mortgage_amount", "principal_amount",
        "loan_balance", "loan_value", "mortgage_balance",
        "original_loan_amount", "funded_amount", "approved_amount",
        "credit_amount", "loan_amount_thousands",
        "original_upb", "orig_upb",
    ],
    CanonicalField.DECISION: [
        "decision", "action_taken", "loan_decision", "outcome",
        "disposition", "status", "loan_status", "application_status",
        "approval_status", "result", "loan_outcome", "application_outcome",
        "action", "final_action", "underwriting_decision",
        "action_taken_name", "action_taken_type",
        "credit_decision", "final_decision",
        "default", "credit_risk", "class", "target", "label", "y",
    ],
    CanonicalField.RACE: [
        "race", "applicant_race", "race_1", "applicant_race_1",
        "borrower_race", "ethnicity_race", "racial_group",
        "race_ethnicity", "applicant_race_code", "race_code",
        "demographic_race", "racial_category",
        "applicant_race_2", "applicant_race_3",
        "derived_race", "co_applicant_race_1", "applicant_race_name_1",
        "ethnic_group",
    ],
    CanonicalField.GENDER: [
        "gender", "sex", "applicant_sex", "borrower_sex",
        "applicant_gender", "gender_code", "sex_code",
        "applicant_sex_code", "borrower_gender", "demographic_gender",
        "male_female", "gender_identity",
        "applicant_sex_name", "derived_sex",
        "co_applicant_sex", "personal_status_sex", "personal_status",
    ],
    CanonicalField.AGE: [
        "age", "applicant_age", "borrower_age", "age_group",
        "age_range", "age_bracket", "applicant_age_group",
        "borrower_age_group", "age_category", "age_band",
        "years_old", "dob_derived_age",
        "applicant_age_above_62",
    ],
    CanonicalField.STATE: [
        "state", "state_code", "state_abbr", "state_name",
        "property_state", "msa_state", "loan_state",
        "collateral_state", "state_of_property", "origination_state",
        "us_state", "state_of_residence",
    ],
    CanonicalField.COUNTY: [
        "county", "county_code", "county_name", "fips_county",
        "county_fips", "census_county", "msa_county",
        "property_county", "county_of_property", "county_id",
        "county_tract", "local_county",
    ],
    CanonicalField.DTI_RATIO: [
        "dti_ratio", "dti", "debt_to_income", "debt_income_ratio",
        "debt_to_income_ratio", "total_dti", "back_end_dti",
        "front_end_dti", "combined_dti", "monthly_dti",
        "housing_expense_ratio", "obligation_ratio",
        "combined_loan_to_value_ratio",
        "loan_to_value_ratio", "ltv", "cltv",
    ],
    CanonicalField.CREDIT_SCORE: [
        "credit_score", "fico", "fico_score", "credit_rating",
        "vantage_score", "credit_bureau_score", "beacon_score",
        "empirica_score", "applicant_credit_score",
        "borrower_credit_score", "qualifying_fico", "risk_score",
        "credit_quality_score",
        "fico_range_low", "fico_range_high", "credit_score_model",
        "applicant_credit_score_type",
    ],
    CanonicalField.EMPLOYMENT: [
        "employment", "employment_status", "employment_type",
        "employment_length", "years_employed", "job_status",
        "work_status", "occupancy_type", "occupation",
        "employer_name", "employment_category", "employment_classification",
        "years_at_job", "self_employed",
    ],
    CanonicalField.PROPERTY_TYPE: [
        "property_type", "property_type_code", "collateral_type",
        "asset_type", "dwelling_type", "home_type",
        "property_class", "structure_type", "unit_type",
        "manufactured_home", "property_description",
        "real_estate_type", "residential_type",
    ],
    CanonicalField.LOAN_PURPOSE: [
        "loan_purpose", "purpose", "loan_purpose_code",
        "reason_for_loan", "mortgage_purpose", "application_purpose",
        "refinance_type", "transaction_purpose", "use_of_proceeds",
        "loan_use", "financing_purpose", "credit_purpose",
        "origination_purpose",
    ],
    CanonicalField.LOAN_TYPE: [
        "loan_type", "mortgage_type", "loan_type_code",
        "product_type", "loan_category", "product_code",
        "loan_product", "mortgage_product", "program_type",
        "financing_type", "credit_type", "loan_class",
        "conventional_government",
    ],
    CanonicalField.INTEREST_RATE: [
        "interest_rate", "rate", "note_rate", "interest_rate_spread",
        "rate_spread", "apr", "annual_percentage_rate",
        "mortgage_rate", "loan_rate", "origination_rate",
        "initial_rate", "coupon_rate",
    ],
    CanonicalField.LIEN_STATUS: [
        "lien_status", "lien", "lien_position", "lien_type",
        "security_interest", "mortgage_position",
        "first_lien", "second_lien", "subordinate_lien",
        "collateral_position", "deed_of_trust",
    ],
    CanonicalField.TRACT_INCOME: [
        "tract_income", "census_tract_income", "tract_to_msa_income",
        "tract_median_income", "msa_income", "area_median_income",
        "ami", "median_family_income", "tract_income_ratio",
        "census_income", "neighborhood_income",
    ],
    CanonicalField.DENIAL_REASON: [
        "denial_reason", "denial_reason_1", "denial_reason_2",
        "reason_for_denial", "rejection_reason", "adverse_action_reason",
        "denial_code", "adverse_action_code", "denial_basis",
        "turn_down_reason", "decline_reason",
    ],
}


# ---------------------------------------------------------------------------
# Schema Discovery Engine
# ---------------------------------------------------------------------------

class SchemaDiscovery:
    """Fuzzy-maps arbitrary DataFrame columns to canonical lending fields."""

    SIMILARITY_THRESHOLD: float = 0.60  # minimum ratio to accept a mapping

    def __init__(self) -> None:
        self._synonym_index: Dict[str, CanonicalField] = {}
        self._build_synonym_index()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_synonym_index(self) -> None:
        """Pre-build a flat lookup: normalised synonym → CanonicalField."""
        for field, synonyms in FIELD_SYNONYMS.items():
            for syn in synonyms:
                self._synonym_index[self._normalise(syn)] = field

    @staticmethod
    def _normalise(text: str) -> str:
        """Lowercase, strip, replace spaces/dashes with underscores."""
        return text.lower().strip().replace(" ", "_").replace("-", "_")

    def _fuzzy_match(
        self, column: str
    ) -> Tuple[Optional[CanonicalField], float]:
        """
        Try exact lookup first; fall back to difflib sequence matching.
        Returns (best_field, confidence).
        """
        norm = self._normalise(column)

        # 1. Exact match
        if norm in self._synonym_index:
            return self._synonym_index[norm], 1.0

        # 2. Substring containment (e.g. "loan_amount_000s" contains "loan_amount")
        for key, field in self._synonym_index.items():
            if key in norm or norm in key:
                return field, 0.90

        # 3. Difflib ratio across all synonyms
        best_field: Optional[CanonicalField] = None
        best_score: float = 0.0
        for key, field in self._synonym_index.items():
            score = difflib.SequenceMatcher(None, norm, key).ratio()
            if score > best_score:
                best_score = score
                best_field = field

        if best_score >= self.SIMILARITY_THRESHOLD:
            return best_field, round(best_score, 3)

        return None, 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(self, df: pd.DataFrame) -> Dict[CanonicalField, str]:
        """
        Return a mapping of CanonicalField → original column name.
        Only includes columns that matched above the threshold.
        """
        mappings: Dict[CanonicalField, str] = {}
        used_canonical: set = set()

        for col in df.columns:
            field, score = self._fuzzy_match(col)
            if field and field not in used_canonical:
                mappings[field] = col
                used_canonical.add(field)

        return mappings

    def get_field_category(self, field: CanonicalField) -> str:
        """Return the category string for a canonical field."""
        return FIELD_CATEGORIES.get(field, "other")

    def map_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a copy of df with discovered columns renamed to their
        canonical field names.  Unmapped columns are preserved as-is.
        """
        mappings = self.discover(df)
        rename_map = {orig: cf.value for cf, orig in mappings.items()}
        return df.rename(columns=rename_map)

    def generate_discovery_report(self, df: pd.DataFrame) -> SchemaDiscoveryResult:
        """Return a full SchemaDiscoveryResult for a DataFrame."""
        all_mappings = self.discover(df)
        mapped_cols = set(all_mappings.values())
        unmapped = [c for c in df.columns if c not in mapped_cols]

        # Confidence scores per canonical field
        confidence: Dict[str, float] = {}
        for field, orig_col in all_mappings.items():
            _, score = self._fuzzy_match(orig_col)
            confidence[field.value] = score

        # Group by category
        categories: Dict[str, List[str]] = {}
        for field in all_mappings:
            cat = self.get_field_category(field)
            categories.setdefault(cat, []).append(field.value)

        # Warnings
        warnings: List[str] = []
        required = {CanonicalField.DECISION, CanonicalField.LOAN_AMOUNT}
        for req in required:
            if req not in all_mappings:
                warnings.append(f"Required field '{req.value}' was not found in the dataset.")

        return SchemaDiscoveryResult(
            total_columns=len(df.columns),
            mapped_columns=len(all_mappings),
            field_mappings={cf.value: orig for cf, orig in all_mappings.items()},
            unmapped_columns=unmapped,
            confidence_scores=confidence,
            categories=categories,
            warnings=warnings,
        )
