"""
cover_letter_exporter.py -- Cover Letter PDF Exporter (FIXED v2.0)

WHAT WAS WRONG
--------------
The old version just dumped raw paragraphs with no visual structure.
No header, no applicant info, no date, no styling — just plain text blocks.

WHAT'S FIXED
------------
Produces a fully formatted professional business letter:

  ┌─────────────────────────────────────────────┐
  │  APPLICANT NAME          (large, bold, blue)│
  │  email | phone | location | linkedin        │
  │  ─────────────────────────────────────────  │
  │                                             │
  │  March 29, 2026                             │
  │                                             │
  │  Hiring Manager                             │
  │  Company Name                               │
  │                                             │
  │  Dear Hiring Manager,                       │
  │                                             │
  │  [Body paragraphs — properly spaced,        │
  │   justified, 11pt Helvetica, line-height    │
  │   1.5, indented first line]                 │
  │                                             │
  │  Sincerely,                                 │
  │  Applicant Name                             │
  └─────────────────────────────────────────────┘

The letter_text produced by CoverLetterGenerator already contains
the full letter (header + body + sign-off). This exporter:
  1. Parses out the sections intelligently
  2. Renders each section with its own style
  3. Falls back gracefully if the text is plain paragraphs only
"""

import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter as LETTER_SIZE
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer
)

# Brand colours (match resume PDF)
DARK_BLUE  = colors.HexColor("#1a1a2e")
MID_BLUE   = colors.HexColor("#2c2c54")
GREY       = colors.HexColor("#555555")
LIGHT_GREY = colors.HexColor("#aaaaaa")
BODY_BLACK = colors.HexColor("#1c1c1c")


# ---------------------------------------------------------------------------
# Style definitions
# ---------------------------------------------------------------------------

def _build_styles():
    base = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "CLName", parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=DARK_BLUE,
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    contact_style = ParagraphStyle(
        "CLContact", parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=GREY,
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    date_style = ParagraphStyle(
        "CLDate", parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=GREY,
        spaceBefore=18,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    recipient_style = ParagraphStyle(
        "CLRecipient", parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=BODY_BLACK,
        spaceAfter=3,
        leading=15,
        alignment=TA_LEFT,
    )
    salutation_style = ParagraphStyle(
        "CLSalutation", parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=BODY_BLACK,
        spaceBefore=12,
        spaceAfter=12,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "CLBody", parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=17,
        textColor=BODY_BLACK,
        spaceAfter=10,
        firstLineIndent=0,
        alignment=TA_JUSTIFY,
    )
    closing_style = ParagraphStyle(
        "CLClosing", parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        textColor=BODY_BLACK,
        spaceBefore=14,
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    sig_style = ParagraphStyle(
        "CLSig", parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=DARK_BLUE,
        spaceBefore=2,
        spaceAfter=0,
        alignment=TA_LEFT,
    )

    return {
        "name":       name_style,
        "contact":    contact_style,
        "date":       date_style,
        "recipient":  recipient_style,
        "salutation": salutation_style,
        "body":       body_style,
        "closing":    closing_style,
        "sig":        sig_style,
    }


# ---------------------------------------------------------------------------
# Text parsing helpers
# ---------------------------------------------------------------------------

def _is_salutation(line: str) -> bool:
    l = line.strip().lower()
    return (l.startswith("dear ") or l.startswith("to whom")
            or l.startswith("hello") or l.startswith("hi "))


def _is_closing(line: str) -> bool:
    l = line.strip().lower().rstrip(",")
    return l in ("sincerely", "regards", "best regards", "kind regards",
                 "yours sincerely", "yours faithfully", "respectfully",
                 "warm regards", "best", "thank you")


def _is_date_line(line: str) -> bool:
    """Detect lines like 'March 29, 2026' or '29 March 2026' or '2026-03-29'."""
    months = ("january", "february", "march", "april", "may", "june",
              "july", "august", "september", "october", "november", "december")
    l = line.strip().lower()
    return (any(m in l for m in months) and any(c.isdigit() for c in l)) \
        or bool(re.match(r"\d{4}-\d{2}-\d{2}", l))


def _is_contact_line(line: str) -> bool:
    l = line.strip().lower()
    return "|" in l or "@" in l or re.search(r"\d{7,}", l) is not None


def _split_letter(raw_text: str) -> dict:
    """
    Intelligently parse a cover letter string into labelled sections.
    Returns a dict with keys: name, contact, date, recipient_lines,
                              salutation, body_paras, closing, signature
    """
    result = {
        "name":            "",
        "contact":         "",
        "date":            "",
        "recipient_lines": [],
        "salutation":      "",
        "body_paras":      [],
        "closing":         "",
        "signature":       "",
    }

    if not raw_text or not raw_text.strip():
        return result

    lines = raw_text.strip().splitlines()

    # ── Try to extract structured header block ────────────────────────────────
    # Pattern: first non-empty line = name, then contact, then date, then
    # recipient block, then salutation, then body, then closing + sig.

    idx = 0
    n   = len(lines)

    # Skip leading blank lines
    while idx < n and not lines[idx].strip():
        idx += 1

    if idx >= n:
        result["body_paras"] = [raw_text.strip()]
        return result

    # Line 0: check if it looks like a name (short, no @ or digits-heavy)
    first = lines[idx].strip()
    if (len(first) < 60 and "@" not in first and "|" not in first
            and not _is_date_line(first) and not _is_salutation(first)):
        result["name"] = first
        idx += 1

    # Next: contact line(s)
    while idx < n and _is_contact_line(lines[idx]):
        if result["contact"]:
            result["contact"] += "  |  " + lines[idx].strip()
        else:
            result["contact"] = lines[idx].strip()
        idx += 1

    # Skip blank
    while idx < n and not lines[idx].strip():
        idx += 1

    # Date line
    if idx < n and _is_date_line(lines[idx]):
        result["date"] = lines[idx].strip()
        idx += 1

    # Skip blank
    while idx < n and not lines[idx].strip():
        idx += 1

    # Recipient block: lines before the salutation
    while idx < n and not _is_salutation(lines[idx]) and lines[idx].strip():
        result["recipient_lines"].append(lines[idx].strip())
        idx += 1

    # Skip blank
    while idx < n and not lines[idx].strip():
        idx += 1

    # Salutation
    if idx < n and _is_salutation(lines[idx]):
        result["salutation"] = lines[idx].strip()
        idx += 1

    # Body: collect paragraphs until we hit a closing keyword
    current_para_lines = []

    def _flush_para():
        text = " ".join(current_para_lines).strip()
        if text:
            result["body_paras"].append(text)
        current_para_lines.clear()

    while idx < n:
        line = lines[idx].strip()

        if _is_closing(line):
            _flush_para()
            result["closing"] = line
            idx += 1
            # Everything after closing = signature
            sig_parts = []
            while idx < n:
                sig_line = lines[idx].strip()
                if sig_line:
                    sig_parts.append(sig_line)
                idx += 1
            result["signature"] = sig_parts[0] if sig_parts else ""
            break
        elif not line:
            _flush_para()
        else:
            current_para_lines.append(line)
        idx += 1

    _flush_para()

    return result


# ---------------------------------------------------------------------------
# Main exporter
# ---------------------------------------------------------------------------

class CoverLetterExporter:

    def export_to_pdf(self, letter_text: str, output_path) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=LETTER_SIZE,
            rightMargin=1.0 * inch,
            leftMargin=1.0 * inch,
            topMargin=0.85 * inch,
            bottomMargin=0.85 * inch,
        )

        st    = _build_styles()
        story = []
        parts = _split_letter(letter_text or "")

        # ── Applicant name ────────────────────────────────────────────────────
        if parts["name"]:
            story.append(Paragraph(parts["name"], st["name"]))

        # ── Contact line ──────────────────────────────────────────────────────
        if parts["contact"]:
            story.append(Paragraph(parts["contact"], st["contact"]))

        # ── Divider ───────────────────────────────────────────────────────────
        if parts["name"] or parts["contact"]:
            story.append(Spacer(1, 4))
            story.append(HRFlowable(
                width="100%", thickness=1.5,
                color=DARK_BLUE, spaceAfter=6
            ))

        # ── Date ──────────────────────────────────────────────────────────────
        date_text = parts["date"] or date.today().strftime("%B %d, %Y")
        story.append(Paragraph(date_text, st["date"]))

        # ── Recipient block ───────────────────────────────────────────────────
        if parts["recipient_lines"]:
            story.append(Spacer(1, 6))
            for line in parts["recipient_lines"]:
                story.append(Paragraph(line, st["recipient"]))

        # ── Salutation ────────────────────────────────────────────────────────
        salutation = parts["salutation"] or "Dear Hiring Manager,"
        if not salutation.endswith(","):
            salutation += ","
        story.append(Paragraph(salutation, st["salutation"]))

        # ── Body paragraphs ───────────────────────────────────────────────────
        if parts["body_paras"]:
            for para in parts["body_paras"]:
                if para.strip():
                    story.append(Paragraph(para.strip(), st["body"]))
        else:
            # Fallback: the text had no clear structure — render as-is
            for block in (letter_text or "").strip().split("\n\n"):
                block = block.strip()
                if block:
                    story.append(Paragraph(
                        block.replace("\n", " "), st["body"]
                    ))

        # ── Closing & signature ───────────────────────────────────────────────
        closing = parts["closing"] or "Sincerely"
        if not closing.endswith(","):
            closing += ","
        story.append(Paragraph(closing, st["closing"]))

        if parts["signature"]:
            story.append(Paragraph(parts["signature"], st["sig"]))
        elif parts["name"]:
            story.append(Paragraph(parts["name"], st["sig"]))

        if not story:
            base = getSampleStyleSheet()
            story.append(Paragraph("Cover letter content not available.", base["Normal"]))

        doc.build(story)
        return str(output_path)