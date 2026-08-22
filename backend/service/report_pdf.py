"""Branded PDF report generator for Duct SEO audit lead emails.

Reads from AuditReport / StructuredAuditData JSON (the same source as AuditReportV1
on the frontend) so content is always consistent. Renders using reportlab — pure Python,
no system deps, safe on Railway.

Duct palette:
  Orange  #ff5c00
  Navy    #0d0f1a
  Cream   #f4ece2
  Gray    #6b7280
"""

from __future__ import annotations

import io
import logging
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Duct brand colours
# ---------------------------------------------------------------------------

ORANGE = colors.HexColor("#ff5c00")
NAVY   = colors.HexColor("#0d0f1a")
CREAM  = colors.HexColor("#f4ece2")
GRAY   = colors.HexColor("#6b7280")
WHITE  = colors.white
RED    = colors.HexColor("#ef4444")
AMBER  = colors.HexColor("#f59e0b")
GREEN  = colors.HexColor("#10b981")
BLUE   = colors.HexColor("#3b82f6")

# Severity → colour mapping matching AuditReportV1
_SEV_COLOR = {
    "fail":        RED,
    "warn":        AMBER,
    "opportunity": ORANGE,
    "pass":        GREEN,
}
_SEV_LABEL = {
    "fail":        "ERROR",
    "warn":        "WARNING",
    "opportunity": "OPP",
    "pass":        "PASS",
}

# Score band colours
def _score_color(score: int) -> Any:
    if score >= 85:
        return GREEN
    if score >= 70:
        return AMBER
    return RED


# ---------------------------------------------------------------------------
# Paragraph styles
# ---------------------------------------------------------------------------

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22,
                             textColor=NAVY, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13,
                             textColor=NAVY, spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10,
                               textColor=NAVY, leading=15, spaceAfter=4),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=9,
                                textColor=GRAY, leading=13),
        "orange": ParagraphStyle("orange", fontName="Helvetica-Bold", fontSize=10,
                                 textColor=ORANGE),
        "win": ParagraphStyle("win", fontName="Helvetica", fontSize=10,
                              textColor=colors.HexColor("#065f46"), leading=14,
                              spaceAfter=3),
        "signal": ParagraphStyle("signal", fontName="Helvetica", fontSize=10,
                                 textColor=NAVY, leading=15, spaceAfter=4,
                                 leftIndent=8),
        "center": ParagraphStyle("center", fontName="Helvetica", fontSize=9,
                                 textColor=GRAY, alignment=TA_CENTER),
    }


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_report_pdf(report_json: dict[str, Any]) -> bytes:
    """Build a branded Duct PDF from an AuditReport JSON dict.

    Accepts the full AuditReport dict (as stored in lead_magnets.report_json).
    Extracts StructuredAuditData from the ``structured_data`` key when present;
    falls back to treating the dict itself as StructuredAuditData (future-proofing).
    Returns raw PDF bytes.
    """
    # Unwrap AuditReport → StructuredAuditData if needed
    data: dict[str, Any] = report_json.get("structured_data") or report_json
    if not data:
        logger.warning("report_pdf: empty data, generating placeholder PDF")
        data = {}

    url            = data.get("url", "your site")
    score          = int(data.get("overall_score", 0))
    score_band     = data.get("score_band", "")
    headline       = data.get("headline", "SEO Audit Report")
    key_signals    = data.get("key_signals", [])
    top_priorities = data.get("top_priorities", [])
    categories     = data.get("categories", [])
    wins           = data.get("wins", [])
    generated_at   = data.get("generated_at", "")[:10]  # date only

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=0,         # header drawn manually
        bottomMargin=14 * mm,
        title=f"SEO Audit — {url}",
        author="Duct · getduct.ai",
    )

    W, H = A4
    inner_w = W - 36 * mm
    s = _styles()
    story = []

    # ── Header bar ────────────────────────────────────────────────────────

    def _header(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        # Full-width orange strip
        canvas.setFillColor(NAVY)
        canvas.rect(0, H - 22 * mm, W, 22 * mm, fill=1, stroke=0)
        # Duct wordmark
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(18 * mm, H - 14 * mm, "DUCT")
        # getduct.ai right-aligned
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(ORANGE)
        canvas.drawRightString(W - 18 * mm, H - 14 * mm, "getduct.ai")
        # Orange underline of header
        canvas.setFillColor(ORANGE)
        canvas.rect(0, H - 23 * mm, W, 1 * mm, fill=1, stroke=0)
        canvas.restoreState()

    def _footer(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFillColor(CREAM)
        canvas.rect(0, 0, W, 10 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAY)
        canvas.drawCentredString(W / 2, 3 * mm,
                                  "Free SEO audit by Duct · getduct.ai/seo-audit")
        canvas.restoreState()

    def _on_page(canvas, doc):  # noqa: ANN001
        _header(canvas, doc)
        _footer(canvas, doc)

    # Spacer to clear the header
    story.append(Spacer(1, 26 * mm))

    # ── Site + date ────────────────────────────────────────────────────────
    story.append(Paragraph(f'<b>{url}</b> · {generated_at}', s["small"]))
    story.append(Spacer(1, 3 * mm))

    # ── Score hero ────────────────────────────────────────────────────────
    sc = _score_color(score)
    score_table = Table(
        [[
            Paragraph(f'<font color="{sc.hexval()}" size="36"><b>{score}</b></font>', s["center"]),
            Paragraph(
                f'<font size="10"><b>/ 100</b></font><br/>'
                f'<font color="{sc.hexval()}" size="11"><b>{score_band.replace("_", " ").title()}</b></font><br/>'
                f'<font size="9" color="{GRAY.hexval()}">{headline}</font>',
                ParagraphStyle("sh", fontName="Helvetica", fontSize=10,
                               textColor=NAVY, leading=16),
            ),
        ]],
        colWidths=[30 * mm, inner_w - 30 * mm],
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CREAM),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [CREAM]),
        ("BOX",     (0, 0), (-1, -1), 1, colors.HexColor("#e5e7eb")),
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 5 * mm))

    # ── Key signals ────────────────────────────────────────────────────────
    if key_signals:
        story.append(Paragraph("Key signals", s["h2"]))
        for sig in key_signals[:3]:
            story.append(Paragraph(f"→ {sig}", s["signal"]))
        story.append(Spacer(1, 3 * mm))

    # ── Fix these first ────────────────────────────────────────────────────
    if top_priorities:
        story.append(Paragraph("Fix these first", s["h2"]))
        rows = [["#", "Finding", "Severity"]]
        for p in top_priorities[:5]:
            sev = p.get("severity", "")
            sev_color = _SEV_COLOR.get(sev, GRAY)
            sev_label = _SEV_LABEL.get(sev, sev.upper())
            rows.append([
                Paragraph(f'<b>{p.get("rank", "")}</b>', s["small"]),
                Paragraph(p.get("title", ""), s["body"]),
                Paragraph(
                    f'<font color="{sev_color.hexval()}"><b>{sev_label}</b></font>',
                    ParagraphStyle("pill", fontName="Helvetica-Bold", fontSize=8,
                                   textColor=sev_color, alignment=TA_CENTER),
                ),
            ])

        t = Table(rows, colWidths=[10 * mm, inner_w - 32 * mm, 22 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, CREAM]),
            ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN",         (0, 0), (0, -1), "CENTER"),
            ("ALIGN",         (2, 0), (2, -1), "CENTER"),
        ]))
        story.append(t)
        story.append(Spacer(1, 5 * mm))

    # ── Category scores ────────────────────────────────────────────────────
    if categories:
        story.append(Paragraph("Category scores", s["h2"]))
        bar_w = inner_w - 50 * mm
        rows = []
        for cat in sorted(categories, key=lambda c: c.get("score", 0)):
            sc_val = int(cat.get("score", 0))
            bar_fill = _score_color(sc_val)
            # Bar drawn as a 2-cell table: filled portion + empty
            fill_pct = sc_val / 100
            bar_tbl = Table(
                [["", ""]],
                colWidths=[bar_w * fill_pct, bar_w * (1 - fill_pct)],
                rowHeights=[4 * mm],
            )
            bar_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), bar_fill),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#e5e7eb")),
                ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING",   (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
            ]))
            rows.append([
                Paragraph(cat.get("label", ""), s["small"]),
                bar_tbl,
                Paragraph(f'<b>{sc_val}</b>', s["small"]),
            ])

        t2 = Table(rows, colWidths=[40 * mm, bar_w, 10 * mm])
        t2.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t2)
        story.append(Spacer(1, 5 * mm))

    # ── What's working ────────────────────────────────────────────────────
    if wins:
        story.append(Paragraph("What's working well", s["h2"]))
        for w in wins[:5]:
            story.append(Paragraph(f"✓  {w}", s["win"]))
        story.append(Spacer(1, 3 * mm))

    # ── CTA ──────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=inner_w, color=colors.HexColor("#e5e7eb"),
                             thickness=0.5, spaceAfter=6))
    story.append(Paragraph(
        'Want a deeper audit with competitor analysis, keyword gaps, and a 90-day action plan? '
        'Visit <font color="#ff5c00"><b>getduct.ai</b></font> or reply to this email.',
        s["small"],
    ))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()
