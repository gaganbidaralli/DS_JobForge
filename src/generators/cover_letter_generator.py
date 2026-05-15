"""Generate cover letters using Ollama."""
import json
from datetime import date
from ..ollama_client import ollama_generate

TONE_INSTRUCTIONS = {
    "professional": "Write in a formal, polished, and professional tone.",
    "enthusiastic": "Write in an energetic, passionate, and enthusiastic tone.",
    "concise":      "Write in a brief, direct, and to-the-point tone. Under 250 words.",
    "creative":     "Write in a unique, memorable, and creative tone.",
}

class CoverLetterGenerator:

    def generate_cover_letter(self, resume: dict, job_analysis: dict, tone: str = "professional") -> str:
        info      = resume.get("personal_info", {})
        exp_list  = resume.get("experience", [])
        skills    = resume.get("skills", {})
        all_skills = []
        for v in skills.values():
            if isinstance(v, list):
                all_skills += v

        current_role = ""
        if exp_list:
            j = exp_list[0]
            current_role = f"{j.get('position', '')} at {j.get('company', '')}"

        tone_inst = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["professional"])

        prompt = (
            "You are an expert cover letter writer.\n"
            f"Tone: {tone_inst}\n\n"
            f"Job Title: {job_analysis.get('job_title', 'the position')}\n"
            f"Company: {job_analysis.get('company', 'the company')}\n"
            f"Required Skills: {', '.join(job_analysis.get('required_skills', [])[:6])}\n\n"
            f"Candidate: {info.get('full_name', 'Candidate')}\n"
            f"Current Role: {current_role}\n"
            f"Key Skills: {', '.join(all_skills[:10])}\n\n"
            "Write ONLY 3–4 body paragraphs (no greeting, no sign-off). "
            "Be specific and compelling."
        )
        return ollama_generate(prompt, timeout=120)

    def format_full_letter(self, body: str, resume: dict, job_analysis: dict) -> str:
        info    = resume.get("personal_info", {})
        name    = info.get("full_name",  "Your Name")
        email   = info.get("email",      "")
        phone   = info.get("phone",      "")
        company = job_analysis.get("company", "Hiring Manager")
        today   = date.today().strftime("%B %d, %Y")

        header = f"{today}\n\n{name}\n{email}"
        if phone:
            header += f" | {phone}"
        header += f"\n\nDear Hiring Manager at {company},\n"
        footer = f"\n\nSincerely,\n{name}\n{email}"
        if phone:
            footer += f"\n{phone}"
        return header + "\n" + body.strip() + footer
