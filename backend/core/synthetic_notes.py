"""
Synthetic Note Generator – produces realistic underwriting-style notes
for lending applications using template-based generation.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Templates per decision type
# ---------------------------------------------------------------------------

APPROVED_TEMPLATES = [
    (
        "Loan application reviewed and approved. Applicant demonstrates strong creditworthiness "
        "with a credit score of {credit_score} and an annual income of {income}. "
        "The requested loan amount of {loan_amount} represents a manageable obligation given the "
        "applicant's debt-to-income ratio of {dti}. Employment history is verified as {employment}. "
        "Property type: {property_type}. Loan purpose: {loan_purpose}. Approved as submitted."
    ),
    (
        "Application approved following standard underwriting review. "
        "Applicant's income of {income} adequately supports the proposed payment structure. "
        "Credit profile ({credit_score}) meets or exceeds program guidelines. "
        "DTI of {dti} is within acceptable limits. The {loan_type} loan for {loan_purpose} "
        "on a {property_type} property in {state} satisfies all eligibility requirements."
    ),
    (
        "Underwriting decision: APPROVED. Key metrics — Income: {income}; "
        "Credit Score: {credit_score}; DTI: {dti}; Loan Amount: {loan_amount}. "
        "No adverse factors identified. Applicant is employed as {employment}. "
        "All documentation received and verified. Loan product: {loan_type}."
    ),
    (
        "File approved per credit policy. The {loan_purpose} loan request of {loan_amount} "
        "is supported by verified income of {income}. Credit bureau report shows a score of "
        "{credit_score} with no significant derogatory history. DTI ratio of {dti} is acceptable. "
        "Collateral is a {property_type} in {county}, {state}."
    ),
    (
        "APPROVAL NOTICE: Application meets all automated underwriting system criteria. "
        "Borrower income: {income}. Requested amount: {loan_amount}. "
        "Credit score: {credit_score}. Loan-to-value and debt ratios within policy. "
        "Employment status confirmed: {employment}. Loan type: {loan_type}. "
        "Application proceeds to closing with standard conditions."
    ),
]

DENIED_TEMPLATES = [
    (
        "Loan application reviewed and denied. Primary reason: insufficient income to support "
        "the requested loan amount of {loan_amount}. Applicant income of {income} results in a "
        "debt-to-income ratio of {dti}, which exceeds program thresholds. "
        "Credit score of {credit_score} also falls below minimum guidelines. "
        "Applicant advised of adverse action rights and right to obtain credit report."
    ),
    (
        "Underwriting decision: DENIED. The application for a {loan_type} loan of {loan_amount} "
        "does not meet creditworthiness standards. Contributing factors include: "
        "DTI ratio of {dti} exceeding program maximum; credit score of {credit_score} "
        "below the required threshold; limited employment documentation for {employment} status. "
        "Adverse action notice will be sent within the required timeframe."
    ),
    (
        "Application for {loan_purpose} financing in the amount of {loan_amount} has been denied. "
        "The applicant's credit profile, including a score of {credit_score}, presents elevated risk. "
        "Income of {income} is insufficient to qualify for this loan size at acceptable debt ratios. "
        "Current DTI of {dti} exceeds underwriting guidelines. Denial letter mailed to applicant."
    ),
    (
        "DENIAL: After review, this {loan_purpose} application does not qualify for approval. "
        "Key deficiencies: (1) Credit score {credit_score} does not meet minimum program requirement; "
        "(2) Debt-to-income ratio {dti} is above acceptable limits; "
        "(3) Income documentation does not support the requested amount of {loan_amount}. "
        "The applicant retains the right to request specific reasons and credit bureau information."
    ),
    (
        "Application denied based on credit analysis. Reported income: {income}. "
        "Loan request: {loan_amount} for {loan_purpose} on {property_type} in {state}. "
        "Credit risk assessment: credit score of {credit_score} indicates above-average default risk. "
        "DTI of {dti} further limits qualification. Employment: {employment}. "
        "Adverse action reasons have been documented in the loan file."
    ),
]

WITHDRAWN_TEMPLATES = [
    (
        "Application for {loan_purpose} loan of {loan_amount} has been voluntarily withdrawn "
        "by the applicant prior to a credit decision. Applicant income: {income}. "
        "Credit score on file: {credit_score}. DTI: {dti}. "
        "File closed per applicant's written request. No adverse action required."
    ),
    (
        "Applicant withdrew the {loan_type} loan application of {loan_amount}. "
        "Withdrawal confirmed verbally and in writing. At time of withdrawal, "
        "the application was in underwriting review. Income: {income}, DTI: {dti}. "
        "File archived. No credit decision was rendered."
    ),
    (
        "Loan file closed — applicant-initiated withdrawal. "
        "The request for {loan_amount} ({loan_purpose}, {property_type}) in {state} "
        "was withdrawn before final underwriting review. No adverse action notice required. "
        "Income: {income}. Credit score: {credit_score}."
    ),
    (
        "Application withdrawn at borrower's request. Loan details: {loan_type} for {loan_purpose}, "
        "amount {loan_amount}, property in {county}, {state}. "
        "Applicant had an income of {income} and credit score of {credit_score} at time of withdrawal. "
        "File status updated to withdrawn. No decision was issued."
    ),
    (
        "WITHDRAWN: The applicant chose to withdraw this {loan_purpose} application "
        "before an underwriting determination was made. Loan amount requested: {loan_amount}. "
        "Income: {income}. DTI: {dti}. Property type: {property_type}. "
        "Withdrawal letter received and filed. Application closed without action."
    ),
]

INCOMPLETE_TEMPLATES = [
    (
        "Application closed for incompleteness. The {loan_type} loan request of {loan_amount} "
        "for {loan_purpose} could not be processed due to missing documentation. "
        "Despite multiple notices, the applicant did not provide required income verification. "
        "Income on file: {income}. Credit score: {credit_score}. File closed after 30-day notice period."
    ),
    (
        "File closed — incomplete application. Required documents were not received within "
        "the allotted timeframe. Loan details: {loan_amount} for {loan_purpose}, {property_type} "
        "in {state}. Applicant income: {income}. DTI: {dti}. "
        "Notice of incompleteness was sent on the required date. No credit decision issued."
    ),
    (
        "Application for {loan_purpose} financing of {loan_amount} closed for incompleteness. "
        "The applicant failed to provide documentation to verify income of {income} "
        "and employment status ({employment}). Credit score: {credit_score}. "
        "Applicable waiting period elapsed. File status: Closed/Incomplete."
    ),
    (
        "INCOMPLETE: Loan application for {loan_amount} ({loan_type}) could not proceed. "
        "The underwriting process was unable to be completed due to insufficient documentation. "
        "Missing items: income verification, tax returns, and property appraisal. "
        "Applicant was notified per ECOA/Regulation B requirements. File closed."
    ),
    (
        "Application closed for incompleteness per regulatory guidelines. "
        "The {loan_purpose} application for a {property_type} in {county}, {state} "
        "required additional documentation that was not received. "
        "Income: {income}. Credit: {credit_score}. DTI: {dti}. "
        "Final written notice was sent 30 days prior to file closure."
    ),
]

ORIGINATED_TEMPLATES = [
    (
        "Loan originated and funded. The {loan_type} loan of {loan_amount} for {loan_purpose} "
        "has been successfully closed. Borrower income: {income}. Credit score: {credit_score}. "
        "DTI: {dti}. Property type: {property_type} located in {county}, {state}. "
        "All conditions satisfied. Funds disbursed as scheduled."
    ),
    (
        "ORIGINATED: The {loan_purpose} application has closed successfully. "
        "Loan amount: {loan_amount}. Borrower's income of {income} fully supports repayment. "
        "Credit score: {credit_score}. Final DTI: {dti}. Employment: {employment}. "
        "Mortgage recorded. Servicer notified. File transferred to portfolio/secondary market."
    ),
    (
        "Loan funded and originated. After satisfying all prior-to-funding conditions, "
        "the {loan_type} mortgage of {loan_amount} closed in {state}. "
        "Applicant income: {income}. Final credit score: {credit_score}. DTI: {dti}. "
        "Property: {property_type}. Closing disclosure acknowledged by borrower."
    ),
    (
        "File originated. The {loan_purpose} loan for a {property_type} in {county}, {state} "
        "has funded. Key metrics at origination — Income: {income}, Score: {credit_score}, "
        "DTI: {dti}, Loan: {loan_amount}. Borrower employment: {employment}. "
        "Note executed. Lien perfected. File complete."
    ),
    (
        "LOAN ORIGINATED. Application received, processed, underwritten, and funded successfully. "
        "Loan type: {loan_type}. Purpose: {loan_purpose}. Amount: {loan_amount}. "
        "Borrower profile — income: {income}, DTI: {dti}, credit score: {credit_score}. "
        "Location: {county}, {state}. Property type: {property_type}. "
        "No outstanding conditions. File complete and archived."
    ),
]

TEMPLATES_BY_DECISION: Dict[str, List[str]] = {
    "approved": APPROVED_TEMPLATES,
    "originated": ORIGINATED_TEMPLATES,
    "denied": DENIED_TEMPLATES,
    "withdrawn": WITHDRAWN_TEMPLATES,
    "incomplete": INCOMPLETE_TEMPLATES,
    "closed for incompleteness": INCOMPLETE_TEMPLATES,
}


# ---------------------------------------------------------------------------
# Helper: safe value formatting
# ---------------------------------------------------------------------------

def _safe_currency(record: Dict[str, Any], *keys: str, default: str = "N/A") -> str:
    for k in keys:
        val = record.get(k)
        if val is not None and str(val).strip().lower() not in ("", "nan", "none"):
            try:
                return f"${float(val):,.0f}"
            except (ValueError, TypeError):
                return str(val)
    return default


def _safe_pct(record: Dict[str, Any], *keys: str, default: str = "N/A") -> str:
    for k in keys:
        val = record.get(k)
        if val is not None and str(val).strip().lower() not in ("", "nan", "none"):
            try:
                return f"{float(val):.1f}%"
            except (ValueError, TypeError):
                return str(val)
    return default


def _safe_str(record: Dict[str, Any], *keys: str, default: str = "N/A") -> str:
    for k in keys:
        val = record.get(k)
        if val is not None and str(val).strip().lower() not in ("", "nan", "none"):
            return str(val)
    return default


# ---------------------------------------------------------------------------
# Synthetic Note Generator
# ---------------------------------------------------------------------------

class SyntheticNoteGenerator:
    """Generates realistic, professional underwriting notes."""

    def _build_vars(self, record: Dict[str, Any]) -> Dict[str, str]:
        """Extract template variables from a record dict."""
        return {
            "income":        _safe_currency(record, "applicant_income", "income"),
            "loan_amount":   _safe_currency(record, "loan_amount"),
            "dti":           _safe_pct(record, "dti_ratio", "dti"),
            "credit_score":  _safe_str(record, "credit_score", "fico"),
            "employment":    _safe_str(record, "employment", "employment_status"),
            "loan_type":     _safe_str(record, "loan_type"),
            "loan_purpose":  _safe_str(record, "loan_purpose"),
            "property_type": _safe_str(record, "property_type"),
            "state":         _safe_str(record, "state"),
            "county":        _safe_str(record, "county"),
        }

    def generate_note(
        self,
        record: Dict[str, Any],
        decision: Optional[str] = None,
    ) -> str:
        """
        Generate a single synthetic underwriting note for a record.

        Parameters
        ----------
        record   : dict of field_name → value (canonical or original names).
        decision : explicit decision string; if None, inferred from record.

        Returns
        -------
        A professional underwriting note string.
        """
        if decision is None:
            decision = str(
                record.get("decision")
                or record.get("action_taken")
                or record.get("outcome")
                or record.get("loan_status")
                or "unknown"
            )

        decision_key = decision.strip().lower()
        templates = TEMPLATES_BY_DECISION.get(
            decision_key,
            APPROVED_TEMPLATES  # fallback
        )

        template = random.choice(templates)
        variables = self._build_vars(record)

        try:
            return template.format(**variables)
        except KeyError:
            # If template has unexpected keys, return a generic note
            return (
                f"Underwriting review completed. Decision: {decision}. "
                f"Income: {variables['income']}. Loan amount: {variables['loan_amount']}. "
                f"Credit score: {variables['credit_score']}. DTI: {variables['dti']}."
            )

    def generate_batch(
        self,
        df: pd.DataFrame,
        field_map: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Generate a synthetic note for every row in a DataFrame.

        Parameters
        ----------
        df        : DataFrame (may use original or canonical column names).
        field_map : optional {canonical_field: original_column_name}.

        Returns
        -------
        List[str] – one note per row.
        """
        notes: List[str] = []

        # Build reverse map: original_col -> canonical_field
        reverse_map: Dict[str, str] = {}
        if field_map:
            reverse_map = {v: k for k, v in field_map.items()}

        for _, row in df.iterrows():
            record_raw = row.to_dict()

            # Re-key using canonical names where possible
            record: Dict[str, Any] = {}
            for col, val in record_raw.items():
                canonical = reverse_map.get(col, col)
                record[canonical] = val

            decision = (
                record.get("decision")
                or record.get("action_taken")
                or record.get("outcome")
                or "unknown"
            )
            notes.append(self.generate_note(record, str(decision)))

        return notes
