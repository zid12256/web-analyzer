"""
PDF report generator for Web Application Analyzer.
Usage: called from analyze.py when --pdf flag is passed.
"""

import os
from datetime import datetime
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Colour palette ────────────────────────────────────────────────────────────
C_BG        = colors.HexColor("#0f172a")   # dark navy (header bg)
C_ACCENT    = colors.HexColor("#38bdf8")   # sky blue
C_GREEN     = colors.HexColor("#22c55e")
C_YELLOW    = colors.HexColor("#eab308")
C_RED       = colors.HexColor("#ef4444")
C_CYAN      = colors.HexColor("#06b6d4")
C_TEXT      = colors.HexColor("#1e293b")
C_MUTED     = colors.HexColor("#64748b")
C_RULE      = colors.HexColor("#e2e8f0")
C_ROW_ALT   = colors.HexColor("#f8fafc")
C_CRITICAL_BG = colors.HexColor("#fff1f2")
C_CRITICAL_BORDER = colors.HexColor("#fecdd3")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _score_color(score):
    if score is None:
        return C_MUTED
    if score >= 90:
        return C_GREEN
    if score >= 50:
        return C_YELLOW
    return C_RED


def _score_label(score):
    if score is None:
        return "N/A"
    if score >= 90:
        return f"{score}/100  Good"
    if score >= 50:
        return f"{score}/100  Needs Work"
    return f"{score}/100  Poor"


def _overall_score(results):
    weights = {"performance": 0.3, "seo": 0.25, "accessibility": 0.25, "security": 0.2}
    scores = []
    for key, weight in weights.items():
        s = results.get(key, {}).get("score")
        if s is not None:
            scores.append(s * weight)
    if not scores:
        return None
    denom = sum(weights[k] for k in weights if results.get(k, {}).get("score") is not None)
    return round(sum(scores) / denom)


SEVERITY_ICON  = {"critical": "✗", "warning": "⚠", "ok": "✓", "info": "ℹ"}
SEVERITY_COLOR = {"critical": C_RED, "warning": C_YELLOW, "ok": C_GREEN, "info": C_CYAN}


def _styles():
    base = getSampleStyleSheet()

    def add(name, **kw):
        base.add(ParagraphStyle(name=name, **kw))

    add("ReportTitle",    fontName="Helvetica-Bold", fontSize=22, textColor=colors.white,
        spaceAfter=2, leading=28, alignment=TA_LEFT)
    add("ReportSubtitle", fontName="Helvetica",      fontSize=10, textColor=C_ACCENT,
        spaceAfter=0, leading=14, alignment=TA_LEFT)
    add("ReportDate",     fontName="Helvetica",      fontSize=8,  textColor=colors.white,
        spaceAfter=0, alignment=TA_RIGHT)

    add("SectionHeading", fontName="Helvetica-Bold", fontSize=12, textColor=C_TEXT,
        spaceBefore=10, spaceAfter=4, leading=16)
    add("IssueText",      fontName="Helvetica",      fontSize=9,  textColor=C_TEXT,
        leading=13, spaceAfter=1, wordWrap="CJK")
    add("IssueTextMuted", fontName="Helvetica",      fontSize=8,  textColor=C_MUTED,
        leading=12, spaceAfter=1, wordWrap="CJK")
    add("ScoreBig",       fontName="Helvetica-Bold", fontSize=28, textColor=C_TEXT,
        alignment=TA_CENTER, leading=34)
    add("ScoreLabel",     fontName="Helvetica",      fontSize=8,  textColor=C_MUTED,
        alignment=TA_CENTER, leading=11)
    add("CriticalTitle",  fontName="Helvetica-Bold", fontSize=10, textColor=C_RED,
        spaceBefore=6, spaceAfter=4)
    add("CriticalItem",   fontName="Helvetica",      fontSize=9,  textColor=C_TEXT,
        leading=13, spaceAfter=2, leftIndent=10)
    add("Footer",         fontName="Helvetica",      fontSize=7,  textColor=C_MUTED,
        alignment=TA_CENTER)
    add("MetricLabel",    fontName="Helvetica",      fontSize=8,  textColor=C_TEXT, leading=11)
    add("MetricValue",    fontName="Helvetica-Bold", fontSize=8,  textColor=C_TEXT, leading=11)

    return base


def _header_block(url, score, styles):
    """Dark banner with title + overall score."""
    domain = urlparse(url).netloc or url
    date_str = datetime.now().strftime("%B %d, %Y  %H:%M")

    score_color = _score_color(score)
    score_text  = str(score) + "/100" if score is not None else "N/A"

    # Two-column header table: left = title/url, right = score
    left_cell = [
        Paragraph("Web Analyzer Report", styles["ReportTitle"]),
        Paragraph(url, styles["ReportSubtitle"]),
        Spacer(1, 4),
        Paragraph(date_str, styles["ReportDate"]),
    ]
    right_cell = [
        Paragraph(score_text,
                  ParagraphStyle("BigScore", fontName="Helvetica-Bold", fontSize=32,
                                 textColor=score_color, alignment=TA_RIGHT, leading=38)),
        Paragraph("Overall Health Score",
                  ParagraphStyle("SmallLabel", fontName="Helvetica", fontSize=8,
                                 textColor=colors.white, alignment=TA_RIGHT, leading=11)),
    ]

    tbl = Table([[left_cell, right_cell]],
                colWidths=[PAGE_W - 2 * MARGIN - 55 * mm, 55 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_BG),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (0, -1),  16),
        ("RIGHTPADDING", (1, 0), (1, -1), 16),
    ]))
    return tbl


def _score_cards(results, styles):
    """Row of four score cards: Performance / SEO / Accessibility / Security."""
    sections = ["performance", "seo", "accessibility", "security"]
    cells = []
    for s in sections:
        score = results.get(s, {}).get("score")
        col   = _score_color(score)
        label = _score_label(score)
        cell  = [
            Paragraph(s.title(),
                      ParagraphStyle("CardTitle", fontName="Helvetica-Bold", fontSize=8,
                                     textColor=C_MUTED, alignment=TA_CENTER, leading=11)),
            Spacer(1, 3),
            Paragraph(str(score) if score is not None else "—",
                      ParagraphStyle("CardScore", fontName="Helvetica-Bold", fontSize=20,
                                     textColor=col, alignment=TA_CENTER, leading=24)),
            Paragraph(label.split("  ", 1)[-1] if score is not None else "No data",
                      ParagraphStyle("CardLbl", fontName="Helvetica", fontSize=7,
                                     textColor=C_MUTED, alignment=TA_CENTER, leading=10)),
        ]
        cells.append(cell)

    card_w = (PAGE_W - 2 * MARGIN - 9 * mm) / 4
    tbl = Table([cells], colWidths=[card_w] * 4, rowHeights=[70])
    tbl.setStyle(TableStyle([
        ("BOX",          (0, 0), (0, 0),  0.5, C_RULE),
        ("BOX",          (1, 0), (1, 0),  0.5, C_RULE),
        ("BOX",          (2, 0), (2, 0),  0.5, C_RULE),
        ("BOX",          (3, 0), (3, 0),  0.5, C_RULE),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("COLPADDING",   (0, 0), (-1, -1), 4),
        ("LINEBEFORE",   (1, 0), (3, 0),  0.5, C_RULE),
    ]))
    return tbl


def _safe(text):
    """Escape XML special chars and insert zero-width spaces after / and = so long URLs wrap."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Allow line-break opportunities after slashes and equals in long URLs
    text = text.replace("/", "/&#8203;").replace("=", "=&#8203;")
    return text


def _section_block(title, issues, styles, score=None, details_text=None):
    """Renders one analysis section (Performance, SEO, etc.)."""
    elems = []
    score_str = f"  —  {_score_label(score)}" if score is not None else ""
    elems.append(Paragraph(f"{title}{score_str}", styles["SectionHeading"]))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=C_RULE, spaceAfter=4))

    col_w = PAGE_W - 2 * MARGIN
    icon_w = 14

    for i, issue in enumerate(issues):
        sev  = issue.get("severity", "info")
        msg  = issue.get("msg", "")
        icon = SEVERITY_ICON.get(sev, "·")
        col  = SEVERITY_COLOR.get(sev, C_MUTED)
        hex_col = col.hexval()[2:].upper()

        icon_style = ParagraphStyle(
            f"Icon_{i}", fontName="Helvetica-Bold", fontSize=9,
            textColor=col, leading=13, spaceAfter=0,
        )
        msg_style = ParagraphStyle(
            f"Msg_{i}", fontName="Helvetica", fontSize=9,
            textColor=C_TEXT, leading=13, spaceAfter=0,
        )

        icon_para = Paragraph(f'<font color="#{hex_col}">{icon}</font>', icon_style)
        msg_para  = Paragraph(_safe(msg), msg_style)

        bg = colors.white if i % 2 == 0 else C_ROW_ALT
        row_tbl = Table(
            [[icon_para, msg_para]],
            colWidths=[icon_w, col_w - icon_w],
        )
        row_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        elems.append(row_tbl)

    if details_text:
        elems.append(Spacer(1, 3))
        elems.append(Paragraph(_safe(details_text), styles["IssueTextMuted"]))

    elems.append(Spacer(1, 6))
    return KeepTogether(elems)


def _critical_block(all_critical, styles):
    elems = []
    elems.append(Paragraph("Critical Issues — Fix These First", styles["CriticalTitle"]))

    col_w  = PAGE_W - 2 * MARGIN
    icon_w = 18
    inner_rows = []
    for item in all_critical:
        icon_p = Paragraph(
            "✗",
            ParagraphStyle("CritIcon", fontName="Helvetica-Bold",
                           fontSize=9, textColor=C_RED, leading=13),
        )
        item_p = Paragraph(
            _safe(item),
            ParagraphStyle("CritItem", fontName="Helvetica", fontSize=9,
                           textColor=C_TEXT, leading=13),
        )
        row_tbl = Table([[icon_p, item_p]], colWidths=[icon_w, col_w - icon_w - 16])
        row_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_CRITICAL_BG),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        inner_rows.append(row_tbl)

    outer = Table([[r] for r in inner_rows], colWidths=[col_w])
    outer.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.8, C_RED),
        ("BACKGROUND",    (0, 0), (-1, -1), C_CRITICAL_BG),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    elems.append(outer)
    elems.append(Spacer(1, 8))
    return KeepTogether(elems)


def generate_pdf(url: str, results: dict, output_path: str = None) -> str:
    """Build a PDF report and return the file path."""
    if output_path is None:
        domain = urlparse(url).netloc.replace(".", "_").replace(":", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.getcwd(), f"report_{domain}_{ts}.pdf")

    styles = _styles()
    score  = _overall_score(results)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title=f"Web Analyzer Report — {url}",
        author="Web Application Analyzer",
    )

    story = []

    # Header
    story.append(_header_block(url, score, styles))
    story.append(Spacer(1, 6))

    # Score cards
    story.append(_score_cards(results, styles))
    story.append(Spacer(1, 10))

    # Critical issues summary (at top)
    all_critical = []
    for section, data in results.items():
        for issue in data.get("issues", []):
            if issue.get("severity") == "critical" and not issue["msg"].startswith("  "):
                all_critical.append(f"[{section.upper()}]  {issue['msg']}")
    if all_critical:
        story.append(_critical_block(all_critical, styles))

    # Performance
    if "performance" in results:
        perf = results["performance"]
        ssl  = perf.get("details", {})
        detail = None
        if perf.get("opportunities"):
            tops = sorted(perf["opportunities"], key=lambda x: -x.get("savings_ms", 0))[:3]
            detail = "Top opportunities: " + " | ".join(
                f"{o['title']} (~{o['savings_ms']}ms)" for o in tops
            )
        story.append(_section_block("Performance", perf.get("issues", []),
                                    styles, perf.get("score"), detail))

    # SEO
    if "seo" in results:
        seo = results["seo"]
        story.append(_section_block("SEO", seo.get("issues", []), styles, seo.get("score")))

    # Accessibility
    if "accessibility" in results:
        a11y = results["accessibility"]
        story.append(_section_block("Accessibility", a11y.get("issues", []),
                                    styles, a11y.get("score")))

    # Security
    if "security" in results:
        sec = results["security"]
        d   = sec.get("details", {})
        detail = None
        if d.get("tls_version"):
            detail = (f"TLS: {d['tls_version']}  |  "
                      f"SSL expires: {d.get('ssl_expires', 'N/A')} "
                      f"({d.get('ssl_days_left', '?')} days remaining)")
        story.append(_section_block("Security", sec.get("issues", []),
                                    styles, sec.get("score"), detail))

    # Links
    if "links" in results:
        links = results["links"]
        d = links.get("details", {})
        detail = None
        if d.get("total_links"):
            detail = (f"Total links: {d['total_links']}  |  "
                      f"Internal: {d['internal']}  |  External: {d['external']}")
        story.append(_section_block("Links & Assets", links.get("issues", []),
                                    styles, None, detail))

    # Footer
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_RULE))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generated by Web Application Analyzer  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  {url}",
        styles["Footer"],
    ))

    doc.build(story)
    return output_path
