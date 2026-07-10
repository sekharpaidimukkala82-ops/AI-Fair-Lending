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
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF

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

    def _bar_chart(self, data: Dict[str, float], title: str, width: float = 6.5, height: float = 2.2, threshold: float = 0.80) -> Drawing:
        """
        Draw a horizontal bar chart showing approval rates or DI ratios.
        Bars below threshold are red, above are navy/green.
        """
        from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group
        from reportlab.platypus import Flowable

        if not data:
            return Drawing(width * inch, 0.1 * inch)

        W = width * inch
        H = height * inch
        margin_left = 1.6 * inch
        margin_right = 0.5 * inch
        margin_top = 0.3 * inch
        margin_bottom = 0.5 * inch
        bar_area_w = W - margin_left - margin_right
        bar_area_h = H - margin_top - margin_bottom

        items = sorted(data.items(), key=lambda x: x[1])
        n = len(items)
        bar_height = min(bar_area_h / n * 0.65, 0.25 * inch)
        gap = bar_area_h / n

        d = Drawing(W, H)

        # Title
        d.add(String(W / 2, H - 0.15 * inch, title,
                     fontSize=10, fontName="Helvetica-Bold",
                     fillColor=colors.HexColor("#1a237e"),
                     textAnchor="middle"))

        max_val = max(v for _, v in items) if items else 1.0
        scale_max = max(max_val * 1.1, threshold * 1.1, 1.0)

        for i, (label, value) in enumerate(items):
            y = margin_bottom + i * gap + (gap - bar_height) / 2
            bar_w = (value / scale_max) * bar_area_w

            # Bar fill color
            bar_color = colors.HexColor("#1a237e") if value >= threshold else colors.HexColor("#ef4444")

            # Bar
            d.add(Rect(margin_left, y, bar_w, bar_height,
                       fillColor=bar_color, strokeColor=None))

            # Label (left)
            label_text = str(label)[:18]
            d.add(String(margin_left - 4, y + bar_height / 2 - 4, label_text,
                         fontSize=8, fontName="Helvetica",
                         fillColor=colors.HexColor("#374151"),
                         textAnchor="end"))

            # Value (right of bar)
            val_str = f"{value:.1%}" if value <= 1.0 else f"{value:.3f}"
            d.add(String(margin_left + bar_w + 4, y + bar_height / 2 - 4, val_str,
                         fontSize=8, fontName="Helvetica-Bold",
                         fillColor=bar_color,
                         textAnchor="start"))

        # Threshold line
        threshold_x = margin_left + (threshold / scale_max) * bar_area_w
        d.add(Line(threshold_x, margin_bottom - 4, threshold_x, H - margin_top,
                   strokeColor=colors.HexColor("#ef4444"),
                   strokeWidth=1.2,
                   strokeDashArray=[4, 3]))
        d.add(String(threshold_x, margin_bottom - 14, f"80% threshold",
                     fontSize=7, fontName="Helvetica",
                     fillColor=colors.HexColor("#ef4444"),
                     textAnchor="middle"))

        return d

    # ------------------------------------------------------------------
    # Fairness Report
    # ------------------------------------------------------------------

    def generate_fairness_report(
        self,
        fairness_report: FairnessReport,
        fmt: str = "pdf",
        df: Any = None,  # optional DataFrame for additional stats
    ) -> bytes:
        if fmt == "json":
            return fairness_report.model_dump_json(indent=2).encode()

        buffer = io.BytesIO()
        doc = _build_doc(buffer, "Fair Lending & ML Analysis Report")
        story = []
        styles = _styles()

        # ── Title Page ──────────────────────────────────────────────────────
        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("FAIR LENDING & ML ANALYSIS REPORT", "ReportTitle"))
        story.append(self._p(
            f"Dataset ID: {fairness_report.dataset_id}   |   "
            f"Generated: {fairness_report.generated_at.strftime('%B %d, %Y %H:%M UTC')}",
            "BodyText2",
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=12))

        # ── Executive Summary ───────────────────────────────────────────────
        story.extend(self._section("Executive Summary"))
        score = fairness_report.score
        di_ratios = fairness_report.disparate_impact_ratios or {}
        approval_rates = fairness_report.approval_rates_by_group or {}
        indicators = fairness_report.bias_indicators or []

        # Determine overall status
        if score >= 80:
            status_text = "No confirmed disparate impact violations detected at standard group level."
            status_color = GREEN
        elif score >= 60:
            status_text = "Moderate fairness concerns detected. Some demographic groups require investigation."
            status_color = AMBER
        else:
            status_text = "Significant disparate impact violations detected. Immediate remediation required."
            status_color = RED

        # Count passing/failing protected classes
        failing = [f for f, r in di_ratios.items() if r < 0.80]
        passing = [f for f, r in di_ratios.items() if r >= 0.80]

        summary_text = (
            f"This analysis covers {len(di_ratios)} protected class attribute(s): "
            f"{', '.join(di_ratios.keys()) or 'none detected'}. "
        )
        if failing:
            summary_text += (
                f"<b>{len(failing)} attribute(s) fall below the 80% disparate impact threshold</b>: "
                f"{', '.join(f.capitalize() for f in failing)}. "
            )
        if passing:
            summary_text += (
                f"{len(passing)} attribute(s) pass the 4/5ths rule: "
                f"{', '.join(f.capitalize() for f in passing)}. "
            )

        story.append(self._p(summary_text, "BodyText2"))
        story.append(Spacer(1, 0.08 * inch))

        # Bottom-line bullet points
        story.append(self._p("<b>Bottom Line:</b>", "BodyText2"))
        bullet_items = []
        if not failing:
            bullet_items.append("No confirmed disparate impact violations at standard group level.")
        else:
            for f in failing:
                r = di_ratios[f]
                rates = approval_rates.get(f, {})
                if rates:
                    best_grp = max(rates, key=rates.get)
                    worst_grp = min(rates, key=rates.get)
                    bullet_items.append(
                        f"{f.capitalize()}: DI ratio {r:.3f} — {worst_grp} applicants approved at "
                        f"{rates[worst_grp]:.1%} vs {best_grp} at {rates[best_grp]:.1%}. "
                        f"Below the 80% threshold — requires investigation."
                    )
        if indicators:
            bullet_items.append(f"{len(indicators)} bias indicator(s) flagged across protected classes.")
        else:
            bullet_items.append("No bias indicators flagged.")

        for item in bullet_items:
            story.append(self._p(f"• {item}", "Finding"))
        story.append(Spacer(1, 0.1 * inch))

        # ── Overall Fairness Score ──────────────────────────────────────────
        story.extend(self._section("Overall Fairness Score"))
        score_data = [
            ["Metric", "Value", "Interpretation"],
            ["Fairness Score", f"{score:.1f} / 100",
             "ACCEPTABLE" if score >= 80 else "NEEDS ATTENTION" if score >= 60 else "HIGH RISK"],
            ["Protected Classes Analyzed", str(len(di_ratios)), f"{', '.join(di_ratios.keys()) or '—'}"],
            ["Bias Indicators Flagged", str(len(indicators)),
             "None" if not indicators else f"{sum(1 for i in indicators if i.severity == 'critical')} critical, "
             f"{sum(1 for i in indicators if i.severity == 'high')} high, "
             f"{sum(1 for i in indicators if i.severity == 'medium')} medium"],
            ["Regulatory Threshold", "80% (4/5ths Rule)", "CFPB / Reg B / ECOA / FHA"],
        ]
        t = Table(score_data, colWidths=[2.5 * inch, 1.5 * inch, 3.0 * inch])
        style = _table_style()
        # Color score row
        score_row_color = colors.HexColor("#E8F5E9") if score >= 80 else colors.HexColor("#FFF9C4") if score >= 60 else colors.HexColor("#FFEBEE")
        style.add("BACKGROUND", (0, 1), (-1, 1), score_row_color)
        t.setStyle(style)
        story.append(t)
        story.append(Spacer(1, 0.1 * inch))

        # ── Disparate Impact Analysis ───────────────────────────────────────
        if di_ratios:
            story.extend(self._section("Disparate Impact Analysis"))
            story.append(self._p(
                "The 4/5ths rule (Uniform Guidelines on Employee Selection Procedures, CFPB Reg B) "
                "requires that the approval rate of any protected group be at least 80% of the "
                "approval rate of the highest-approval reference group. A ratio below 0.80 is a "
                "potential disparate impact concern requiring investigation.",
                "BodyText2",
            ))
            story.append(Spacer(1, 0.06 * inch))

            di_data = [["Protected Class", "DI Ratio", "4/5ths Status", "Notes"]]
            for field, ratio in sorted(di_ratios.items(), key=lambda x: x[1]):
                rates = approval_rates.get(field, {})
                note = ""
                if rates:
                    best = max(rates, key=rates.get)
                    worst = min(rates, key=rates.get)
                    note = f"{worst}: {rates[worst]:.1%} vs {best}: {rates[best]:.1%}"
                status = "PASS ✓" if ratio >= 0.80 else "FAIL ✗"
                di_data.append([field.capitalize(), f"{ratio:.3f}", status, note])

            t = Table(di_data, colWidths=[1.4 * inch, 1.0 * inch, 1.0 * inch, 3.6 * inch])
            style = _table_style()
            for i, row in enumerate(di_data[1:], 1):
                if "FAIL" in row[2]:
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFEBEE"))
                    style.add("TEXTCOLOR", (2, i), (2, i), RED)
                else:
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8F5E9"))
                    style.add("TEXTCOLOR", (2, i), (2, i), GREEN)
            t.setStyle(style)
            story.append(t)

            # DI ratio bar chart
            try:
                di_chart = self._bar_chart(
                    di_ratios, "Disparate Impact Ratios by Protected Class",
                    width=6.5, height=max(1.5, len(di_ratios) * 0.4),
                    threshold=0.80
                )
                story.append(Spacer(1, 0.08 * inch))
                story.append(di_chart)
            except Exception:
                pass
            story.append(Spacer(1, 0.1 * inch))

        # ── Approval Rates by Demographic Group ────────────────────────────
        if approval_rates:
            story.extend(self._section("Approval Rates by Demographic Group"))
            story.append(self._p(
                "Approval rates below are calculated on decisive outcomes only (approved/denied). "
                "Withdrawn, incomplete, and purchased loan applications were excluded per "
                "CFPB standard methodology.",
                "BodyText2",
            ))
            story.append(Spacer(1, 0.06 * inch))

            for field, rates in approval_rates.items():
                if not rates:
                    continue
                story.append(self._p(field.capitalize(), "SubHeading"))

                # Bar chart for this field
                try:
                    chart = self._bar_chart(
                        {k: v for k, v in rates.items()},
                        f"Approval Rate by {field.capitalize()}",
                        width=6.5, height=max(1.8, len(rates) * 0.35),
                        threshold=0.80
                    )
                    story.append(chart)
                    story.append(Spacer(1, 0.05 * inch))
                except Exception:
                    pass

                max_rate = max(rates.values())
                rate_data = [["Group", "Approval Rate", "DI vs Best Group", "Status"]]
                for grp, rate in sorted(rates.items(), key=lambda x: x[1], reverse=True):
                    di = rate / max_rate if max_rate > 0 else 1.0
                    status = "Reference" if abs(di - 1.0) < 0.001 else ("PASS" if di >= 0.80 else "BELOW THRESHOLD")
                    rate_data.append([str(grp), f"{rate:.1%}", f"{di:.3f}", status])
                t = Table(rate_data, colWidths=[2.0 * inch, 1.5 * inch, 1.5 * inch, 2.0 * inch])
                style = _table_style()
                for i, row in enumerate(rate_data[1:], 1):
                    if row[3] == "BELOW THRESHOLD":
                        style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFEBEE"))
                        style.add("TEXTCOLOR", (3, i), (3, i), RED)
                    elif row[3] == "Reference":
                        style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E3F2FD"))
                t.setStyle(style)
                story.append(t)
                story.append(Spacer(1, 0.1 * inch))

        # ── Bias Indicators ──────────────────────────────────────────────────
        if indicators:
            story.extend(self._section("Detected Bias Indicators"))
            story.append(self._p(
                "The following specific group-level violations were flagged. Each represents a "
                "demographic group whose approval rate falls materially below the highest-approval "
                "reference group. Severity levels: Critical (<60%), High (60-70%), Medium (70-80%).",
                "BodyText2",
            ))
            story.append(Spacer(1, 0.06 * inch))
            bi_data = [["Protected Class", "Group", "DI Ratio", "Severity", "Description"]]
            for ind in sorted(indicators, key=lambda x: x.value):
                bi_data.append([
                    ind.field.capitalize(),
                    str(ind.group),
                    f"{ind.value:.3f}",
                    ind.severity.upper(),
                    ind.description[:60] + "…" if len(ind.description) > 60 else ind.description,
                ])
            t = Table(bi_data, colWidths=[1.2 * inch, 1.3 * inch, 0.9 * inch, 0.9 * inch, 2.7 * inch])
            style = _table_style()
            sev_colors = {
                "CRITICAL": colors.HexColor("#FFCDD2"),
                "HIGH":     colors.HexColor("#FFE0B2"),
                "MEDIUM":   colors.HexColor("#FFF9C4"),
            }
            for i, row in enumerate(bi_data[1:], 1):
                bg = sev_colors.get(row[3], colors.white)
                style.add("BACKGROUND", (0, i), (-1, i), bg)
            t.setStyle(style)
            story.append(t)
            story.append(Spacer(1, 0.1 * inch))

        # ── Methodology Note ────────────────────────────────────────────────
        story.extend(self._section("Methodology"))
        story.append(self._p(
            "<b>Outcome Definition:</b> This analysis treats 'Originated' and 'Approved Not Accepted' "
            "as approved outcomes, and 'Denied' as denied. Withdrawn applications, incomplete files, "
            "and purchased loans were excluded because they reflect applicant behavior or loan-purchasing "
            "activity rather than a lender's underwriting decision.",
            "BodyText2",
        ))
        story.append(Spacer(1, 0.05 * inch))
        story.append(self._p(
            "<b>Disparate Impact Ratio:</b> For each protected-class group, the approval rate is divided "
            "by the approval rate of the highest-approval reference group (excluding 'Not Provided' and "
            "'Joint' categories). A ratio below 0.80 is the standard regulatory threshold (4/5ths rule) "
            "for a potential disparate impact concern under ECOA and the Fair Housing Act.",
            "BodyText2",
        ))
        story.append(Spacer(1, 0.05 * inch))
        story.append(self._p(
            "<b>Scoring:</b> The overall fairness score (0–100) is calculated as "
            "100 − Σ(0.80 − DI_ratio) × 100 for each protected class where DI < 0.80. "
            "This gives a proportional, continuous score rather than flat penalty buckets.",
            "BodyText2",
        ))
        story.append(Spacer(1, 0.1 * inch))

        # ── Key Findings ────────────────────────────────────────────────────
        story.extend(self._section("Key Findings"))
        for finding in (fairness_report.findings or []):
            story.append(self._p(f"• {finding}", "Finding"))
        story.append(Spacer(1, 0.1 * inch))

        # ── Recommendations ────────────────────────────────────────────────
        story.extend(self._section("Recommendations"))
        for rec in (fairness_report.recommendations or []):
            story.append(self._p(f"• {rec}", "Finding"))
        story.append(Spacer(1, 0.1 * inch))

        # ── Limitations ────────────────────────────────────────────────────
        story.extend(self._section("Limitations of This Analysis"))
        limitations = [
            "The disparate impact ratio is a screening tool, not a legal determination. "
            "A ratio below 0.80 warrants further investigation; it is not proof of discrimination.",
            "Groups with fewer than 30 decisioned records have limited statistical reliability — "
            "a handful of decisions can swing the ratio substantially.",
            "This analysis covers disparate impact at the group level. It does not constitute "
            "a full ECOA adverse action letter workflow or a complete regulatory examination.",
            "Consult qualified fair lending counsel before taking or reporting regulatory action "
            "based solely on this analysis.",
        ]
        for lim in limitations:
            story.append(self._p(f"• {lim}", "Finding"))

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
        doc = _build_doc(buffer, "Fair Lending Executive Summary")
        story = []

        story.append(Spacer(1, 0.2 * inch))
        story.append(self._p("FAIR LENDING EXECUTIVE SUMMARY", "ReportTitle"))
        story.append(self._p(
            f"Generated: {datetime.utcnow().strftime('%B %d, %Y %H:%M UTC')}   |   "
            f"Dataset: {all_data.get('dataset_name', all_data.get('dataset_id', 'N/A'))}",
            "BodyText2",
        ))
        story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=12))

        # ── Key Metrics ──
        story.extend(self._section("Portfolio Overview"))
        kpi_data = [["Metric", "Value", "Status"]]
        if all_data.get("total_records"):
            kpi_data.append(["Total Applications", f"{all_data['total_records']:,}", "—"])
        if all_data.get("fairness_score") is not None:
            score = float(all_data["fairness_score"])
            status = "ACCEPTABLE" if score >= 80 else "NEEDS ATTENTION" if score >= 60 else "HIGH RISK"
            kpi_data.append(["Fairness Score", f"{score:.1f}/100", status])
        if all_data.get("quality_score"):
            kpi_data.append(["Data Quality Score", f"{all_data['quality_score']:.1f}%", "—"])
        if all_data.get("model_approval_rate"):
            kpi_data.append(["Model Approval Rate", f"{all_data['model_approval_rate']}%", "—"])

        if len(kpi_data) > 1:
            t = Table(kpi_data, colWidths=[2.5 * inch, 2.0 * inch, 2.5 * inch])
            style = _table_style()
            for i, row in enumerate(kpi_data[1:], 1):
                if "HIGH RISK" in str(row[2]):
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFEBEE"))
                elif "NEEDS ATTENTION" in str(row[2]):
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFF9C4"))
                elif "ACCEPTABLE" in str(row[2]):
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8F5E9"))
            t.setStyle(style)
            story.append(t)
            story.append(Spacer(1, 0.1 * inch))

        # ── Disparate Impact ──
        di = all_data.get("disparate_impact_ratios", {})
        if di:
            story.extend(self._section("Disparate Impact Summary"))
            di_data = [["Protected Class", "DI Ratio", "4/5ths Status"]]
            for field, ratio in sorted(di.items(), key=lambda x: float(x[1])):
                r = float(ratio)
                di_data.append([field.capitalize(), f"{r:.3f}", "PASS ✓" if r >= 0.80 else "FAIL ✗"])
            t = Table(di_data, colWidths=[2.0 * inch, 2.0 * inch, 2.5 * inch])
            style = _table_style()
            for i, row in enumerate(di_data[1:], 1):
                if "FAIL" in row[2]:
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFEBEE"))
                    style.add("TEXTCOLOR", (2, i), (2, i), RED)
                else:
                    style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8F5E9"))
                    style.add("TEXTCOLOR", (2, i), (2, i), GREEN)
            t.setStyle(style)
            story.append(t)
            # DI bar chart
            try:
                chart = self._bar_chart(
                    {k: float(v) for k, v in di.items()},
                    "Disparate Impact Ratios", width=6.5,
                    height=max(1.5, len(di) * 0.4), threshold=0.80
                )
                story.append(Spacer(1, 0.06 * inch))
                story.append(chart)
            except Exception:
                pass
            story.append(Spacer(1, 0.1 * inch))

        # ── Approval Rates ──
        approval = all_data.get("approval_rates_by_group", {})
        if approval:
            story.extend(self._section("Approval Rates by Demographic Group"))
            for field, rates in approval.items():
                if not rates:
                    continue
                story.append(self._p(field.capitalize(), "SubHeading"))
                try:
                    chart = self._bar_chart(
                        {str(k): float(v) for k, v in rates.items()},
                        f"Approval Rate by {field.capitalize()}",
                        width=6.5, height=max(1.5, len(rates) * 0.35), threshold=0.80
                    )
                    story.append(chart)
                    story.append(Spacer(1, 0.06 * inch))
                except Exception:
                    pass

        # ── Bias Indicators ──
        bias = all_data.get("bias_indicators", [])
        if bias:
            story.extend(self._section(f"Bias Indicators ({len(bias)} flagged)"))
            bi_data = [["Protected Class", "Group", "DI Ratio", "Severity"]]
            for ind in (bias if isinstance(bias[0], dict) else [b.model_dump() for b in bias]):
                bi_data.append([
                    str(ind.get("field", "")).capitalize(),
                    str(ind.get("group", "")),
                    f"{float(ind.get('value', 0)):.3f}",
                    str(ind.get("severity", "")).upper(),
                ])
            t = Table(bi_data, colWidths=[1.5 * inch, 1.8 * inch, 1.2 * inch, 1.2 * inch])
            sev_colors = {"CRITICAL": colors.HexColor("#FFCDD2"), "HIGH": colors.HexColor("#FFE0B2"), "MEDIUM": colors.HexColor("#FFF9C4")}
            style = _table_style()
            for i, row in enumerate(bi_data[1:], 1):
                style.add("BACKGROUND", (0, i), (-1, i), sev_colors.get(row[3], colors.white))
            t.setStyle(style)
            story.append(t)
            story.append(Spacer(1, 0.1 * inch))

        # ── Findings ──
        findings = all_data.get("findings", [])
        if findings:
            story.extend(self._section("Key Findings"))
            for f in findings:
                story.append(self._p(f"• {f}", "Finding"))
            story.append(Spacer(1, 0.08 * inch))

        # ── Recommendations ──
        recs = all_data.get("recommendations", [])
        if recs:
            story.extend(self._section("Recommendations"))
            for r in recs:
                story.append(self._p(f"• {r}", "Finding"))

        # ── Error/note if dataset not on disk ──
        if all_data.get("error"):
            story.extend(self._section("Note"))
            story.append(self._p(str(all_data["error"]), "BodyText2"))

        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        return buffer.getvalue()
