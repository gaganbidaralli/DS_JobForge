"""
job_analyzer.py  --  Job Description Analyzer  (FIXED v1.2)

BUGS FIXED
----------
1. Frontend crash: "(ja.required_skills || []).map is not a function"
   Root cause: Ollama sometimes returns list fields as a plain comma-separated
   string instead of a JSON array, e.g.:
     "required_skills": "Python, Django, REST APIs"   <-- wrong
   instead of:
     "required_skills": ["Python", "Django", "REST APIs"]  <-- correct
   The frontend calls .map() on these fields and crashes when the value is
   a string (strings are iterable but don't have .map()).
   Fix: _normalize_lists() converts any string/scalar field to a proper list
   immediately after Ollama's response is parsed.

2. timeout=180 -> DEFAULT_TIMEOUT (600 s) from ollama_client.

3. .format() on JSON strings replaced with string concatenation to avoid
   Python treating JSON {} braces as format placeholders.

4. Graceful fallback dict returned when Ollama response is unparseable JSON.
"""

import json
import logging

from src.ollama_client import ollama_generate, DEFAULT_TIMEOUT

log = logging.getLogger(__name__)

# All fields the frontend may call .map() or .forEach() on
_LIST_FIELDS = [
    "required_skills",
    "preferred_skills",
    "responsibilities",
    "requirements",
    "keywords",
    "benefits",
    "culture_keywords",
    "ats_keywords",
    "nice_to_have",
    "qualifications",
    "tools",
    "certifications",
]


def _normalize_lists(data: dict) -> dict:
    """
    Guarantee every expected list field is an actual Python list.
    Called right after JSON parsing so callers and the frontend can
    always call .map() / .forEach() without checking the type first.
    """
    if not isinstance(data, dict):
        return data
    for field in _LIST_FIELDS:
        val = data.get(field)
        if val is None:
            data[field] = []
        elif isinstance(val, str):
            # Ollama returned "Python, Django, REST" -- split into list
            data[field] = [s.strip() for s in val.split(",") if s.strip()]
        elif isinstance(val, dict):
            # Very occasionally Ollama returns {"0": "Python", "1": "Django"}
            data[field] = list(val.values())
        elif not isinstance(val, list):
            data[field] = [str(val)]
        # else: already a proper list, leave it alone
    return data


def _fallback() -> dict:
    """Return a safe empty job-analysis dict when parsing fails."""
    return {field: [] for field in _LIST_FIELDS} | {
        "job_title":  "Unknown",
        "company":    "Unknown",
        "location":   "",
        "employment_type":    "",
        "experience_level":   "",
        "salary_range":       "",
    }


class JobAnalyzer:
    def analyze_job_description(self, description: str,
                                timeout: int = DEFAULT_TIMEOUT) -> dict:
        """
        Send the job description to Ollama and return a normalized dict.
        All list fields are guaranteed to be actual Python lists.
        """
        prompt = (
            "Analyze the following job description and extract structured information.\n"
            "Return ONLY valid JSON with these exact keys (use arrays for list fields):\n"
            "  job_title (string)\n"
            "  company (string)\n"
            "  location (string)\n"
            "  employment_type (string)\n"
            "  experience_level (string)\n"
            "  required_skills (ARRAY of strings)\n"
            "  preferred_skills (ARRAY of strings)\n"
            "  responsibilities (ARRAY of strings)\n"
            "  requirements (ARRAY of strings)\n"
            "  keywords (ARRAY of strings)\n"
            "  salary_range (string)\n"
            "  benefits (ARRAY of strings)\n"
            "  culture_keywords (ARRAY of strings)\n"
            "  ats_keywords (ARRAY of strings)\n\n"
            "IMPORTANT: Every field marked ARRAY must be a JSON array [], "
            "never a comma-separated string.\n"
            "Do NOT include any text outside the JSON object.\n\n"
            "JOB DESCRIPTION:\n"
            + description
        )

        try:
            raw = ollama_generate(prompt, timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError(str(exc)) from exc

        raw = raw.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        # Some models wrap response in extra text before/after the JSON object
        # Try to extract just the {...} portion
        if not raw.startswith("{"):
            start = raw.find("{")
            end   = raw.rfind("}")
            if start != -1 and end != -1:
                raw = raw[start:end+1]

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "Ollama returned non-JSON for job analysis -- using fallback.\n"
                "Raw response (first 300 chars): %s", raw[:300]
            )
            return _fallback()

        # Normalize: guarantee all list fields are actual lists
        return _normalize_lists(result)