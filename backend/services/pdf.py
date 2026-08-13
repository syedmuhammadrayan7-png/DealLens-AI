"""Printable, multi-page PDF renderer. It consumes a completed report only."""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.schemas.case import DueDiligenceReport, Evidence, EvidenceStatus

NAVY, CYAN, INK, MUTED = colors.HexColor("#0B1B2D"), colors.HexColor("#067C9E"), colors.HexColor("#17212B"), colors.HexColor("#526171")


def _escape(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7DEE5")); canvas.line(0.6 * inch, 0.52 * inch, 7.9 * inch, 0.52 * inch)
    canvas.setFont("Helvetica", 7); canvas.setFillColor(MUTED)
    canvas.drawString(0.6 * inch, 0.35 * inch, "DealLens AI | Due Diligence Intelligence")
    canvas.drawRightString(7.9 * inch, 0.35 * inch, f"Decision support only - not investment advice. | Page {doc.page}")
    canvas.restoreState()


def _evidence_block(title: str, items: list[Evidence], styles) -> list:
    story = [Paragraph(title, styles["section"])]
    if not items:
        return story + [Paragraph(f"No {title.lower()} identified.", styles["muted"]), Spacer(1, 8)]
    for item in items:
        source = item.source_name or item.source or "Source unavailable"
        detail = f"{item.status.value.replace('_', ' ').title()} | {source}"
        if item.confidence is not None: detail += f" | Confidence {item.confidence}%"
        if item.source_url: detail += f" | <link href='{_escape(item.source_url)}' color='#067C9E'>{_escape(item.source_url)}</link>"
        story += [KeepTogether([Paragraph(_escape(item.statement), styles["body"]), Paragraph(detail, styles["meta"]), Paragraph(_escape(item.notes), styles["muted"]) if item.notes else Spacer(1, 5)])]
    return story + [Spacer(1, 8)]


def render_report_pdf(report: DueDiligenceReport) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.62 * inch, leftMargin=0.62 * inch, topMargin=0.62 * inch, bottomMargin=0.75 * inch, title="DealLens AI - Investment Memo")
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("DealLensTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, alignment=TA_LEFT, spaceAfter=6),
        "subtitle": ParagraphStyle("DealLensSub", parent=base["Normal"], fontSize=9, leading=12, textColor=MUTED, spaceAfter=14),
        "section": ParagraphStyle("DealLensSection", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=NAVY, spaceBefore=12, spaceAfter=6, keepWithNext=True),
        "body": ParagraphStyle("DealLensBody", parent=base["BodyText"], fontSize=9.4, leading=13.3, textColor=INK, spaceAfter=3),
        "meta": ParagraphStyle("DealLensMeta", parent=base["Normal"], fontSize=7.8, leading=10, textColor=CYAN, spaceAfter=2),
        "muted": ParagraphStyle("DealLensMuted", parent=base["Normal"], fontSize=8.3, leading=11.5, textColor=MUTED, spaceAfter=4),
        "bullet": ParagraphStyle("DealLensBullet", parent=base["BodyText"], fontSize=9.2, leading=13, leftIndent=12, firstLineIndent=-9, textColor=INK, spaceAfter=3),
    }
    timestamp = report.generated_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    story = [Paragraph("DealLens AI - Investment Memo", styles["title"]), Paragraph(f"Company: <b>{_escape(report.company_name)}</b> &nbsp;&nbsp; Sector: {_escape(report.sector)} &nbsp;&nbsp; Stage: {_escape(report.funding_stage)}<br/>Case ID: {_escape(report.case_id)}<br/>Generated: {_escape(timestamp)}<br/>Decision-support report - not investment advice.", styles["subtitle"])]
    summary = [["Overall score", "Risk level", "Confidence", "Recommendation"], [f"{report.overall_score} / 100", report.risk_level.value, report.confidence_level, report.recommendation.value]]
    table = Table(summary, colWidths=[1.3 * inch, 1.25 * inch, 1.15 * inch, 3.1 * inch])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#EDF4F7")), ("TEXTCOLOR", (0, 1), (-1, 1), INK), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C5D2DA")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [table, Paragraph("Investment Thesis", styles["section"]), Paragraph(_escape(report.investment_thesis), styles["body"]), Paragraph("Recommendation rationale", styles["section"]), Paragraph(_escape(report.recommendation_reason or "Recommendation is based on the score, confidence, and documented evidence gaps."), styles["body"]), Paragraph("Auditable Scorecard", styles["section"])]
    for breakdown in report.score_breakdowns:
        rows = [[f"{breakdown.category}: {breakdown.score} / 100", f"Confidence: {breakdown.confidence}"]] + [[f"+{item.points} / {item.max_points or item.points} {item.label}", item.note] for item in breakdown.contributing_factors] + [[f"{item.points} / {item.max_points or abs(item.points)} {item.label}", item.note] for item in breakdown.deductions]
        score_table = Table([[Paragraph(_escape(cell), styles["body"]) for cell in row] for row in rows], colWidths=[2.2 * inch, 4.55 * inch])
        score_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F5F8")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6E0E6")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story += [KeepTogether([score_table, Spacer(1, 7)])]
    story += [Paragraph("Key Strengths", styles["section"])] + ([Paragraph(f"• {_escape(item)}", styles["bullet"]) for item in report.strengths] or [Paragraph("No strengths were identified from the available evidence.", styles["muted"])])
    story += [Paragraph("Red Flags / Risks", styles["section"])] + ([Paragraph(f"• {_escape(item)}", styles["bullet"]) for item in report.red_flags] or [Paragraph("No red flags were identified from the available evidence.", styles["muted"])])
    story += [PageBreak()]
    groups = [("Verified Evidence", [item for item in report.verified_evidence if item.status == EvidenceStatus.VERIFIED]), ("Supported Evidence", [item for item in report.verified_evidence if item.status == EvidenceStatus.SUPPORTED]), ("Public Company Claims", [item for item in report.verified_evidence if item.status == EvidenceStatus.PUBLIC_COMPANY_CLAIM]), ("Founder-Provided Claims", report.founder_provided_claims), ("Unverified Claims", report.unverified_claims), ("Conflicting Evidence", report.conflicting_evidence), ("Unavailable Evidence", report.unavailable_evidence)]
    for title, items in groups: story += _evidence_block(title, items, styles)
    story += [Paragraph("Investor Questions", styles["section"])] + ([Paragraph(f"• {_escape(item)}", styles["bullet"]) for item in report.investor_questions] or [Paragraph("No investor questions were generated.", styles["muted"])])
    story += [Paragraph("Additional Verification Required", styles["section"])] + ([Paragraph(f"• {_escape(item)}", styles["bullet"]) for item in report.additional_verification_required] or [Paragraph("No additional verification items were listed.", styles["muted"])])
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
