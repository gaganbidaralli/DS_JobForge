"""
main.py  --  Resume parsing entry point  (FIXED v1.2)

BUGS FIXED
----------
1. Curly braces / dict repr in resume bullet points
   Root cause: Ollama sometimes returns responsibilities as a list of dicts:
     [{"bullet_point": "Did X", "metric": "", "date_range": ""}]
   instead of a plain list of strings:
     ["Did X"]
   The PDF/DOCX generators called str() on each item, producing the raw
   dict repr: {'bullet_point': 'Did X', 'metric': '', 'date_range': ''}
   Fix: _normalize_resume() extracts the text from any dict bullet and
   converts it to a plain string before the data leaves this module.

2. .format() swallows JSON braces -- already fixed, preserved here.
"""
import json
import re
from pathlib import Path

from .parsers.pdf_parser  import extract_text_pdf
from .parsers.docx_parser import extract_text_docx
from .parsers.txt_parser  import extract_text_txt
from .ollama_client       import ollama_generate


# ---------------------------------------------------------------------------
# Prompt (concatenation -- NOT .format() to avoid brace collisions)
# ---------------------------------------------------------------------------

PARSE_PROMPT_PREFIX = """You are a professional resume parser.
Extract the following fields from the resume text and return ONLY valid JSON.
Do NOT include any markdown, code fences, or explanation -- just the JSON object.

IMPORTANT: responsibilities must be a plain JSON array of strings, like:
  "responsibilities": ["Did X", "Did Y", "Did Z"]
NOT a list of objects.

Return this exact JSON structure with real values filled in:
"""

PARSE_PROMPT_TEMPLATE = """{
  "personal_info": {
    "full_name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
    "github": ""
  },
  "summary": "",
  "experience": [
    {
      "company": "",
      "position": "",
      "start_date": "",
      "end_date": "",
      "location": "",
      "responsibilities": ["string", "string"]
    }
  ],
  "education": [
    {
      "institution": "",
      "degree": "",
      "field": "",
      "graduation_year": ""
    }
  ],
  "skills": {
    "technical": [],
    "soft": [],
    "tools": [],
    "languages": []
  },
  "certifications": [],
  "projects": [
    {
      "name": "",
      "description": "",
      "technologies": [],
      "highlights": ["string", "string"],
      "url": ""
    }
  ]
}"""

PARSE_PROMPT_SUFFIX = """

IMPORTANT RULES:
- Extract ALL projects from the resume, even if only partially described.
- For each project: fill name, description (1-2 sentences), technologies (list of tech used),
  highlights (list of key achievements/features as plain strings), and url if mentioned.
- If no projects exist in the resume, return "projects": [].
- responsibilities must be plain strings, not objects.

Resume text:
{resume_text}

Return ONLY the JSON object. No explanation, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Normalizer  (the critical fix)
# ---------------------------------------------------------------------------

def _bullet_to_str(item) -> str:
    """
    Convert a bullet point to a plain string regardless of how Ollama returned it.

    Handles all observed Ollama output formats:
      "Did X"                                          -> "Did X"
      {"bullet_point": "Did X", "metric": "", ...}    -> "Did X"
      {"text": "Did X"}                               -> "Did X"
      {"description": "Did X"}                        -> "Did X"
      {"point": "Did X"}                              -> "Did X"
      {"0": "Did X"}                                  -> "Did X"
    """
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        # Try known key names in priority order
        for key in ("bullet_point", "text", "description", "point",
                    "responsibility", "detail", "content"):
            if key in item and isinstance(item[key], str) and item[key].strip():
                return item[key].strip()
        # Fallback: return the first non-empty string value found
        for v in item.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    return str(item).strip()


def _normalize_resume(data: dict) -> dict:
    """
    Walk the parsed resume dict and ensure every responsibilities/bullets list
    contains plain strings, not dicts.  Also normalises skills lists.
    """
    if not isinstance(data, dict):
        return data

    # Fix experience responsibilities
    for job in data.get("experience", []):
        raw = job.get("responsibilities", [])
        if isinstance(raw, list):
            job["responsibilities"] = [
                s for s in (_bullet_to_str(r) for r in raw) if s
            ]
        elif isinstance(raw, str):
            job["responsibilities"] = [s.strip() for s in raw.split("\n") if s.strip()]

    # Fix projects bullets if they exist
    for proj in data.get("projects", []):
        for field in ("bullets", "responsibilities", "highlights", "description"):
            raw = proj.get(field)
            if isinstance(raw, list):
                proj[field] = [s for s in (_bullet_to_str(r) for r in raw) if s]
            elif isinstance(raw, str) and field != "description":
                proj[field] = [s.strip() for s in raw.split("\n") if s.strip()]

    # Fix skills -- ensure they are lists of strings
    skills = data.get("skills", {})
    if isinstance(skills, dict):
        for k, v in skills.items():
            if isinstance(v, str):
                skills[k] = [s.strip() for s in v.split(",") if s.strip()]
            elif isinstance(v, list):
                skills[k] = [_bullet_to_str(s) for s in v if _bullet_to_str(s)]
    elif isinstance(skills, list):
        # Some models return skills as a flat list
        data["skills"] = {"technical": [_bullet_to_str(s) for s in skills]}

    # Fix certifications
    certs = data.get("certifications", [])
    if isinstance(certs, list):
        data["certifications"] = [_bullet_to_str(c) for c in certs if _bullet_to_str(c)]

    return data


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_resume(file_path: str) -> dict:
    path = Path(file_path)
    ext  = path.suffix.lower()

    if ext == ".pdf":
        text = extract_text_pdf(str(path))
    elif ext in (".docx", ".doc"):
        text = extract_text_docx(str(path))
    else:
        text = extract_text_txt(str(path))

    if not text.strip():
        raise ValueError("Could not extract any text from the resume file.")

    prompt = (
        PARSE_PROMPT_PREFIX
        + PARSE_PROMPT_TEMPLATE
        + PARSE_PROMPT_SUFFIX.replace("{resume_text}", text[:8000])
    )

    response = ollama_generate(prompt)

    # Robustly extract JSON from Ollama's response
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        cleaned = re.sub(r"```(?:json)?", "", response).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(
                    f"AI returned invalid JSON.\nResponse: {response[:500]}"
                )

    # CRITICAL: normalize before returning so no caller ever sees dict bullets
    return _normalize_resume(data)