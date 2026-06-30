"""
Report Generator – produces PDF and JSON compliance and fairness reports.
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, SimpleDocTemplate, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from backend.models.schemas import FairnessReport, MLPrediction


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

NAVY    = colors.HexColor("#1a237e")
BLUE    = colors.HexColor("#1976D2")
GREEN   = colors.HexColor("#388E3C")
RED     = colors.HexColor("#D32F2F")
AMBER   = colors.HexColor("#F57C00")
LGREY   = colors.HexColor("#F5F5F5")
MGREY   = colors.HexColor("#9E9E9E")


# ---------------------------------------------------------------------------
# Base builder helpers
# ---------------------------------------------------------------------------

def _build_doc(buffer: io.BytesIO, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1.0 * inch,
        bottomMargin=0.75 * inch,
        title=title,
    )


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(
        "ReportTitle",
        parent=ss["Title"],
        fontSize=20, textColor=NAVY, spaceAfter=6, leading=24, alignment=TA_CENTER,
    ))
    ss.add(ParagraphStyle(
        "SectionHeading",
        parent=ss["Heading2"],
        fontSize=13, textColor=NAVY, spaceBefore=12, spaceAfter=4,
    ))
    ss.add(ParagraphStyle(
        "SubHeading",
        parent=ss["Heading3"],
        fontSize=11, textColor=BLUE, spaceBefore=8, spaceAfter=3,
    ))
    ss.add(ParagraphStyle(
        "BodyText2",
        parent=ss["Normal"],
        fontSize=9, leading=13, spaceAfter=3,
    ))
    ss.add(ParagraphStyle(
        "Finding",
        parent=ss["Normal"],
        fontSize=9, leading=13, leftIndent=12, spaceAfter=3,
    ))
    return ss


def _table_style(header_bg=NAVY, row_alt=LGREY) -> TableStyle:
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 9),
        ("ALIGN",       (0, 0), (-1, 0), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, row_alt]),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("ALIGN",       (1, 1), (-1, -1), "CENTER"),
        ("GRID",        (0, 0), (-1, -1), 0.4, MGREY),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ])


def _header_footer(canvas, doc):
    """Draw page header and footer."""
    canvas.saveState()
    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, letter[1] - 0.4 * inch, letter[0], 0.4 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(0.75 * inch, letter[1] - 0.27 * inch, "Fair Lending Intelligence Platform")
    canvas.drawRightString(
        letter[0] - 0.75 * inch,
        letter[1] - 0.27 * inch,
        datetime.utcnow().strftime("%Y-%m-%d"),
    )
    # Footer
    canvas.setFillColor(MGREY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        0.75 * inch, 0.4 * inch, "CONFIDENTIAL – For Internal Compliance Use Only"
    )
    canvas.drawRightString(
        letter[0] - 0.75 * inch, 0.4 * inch, f"Page {doc.page}"
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Generates PDF and JSON reports for fairness, compliance, risk, and executive summaries."""

    def __init__(self) -> None:
        self._ss = _styles()

    def _p(self, text: str, style: str = "BodyText2") -> Paragraph:
        return Paragraph(str(text), self._ss[style])

    def _section(self, title: str) -> List:
        return [
            Spacer(1, 0.1 * inch),
            self._p(title, "SectionHeading"),
            HRFlowable(width="100%", thickness=1, color=BLUE),
            Spacer(1, 0.05 * inch),
        ]

    def _score_color(self, score: float) -> colors.Color:
        if score >= 80:
            return GREEN
        elif score >= 60:
            return AMBER
        return RED

    # ------------------------------------------------------------------
    # Fairness Report
    # ------------------------------------------------------------------

    def generate_fairness_report(
        self,
        fairness_report: FairnessReport,
        fmt: str = "pdf",
    ) -> bytes:
        if fmt == "json":
            return fairness_report.model_dump_json(indent=2).encode()

        buffer = io.BytesIO()
        doc = _build_doc(buffer, "Fair Lending Fairness Report")
        story = []

        # Title
        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("FAIR LENDING FAIRNESS AUDIT REPORT", "ReportTitle"))
        story.append(self._p(
            f"Dataset ID: {fairness_report.dataset_id}   |   "
            f"Generated: {fairness_report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "BodyText2",
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Fairness Score
        score = fairness_report.score
        score_color = self._score_color(score)
        story.extend(self._section("Fairness Score"))
        score_data = [
            ["Metric", "Value", "Status"],
            ["Overall Fairness Score", f"{score}/100",
             "ACCEPTABLE" if score >= 80 else "NEEDS ATTENTION" if score >= 60 else "HIGH RISK"],
            ["Disparate Impact Threshold", "80% (4/5ths Rule)", "CFPB / Reg B"],
        ]
        t = Table(score_data, colWidths=[2.5 * inch, 2 * inch, 2 * inch])
        t.setStyle(_table_style())
        story.append(t)
        story.append(Spacer(1, 0.1 * inch))

        # Disparate Impact Ratios
        if fairness_report.disparate_impact_ratios:
            story.extend(self._section("Disparate Impact Analysis"))
            di_data = [["Protected Class", "DI Ratio", "Pass/Fail"]]
            for field, ratio in fairness_report.disparate_impact_ratios.items():
                status = "PASS ✓" if ratio >= 0.80 else "FAIL ✗"
                di_data.append([field.capitalize(), f"{ratio:.2%}", status])
            t = Table(di_data, colWidths=[2.5 * inch, 2 * inch, 2 * inch])
            style = _table_style()
            # Colour fail rows red
            for i, row in enumerate(di_data[1:], 1):
                if "FAIL" in row[2]:
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFEBEE"))
                    style.add("TEXTCOLOR",  (2, i), (2, i), RED)
            t.setStyle(style)
            story.append(t)
            story.append(Spacer(1, 0.1 * inch))

        # Approval Rates by Group
        if fairness_report.approval_rates_by_group:
            story.extend(self._section("Approval Rates by Demographic Group"))
            for field, rates in fairness_report.approval_rates_by_group.items():
                story.append(self._p(field.capitalize(), "SubHeading"))
                rate_data = [["Group", "Approval Rate"]]
                for grp, rate in sorted(rates.items(), key=lambda x: x[1], reverse=True):
                    rate_data.append([str(grp), f"{rate:.1%}"])
                t = Table(rate_data, colWidths=[3.5 * inch, 2 * inch])
                t.setStyle(_table_style())
                story.append(t)
                story.append(Spacer(1, 0.05 * inch))

        # Bias Indicators
        if fairness_report.bias_indicators:
            story.extend(self._section("Detected Bias Indicators"))
            bi_data = [["Field", "Group", "DI Ratio", "Severity"]]
            for ind in fairness_report.bias_indicators:
                bi_data.append([
                    ind.field.capitalize(),
                    str(ind.group),
                    f"{ind.value:.2%}",
                    ind.severity.upper(),
                ])
            t = Table(bi_data, colWidths=[1.5 * inch, 2 * inch, 1.5 * inch, 1.5 * inch])
            style = _table_style()
            sev_colors = {"CRITICAL": colors.HexColor("#FFCDD2"), "HIGH": colors.HexColor("#FFE0B2"),
                          "MEDIUM": colors.HexColor("#FFF9C4")}
            for i, row in enumerate(bi_data[1:], 1):
                bg = sev_colors.get(row[3], colors.white)
                style.add("BACKGROUND", (0, i), (-1, i), bg)
            t.setStyle(style)
            story.append(t)
            story.append(Spacer(1, 0.1 * inch))

        # Findings
        story.extend(self._section("Findings"))
        for finding in fairness_report.findings:
            story.append(self._p(f"• {finding}", "Finding"))

        # Recommendations
        story.extend(self._section("Recommendations"))
        for rec in fairness_report.recommendations:
            story.append(self._p(f"• {rec}", "Finding"))

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Compliance Report
    # ------------------------------------------------------------------

    def generate_compliance_report(
        self,
        df: Any,  # pd.DataFrame
        field_map: Optional[Dict[str, Any]] = None,
        fmt: str = "pdf",
    ) -> bytes:
        if fmt == "json":
            summary = {
                "total_records": len(df),
                "columns": list(df.columns),
                "field_map": field_map or {},
                "generated_at": datetime.utcnow().isoformat(),
            }
            return json.dumps(summary, indent=2).encode()

        buffer = io.BytesIO()
        doc = _build_doc(buffer, "HMDA Compliance Report")
        story = []

        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("HMDA COMPLIANCE SUMMARY REPORT", "ReportTitle"))
        story.append(self._p(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}   |   "
            f"Total Records: {len(df):,}",
            "BodyText2",
        ))

        # Dataset Overview
        story.extend(self._section("Dataset Overview"))
        overview_data = [
            ["Metric", "Value"],
            ["Total Loan Applications", f"{len(df):,}"],
            ["Total Columns", str(len(df.columns))],
            ["Mapped Canonical Fields", str(len(field_map or {}))],
        ]

        # Decision breakdown
        decision_cols = [c for c in df.columns if any(
            kw in c.lower() for kw in ("decision", "action_taken", "outcome")
        )]
        if decision_cols:
            col = decision_cols[0]
            for val, cnt in df[col].value_counts().items():
                overview_data.append([f"  {val}", f"{cnt:,} ({cnt/len(df):.1%})"])

        t = Table(overview_data, colWidths=[3.5 * inch, 3 * inch])
        t.setStyle(_table_style())
        story.append(t)

        # Missing data summary
        story.extend(self._section("Data Quality Summary"))
        missing = df.isnull().sum()
        missing_data = [["Column", "Missing Count", "Missing %"]]
        for col, cnt in missing[missing > 0].items():
            pct = cnt / len(df) * 100
            missing_data.append([col, str(cnt), f"{pct:.1f}%"])

        if len(missing_data) == 1:
            missing_data.append(["No missing values detected", "", ""])

        t = Table(missing_data, colWidths=[3 * inch, 2 * inch, 1.5 * inch])
        t.setStyle(_table_style())
        story.append(t)

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Risk Report (from raw DataFrame — no ML required)
    # ------------------------------------------------------------------

    def generate_risk_report_from_df(
        self,
        df: Any,  # pd.DataFrame
        field_map: Optional[Dict[str, Any]] = None,
        fmt: str = "pdf",
    ) -> bytes:
        """Generate a risk report directly from dataset stats when no ML predictions exist."""
        import pandas as pd

        if fmt == "json":
            summary: Dict[str, Any] = {
                "total_records": len(df),
                "note": "Statistical risk summary (ML model not trained)",
                "generated_at": datetime.utcnow().isoformat(),
            }
            # Numeric column stats
            num_cols = df.select_dtypes(include="number").columns.tolist()
            summary["numeric_stats"] = {
                col: {
                    "mean": round(float(df[col].mean()), 2),
                    "median": round(float(df[col].median()), 2),
                    "std": round(float(df[col].std()), 2),
                }
                for col in num_cols[:10]
            }
            return json.dumps(summary, default=str, indent=2).encode()

        buffer = io.BytesIO()
        doc = _build_doc(buffer, "Applicant Risk Report")
        story = []

        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("APPLICANT RISK ASSESSMENT REPORT", "ReportTitle"))
        story.append(self._p(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}   |   "
            f"Total Applicants: {len(df):,}   |   Statistical Analysis",
            "BodyText2",
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Note about ML
        story.extend(self._section("Analysis Method"))
        story.append(self._p(
            "This report uses statistical analysis of the dataset. For ML-based risk scoring "
            "(approval probability, individual risk categories), use the ML Engine page to train "
            "a model first, then regenerate this report.",
            "BodyText2",
        ))

        # Dataset overview
        story.extend(self._section("Portfolio Overview"))
        overview = [["Metric", "Value"], ["Total Applications", f"{len(df):,}"], ["Total Fields", str(len(df.columns))]]

        # Outcome column detection
        outcome_cols = [c for c in df.columns if any(
            kw in c.lower() for kw in ("action_taken", "decision", "outcome", "approved", "status", "loan_status")
        )]
        if outcome_cols:
            col = outcome_cols[0]
            for val, cnt in df[col].value_counts().head(6).items():
                overview.append([f"  {col} = {val}", f"{cnt:,} ({cnt/len(df):.1%})"])

        t = Table(overview, colWidths=[3.5 * inch, 3 * inch])
        t.setStyle(_table_style())
        story.append(t)

        # Numeric distribution
        import pandas as pd
        num_cols = df.select_dtypes(include="number").columns.tolist()
        risk_cols = [c for c in num_cols if any(
            kw in c.lower() for kw in ("income", "loan", "credit", "debt", "dti", "amount", "rate", "score")
        )][:8]

        if risk_cols:
            story.extend(self._section("Key Risk Indicator Distribution"))
            stats_data = [["Field", "Mean", "Median", "Std Dev", "Missing %"]]
            for col in risk_cols:
                missing_pct = df[col].isna().sum() / len(df) * 100
                stats_data.append([
                    col.replace("_", " ").title(),
                    f"{df[col].mean():,.1f}",
                    f"{df[col].median():,.1f}",
                    f"{df[col].std():,.1f}",
                    f"{missing_pct:.1f}%",
                ])
            t = Table(stats_data, colWidths=[2.2 * inch, 1.3 * inch, 1.3 * inch, 1.3 * inch, 1.1 * inch])
            t.setStyle(_table_style())
            story.append(t)

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Risk Report (from ML predictions)

    def generate_risk_report(
        self,
        predictions: List[MLPrediction],
        fmt: str = "pdf",
    ) -> bytes:
        if fmt == "json":
            return json.dumps(
                [p.model_dump() for p in predictions],
                default=str, indent=2
            ).encode()

        buffer = io.BytesIO()
        doc = _build_doc(buffer, "Applicant Risk Report")
        story = []

        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("APPLICANT RISK ASSESSMENT REPORT", "ReportTitle"))
        story.append(self._p(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}   |   "
            f"Total Applicants: {len(predictions):,}",
            "BodyText2",
        ))

        # Risk Distribution
        from collections import Counter
        dist = Counter(p.risk_category for p in predictions)
        story.extend(self._section("Risk Distribution Summary"))
        risk_data = [["Risk Category", "Count", "Percentage"]]
        for cat in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH"):
            cnt = dist.get(cat, 0)
            risk_data.append([cat, str(cnt), f"{cnt/max(len(predictions),1):.1%}"])
        t = Table(risk_data, colWidths=[2.5 * inch, 2 * inch, 2 * inch])
        t.setStyle(_table_style())
        story.append(t)

        # Top HIGH risk applicants
        high_risk = [p for p in predictions if p.risk_category in ("HIGH", "VERY_HIGH")][:20]
        if high_risk:
            story.extend(self._section("High Risk Applications (Sample)"))
            hr_data = [["Applicant ID", "Approval Prob.", "Risk Score", "Category"]]
            for p in high_risk:
                hr_data.append([
                    p.applicant_id,
                    f"{p.approval_probability:.1%}",
                    f"{p.risk_score:.1f}",
                    p.risk_category,
                ])
            t = Table(hr_data, colWidths=[2 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
            t.setStyle(_table_style())
            story.append(t)

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Executive Summary
    # ------------------------------------------------------------------

    def generate_executive_summary(
        self,
        all_data: Dict[str, Any],
        fmt: str = "pdf",
    ) -> bytes:
        if fmt == "json":
            return json.dumps(all_data, default=str, indent=2).encode()

        buffer = io.BytesIO()
        doc = _build_doc(buffer, "Executive Summary")
        story = []

        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("FAIR LENDING EXECUTIVE SUMMARY", "ReportTitle"))
        story.append(self._p(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "BodyText2",
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Key metrics table
        story.extend(self._section("Key Performance Indicators"))
        kpi_rows = [["Indicator", "Value"]]
        for key, val in all_data.items():
            if isinstance(val, (int, float, str)):
                kpi_rows.append([str(key).replace("_", " ").title(), str(val)])
        t = Table(kpi_rows, colWidths=[3.5 * inch, 3 * inch])
        t.setStyle(_table_style())
        story.append(t)

        # Findings / notes
        findings = all_data.get("findings", [])
        if findings:
            story.extend(self._section("Key Findings"))
            for f in findings:
                story.append(self._p(f"• {f}", "Finding"))

        # Recommendations
        recs = all_data.get("recommendations", [])
        if recs:
            story.extend(self._section("Recommendations"))
            for r in recs:
                story.append(self._p(f"• {r}", "Finding"))

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return buffer.getvalue()
