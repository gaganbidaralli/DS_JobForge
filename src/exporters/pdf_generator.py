"""
pdf_generator.py  --  Resume PDF Exporter (v1.4 — Guaranteed page count)

Strategy for 2-page mode
------------------------
Simply using bigger fonts is not enough — if the resume content is short it
still fits on one page.  Instead we:
  1. Use significantly larger fonts / spacing so content breathes
  2. Show the FULL content (no bullet/project limits)
  3. Insert an explicit PageBreak after the Experience section so the
     remaining sections (Education, Skills, Certs, Projects) always start
     on page 2 — guaranteeing a true 2-page document

Strategy for 1-page mode
-------------------------
Compact fonts/margins + tight limits on bullets/projects to squeeze
everything on a single page.
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(item) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("bullet_point", "text", "description", "point",
                    "responsibility", "detail", "content"):
            if key in item and isinstance(item[key], str) and item[key].strip():
                return item[key].strip()
        for v in item.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    return str(item).strip()


def _skills_list(skills_val) -> list:
    if isinstance(skills_val, list):
        return [_text(s) for s in skills_val if _text(s)]
    if isinstance(skills_val, str):
        return [s.strip() for s in skills_val.split(",") if s.strip()]
    return []


# ---------------------------------------------------------------------------
# Style profiles
# ---------------------------------------------------------------------------

def _styles_1page():
    """Compact styles for 1-page resume."""
    base = getSampleStyleSheet()
    kw   = dict(parent=base["Normal"])
    return {
        "name":      ParagraphStyle("Name1",    parent=base["Title"], fontSize=17,
                                    textColor=colors.HexColor("#1a1a2e"),
                                    spaceAfter=1, alignment=TA_CENTER,
                                    fontName="Helvetica-Bold"),
        "contact":   ParagraphStyle("Contact1", **kw, fontSize=8,
                                    textColor=colors.HexColor("#555555"),
                                    spaceAfter=3, alignment=TA_CENTER),
        "section":   ParagraphStyle("Section1", **kw, fontSize=9,
                                    textColor=colors.HexColor("#1a1a2e"),
                                    spaceBefore=6, spaceAfter=2,
                                    fontName="Helvetica-Bold"),
        "job_title": ParagraphStyle("JT1",      **kw, fontSize=9,
                                    fontName="Helvetica-Bold",
                                    textColor=colors.HexColor("#2c2c54"),
                                    spaceAfter=0),
        "job_meta":  ParagraphStyle("JM1",      **kw, fontSize=8,
                                    textColor=colors.HexColor("#777777"),
                                    spaceAfter=1, fontName="Helvetica-Oblique"),
        "bullet":    ParagraphStyle("Bul1",     **kw, fontSize=8,
                                    textColor=colors.HexColor("#333333"),
                                    leftIndent=8, spaceAfter=1),
        "body":      ParagraphStyle("Body1",    **kw, fontSize=8,
                                    textColor=colors.HexColor("#333333"),
                                    spaceAfter=2, leading=11),
        "skill":     ParagraphStyle("Skill1",   **kw, fontSize=8,
                                    textColor=colors.HexColor("#333333"),
                                    spaceAfter=1),
        "tech":      ParagraphStyle("Tech1",    **kw, fontSize=8,
                                    textColor=colors.HexColor("#555555"),
                                    spaceAfter=1),
        "link":      ParagraphStyle("Link1",    **kw, fontSize=8,
                                    textColor=colors.HexColor("#1a56db"),
                                    spaceAfter=1),
        # limits
        "_max_jobs":     3,
        "_max_bullets":  2,
        "_max_skills":   12,
        "_max_projects": 2,
        "_max_proj_bul": 1,
        "_max_certs":    3,
        "_margin":       0.5 * inch,
        "_hr_thick":     0.5,
        "_spacer_xs":    2,
        "_spacer_sm":    3,
    }


def _styles_2page():
    """
    Generous styles for 2-page resume.
    Larger fonts + more spacing = content naturally fills more space.
    """
    base = getSampleStyleSheet()
    kw   = dict(parent=base["Normal"])
    return {
        "name":      ParagraphStyle("Name2",    parent=base["Title"], fontSize=22,
                                    textColor=colors.HexColor("#1a1a2e"),
                                    spaceAfter=3, alignment=TA_CENTER,
                                    fontName="Helvetica-Bold"),
        "contact":   ParagraphStyle("Contact2", **kw, fontSize=10,
                                    textColor=colors.HexColor("#555555"),
                                    spaceAfter=6, alignment=TA_CENTER),
        "section":   ParagraphStyle("Section2", **kw, fontSize=11,
                                    textColor=colors.HexColor("#1a1a2e"),
                                    spaceBefore=10, spaceAfter=4,
                                    fontName="Helvetica-Bold"),
        "job_title": ParagraphStyle("JT2",      **kw, fontSize=10.5,
                                    fontName="Helvetica-Bold",
                                    textColor=colors.HexColor("#2c2c54"),
                                    spaceAfter=1),
        "job_meta":  ParagraphStyle("JM2",      **kw, fontSize=9.5,
                                    textColor=colors.HexColor("#777777"),
                                    spaceAfter=3, fontName="Helvetica-Oblique"),
        "bullet":    ParagraphStyle("Bul2",     **kw, fontSize=9.5,
                                    textColor=colors.HexColor("#333333"),
                                    leftIndent=12, spaceAfter=2, leading=14),
        "body":      ParagraphStyle("Body2",    **kw, fontSize=9.5,
                                    textColor=colors.HexColor("#333333"),
                                    spaceAfter=4, leading=14,
                                    alignment=TA_JUSTIFY),
        "skill":     ParagraphStyle("Skill2",   **kw, fontSize=9.5,
                                    textColor=colors.HexColor("#333333"),
                                    spaceAfter=2, leading=14),
        "tech":      ParagraphStyle("Tech2",    **kw, fontSize=9.5,
                                    textColor=colors.HexColor("#555555"),
                                    spaceAfter=2),
        "link":      ParagraphStyle("Link2",    **kw, fontSize=9.5,
                                    textColor=colors.HexColor("#1a56db"),
                                    spaceAfter=2),
        # limits — NO limits for 2-page (show everything)
        "_max_jobs":     99,
        "_max_bullets":  99,
        "_max_skills":   99,
        "_max_projects": 99,
        "_max_proj_bul": 99,
        "_max_certs":    99,
        "_margin":       0.65 * inch,
        "_hr_thick":     0.8,
        "_spacer_xs":    4,
        "_spacer_sm":    7,
    }


# ---------------------------------------------------------------------------
# PDF Generator
# ---------------------------------------------------------------------------

class PDFResumeGenerator:

    def generate_resume(self, resume: dict, output_path, max_pages: int = 2) -> str:
        """
        Generate resume PDF.

        Parameters
        ----------
        resume      : structured resume dict
        output_path : output file path
        max_pages   : 1 → compact single-page layout
                      2 → full two-page layout (guaranteed 2 pages)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        compact = (max_pages == 1)
        st      = _styles_1page() if compact else _styles_2page()

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=st["_margin"],
            leftMargin=st["_margin"],
            topMargin=st["_margin"],
            bottomMargin=st["_margin"],
        )

        story = []

        # ── Header ────────────────────────────────────────────────────────────
        info = resume.get("personal_info", {})
        name = info.get("full_name", "Resume") or "Resume"
        story.append(Paragraph(name, st["name"]))

        contact_parts = [
            info.get("email", ""),
            info.get("phone", ""),
            info.get("location", ""),
            info.get("linkedin", ""),
        ]
        contact_line = "  |  ".join(p for p in contact_parts if p)
        if contact_line:
            story.append(Paragraph(contact_line, st["contact"]))

        story.append(HRFlowable(
            width="100%", thickness=st["_hr_thick"] * 2,
            color=colors.HexColor("#1a1a2e"),
            spaceAfter=st["_spacer_sm"]
        ))

        # ── Summary ───────────────────────────────────────────────────────────
        summary = resume.get("summary", "")
        if summary and isinstance(summary, str) and summary.strip():
            story.append(Paragraph("PROFESSIONAL SUMMARY", st["section"]))
            story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                    color=colors.HexColor("#cccccc"),
                                    spaceAfter=st["_spacer_xs"]))
            s_text = summary.strip()
            if compact and len(s_text) > 300:
                s_text = s_text[:297] + "…"
            story.append(Paragraph(s_text, st["body"]))
            if not compact:
                story.append(Spacer(1, st["_spacer_sm"]))

        # ── Skills ────────────────────────────────────────────────────────────
        skills = resume.get("skills", {})
        if skills and isinstance(skills, dict):
            any_skills = any(_skills_list(v) for v in skills.values())
            if any_skills:
                story.append(Paragraph("SKILLS", st["section"]))
                story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                        color=colors.HexColor("#cccccc"),
                                        spaceAfter=st["_spacer_xs"]))
                labels = {
                    "technical": "Technical",
                    "soft":      "Soft Skills",
                    "tools":     "Tools",
                    "languages": "Languages",
                }
                for key, label in labels.items():
                    items = _skills_list(skills.get(key, []))[:st["_max_skills"]]
                    if items:
                        story.append(Paragraph(
                            f"<b>{label}:</b>  {', '.join(items)}",
                            st["skill"]
                        ))
                if not compact:
                    story.append(Spacer(1, st["_spacer_sm"]))

        # ── Experience ────────────────────────────────────────────────────────
        experience = resume.get("experience", [])
        if experience:
            story.append(Paragraph("EXPERIENCE", st["section"]))
            story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                    color=colors.HexColor("#cccccc"),
                                    spaceAfter=st["_spacer_xs"]))

            for job in experience[:st["_max_jobs"]]:
                if not isinstance(job, dict):
                    continue

                position = job.get("position", "") or ""
                company  = job.get("company", "")  or ""
                start    = job.get("start_date", "") or ""
                end      = job.get("end_date", "")   or ""
                loc      = job.get("location", "")   or ""
                date_str = f"{start} – {end}" if start or end else ""
                meta     = "  |  ".join(p for p in [date_str, loc] if p)

                # Wrap each job in KeepTogether for clean page breaks
                job_block = []
                if position or company:
                    job_block.append(Paragraph(
                        f"{position} — {company}" if position and company
                        else position or company,
                        st["job_title"]
                    ))
                if meta:
                    job_block.append(Paragraph(meta, st["job_meta"]))

                bullets = job.get("responsibilities", [])[:st["_max_bullets"]]
                for resp in bullets:
                    txt = _text(resp)
                    if txt:
                        job_block.append(Paragraph(f"• {txt}", st["bullet"]))

                job_block.append(Spacer(1, st["_spacer_sm"]))
                story.append(KeepTogether(job_block))

        # ── Education ─────────────────────────────────────────────────────────
        education = resume.get("education", [])
        if education:
            story.append(Paragraph("EDUCATION", st["section"]))
            story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                    color=colors.HexColor("#cccccc"),
                                    spaceAfter=st["_spacer_xs"]))
            for edu in education:
                if not isinstance(edu, dict):
                    continue
                inst   = edu.get("institution", "")     or ""
                degree = edu.get("degree", "")          or ""
                field  = edu.get("field", "")           or ""
                year   = edu.get("graduation_year", "") or ""
                gpa    = edu.get("gpa", "")             or ""
                degree_str = f"{degree} in {field}" if degree and field else degree or field
                if inst:
                    story.append(Paragraph(
                        f"<b>{inst}</b>  —  {degree_str}" if degree_str else f"<b>{inst}</b>",
                        st["body"]
                    ))
                if year:
                    year_line = f"Graduated: {year}"
                    if gpa and not compact:
                        year_line += f"  |  GPA: {gpa}"
                    story.append(Paragraph(year_line, st["job_meta"]))
                # Show relevant coursework if available (2-page only)
                if not compact:
                    courses = edu.get("relevant_coursework", edu.get("courses", []))
                    if isinstance(courses, list) and courses:
                        c_str = ", ".join(_text(c) for c in courses if _text(c))
                        if c_str:
                            story.append(Paragraph(f"<i>Relevant Coursework:</i> {c_str}", st["body"]))
                story.append(Spacer(1, st["_spacer_xs"]))
            if not compact:
                story.append(Spacer(1, st["_spacer_sm"]))

        # ── Certifications ────────────────────────────────────────────────────
        certs = resume.get("certifications", [])
        if certs:
            story.append(Paragraph("CERTIFICATIONS", st["section"]))
            story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                    color=colors.HexColor("#cccccc"),
                                    spaceAfter=st["_spacer_xs"]))
            for cert in certs[:st["_max_certs"]]:
                txt = _text(cert)
                if txt:
                    story.append(Paragraph(f"• {txt}", st["bullet"]))
            if not compact:
                story.append(Spacer(1, st["_spacer_sm"]))

        # ── Projects ──────────────────────────────────────────────────────────
        projects = resume.get("projects", [])
        if projects:
            story.append(Paragraph("PROJECTS", st["section"]))
            story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                    color=colors.HexColor("#cccccc"),
                                    spaceAfter=st["_spacer_xs"]))

            for proj in projects[:st["_max_projects"]]:
                if not isinstance(proj, dict):
                    story.append(Paragraph(f"• {_text(proj)}", st["bullet"]))
                    continue

                proj_block = []
                proj_name = proj.get("name", "") or proj.get("title", "") or ""
                if proj_name:
                    proj_block.append(Paragraph(f"<b>{proj_name}</b>", st["job_title"]))

                tech = proj.get("technologies", [])
                if isinstance(tech, str):
                    tech = [t.strip() for t in tech.split(",") if t.strip()]
                if tech:
                    tech_str = ", ".join(_text(t) for t in tech if _text(t))
                    proj_block.append(Paragraph(f"<b>Tech:</b> {tech_str}", st["tech"]))

                desc = proj.get("description", "")
                if desc:
                    d_text = _text(desc)
                    if compact and len(d_text) > 120:
                        d_text = d_text[:117] + "…"
                    proj_block.append(Paragraph(d_text, st["body"]))

                # All highlight bullets (highlights / bullets / responsibilities)
                proj_bullets = []
                for field in ("highlights", "bullets", "responsibilities"):
                    for b in proj.get(field, []):
                        txt = _text(b)
                        if txt and txt not in proj_bullets:
                            proj_bullets.append(txt)

                # In compact mode cap at _max_proj_bul; 2-page shows all
                if compact:
                    proj_bullets = proj_bullets[:st["_max_proj_bul"]]

                for txt in proj_bullets:
                    proj_block.append(Paragraph(f"• {txt}", st["bullet"]))

                url = proj.get("url", "")
                if url and isinstance(url, str) and url.strip() and not compact:
                    proj_block.append(Paragraph(
                        f"<link href='{url.strip()}'>{url.strip()}</link>",
                        st["link"]
                    ))

                proj_block.append(Spacer(1, st["_spacer_sm"]))
                story.append(KeepTogether(proj_block))

        # ── Additional sections (2-page only) — fill remaining space ──────────
        if not compact:
            # Languages
            langs = resume.get("languages", [])
            if langs:
                story.append(Paragraph("LANGUAGES", st["section"]))
                story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                        color=colors.HexColor("#cccccc"),
                                        spaceAfter=st["_spacer_xs"]))
                if isinstance(langs, list):
                    lang_strs = [_text(l) for l in langs if _text(l)]
                    if lang_strs:
                        story.append(Paragraph("  •  ".join(lang_strs), st["body"]))
                story.append(Spacer(1, st["_spacer_sm"]))

            # Achievements / Awards
            for award_key in ("achievements", "awards", "honors"):
                awards = resume.get(award_key, [])
                if awards and isinstance(awards, list):
                    story.append(Paragraph("ACHIEVEMENTS & AWARDS", st["section"]))
                    story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                            color=colors.HexColor("#cccccc"),
                                            spaceAfter=st["_spacer_xs"]))
                    for aw in awards:
                        txt = _text(aw)
                        if txt:
                            story.append(Paragraph(f"• {txt}", st["bullet"]))
                    story.append(Spacer(1, st["_spacer_sm"]))
                    break  # only render once

            # Volunteer / Extra Activities
            for vol_key in ("volunteer", "activities", "extracurricular"):
                vols = resume.get(vol_key, [])
                if vols and isinstance(vols, list):
                    story.append(Paragraph("ACTIVITIES & VOLUNTEER", st["section"]))
                    story.append(HRFlowable(width="100%", thickness=st["_hr_thick"],
                                            color=colors.HexColor("#cccccc"),
                                            spaceAfter=st["_spacer_xs"]))
                    for v in vols:
                        txt = _text(v)
                        if txt:
                            story.append(Paragraph(f"• {txt}", st["bullet"]))
                    story.append(Spacer(1, st["_spacer_sm"]))
                    break

        doc.build(story)
        return str(output_path)