"""Tailor a resume to a job description — preserves ALL sections including projects.
Supports verbose=True mode for 2-page resumes (more bullets, richer descriptions).
"""
import json
import re
import copy
from ..ollama_client import ollama_generate

# ── Prompt for standard (1-page) tailoring ────────────────────────────────────
TAILOR_PROMPT_COMPACT = """You are an expert resume writer. Rewrite the resume JSON to better match the job requirements.

CRITICAL RULES:
1. Return ONLY valid JSON in the EXACT same schema as the input resume — same keys, same structure.
2. DO NOT fabricate facts. Keep company names, dates, education, and project names accurate.
3. PRESERVE all sections: personal_info, summary, experience, education, skills, certifications, projects.
4. If the resume has projects, you MUST include ALL of them in the output with enhanced descriptions.
5. Update the summary to target the specific role (2-3 sentences).
6. Each job: write 3-4 strong bullet points with action verbs and metrics where supported.
7. Add/strengthen skills that match job requirements (only skills the person plausibly has).
8. responsibilities and highlights must be plain string arrays, NOT arrays of objects.

Job Requirements:
{job_summary}

Current Resume:
{resume_json}

Return ONLY the improved resume JSON. No markdown, no explanation, no code fences."""


# ── Prompt for verbose (2-page) tailoring ─────────────────────────────────────
TAILOR_PROMPT_VERBOSE = """You are a senior professional resume writer specializing in comprehensive two-page resumes.
Your goal is to create a DETAILED, CONTENT-RICH resume that fully FILLS two pages with zero empty space.

CRITICAL RULES:
1. Return ONLY valid JSON in the EXACT same schema as the input resume — same keys, same structure.
2. DO NOT fabricate facts. Keep company names, dates, education, and project names accurate.
3. PRESERVE all sections: personal_info, summary, experience, education, skills, certifications, projects.
4. responsibilities and highlights must be plain string arrays, NOT arrays of objects.

CONTENT EXPANSION REQUIREMENTS — this is the MOST IMPORTANT part:

SUMMARY: Write a rich EXACTLY 5-sentence professional summary (minimum 80 words total). Cover:
  sentence 1 — years of experience and core domain
  sentence 2 — primary technical skills and platforms
  sentence 3 — a concrete key achievement with a metric
  sentence 4 — collaboration, leadership, or cross-functional impact
  sentence 5 — career goal aligned directly to this specific role

EXPERIENCE — for EACH job write EXACTLY 5-6 bullet points:
  - Start each bullet with a strong action verb (Architected, Engineered, Led, Delivered, Optimized, Spearheaded, Collaborated, Designed, Implemented, Reduced, Increased, Automated, Streamlined)
  - Include quantified metrics wherever possible (percentages, time saved, users served, team size, revenue impact)
  - Expand each responsibility into a full, detailed sentence (20-35 words each)
  - Highlight tools, technologies, and methodologies used in context
  - Show business impact and outcomes, not just tasks

PROJECTS — for EACH project write AT MINIMUM 5 detailed bullet points in the "highlights" array:
  - bullet 1: project purpose and the problem it solves
  - bullet 2: your specific technical role and architecture decisions
  - bullet 3: key technologies, frameworks, and tools used
  - bullet 4: a quantified result or measurable outcome (performance, users, uptime, etc.)
  - bullet 5: challenges overcome or innovations introduced
  Also include: a 2-3 sentence description, and list ALL relevant technologies.

SKILLS: Expand each skill category with ALL relevant skills from the job description that the candidate plausibly has.

EDUCATION: Include relevant coursework, honors, or achievements if known.

Job Requirements:
{job_summary}

Current Resume:
{resume_json}

Return ONLY the improved resume JSON with maximum detail. No markdown, no explanation, no code fences."""


class ResumeTailor:

    def tailor_resume(self, resume: dict, job_analysis: dict,
                      verbose: bool = False) -> dict:
        """
        Tailor resume to job description.

        Parameters
        ----------
        resume       : structured resume dict
        job_analysis : job analysis dict
        verbose      : True → 2-page mode (richer prompts, more content)
                       False → 1-page mode (concise)
        """
        job_summary = self._summarize_job(job_analysis, verbose=verbose)
        resume_json = json.dumps(resume, indent=2)

        # For verbose mode keep full content; for compact, compress if too large
        if not verbose and len(resume_json) > 5000:
            resume_json = self._compress_resume(resume)
        elif verbose and len(resume_json) > 8000:
            # In verbose mode we still compress but keep more bullets
            resume_json = self._compress_resume(resume, max_bullets=5)

        template = TAILOR_PROMPT_VERBOSE if verbose else TAILOR_PROMPT_COMPACT
        prompt = (template
                  .replace("{job_summary}", job_summary)
                  .replace("{resume_json}", resume_json))

        # Verbose mode needs a bigger token budget for richer output
        token_budget = 8192 if verbose else 4096
        response = ollama_generate(prompt, timeout=300, num_predict=token_budget)

        tailored = self._parse_response(response)
        if tailored is None:
            return copy.deepcopy(resume)

        # Preserve projects if tailor dropped them
        if not tailored.get("projects") and resume.get("projects"):
            tailored["projects"] = resume["projects"]

        tailored = self._normalize(tailored, resume)

        # In verbose mode, ensure minimum bullet count per job
        if verbose:
            tailored = self._ensure_verbose_content(tailored, resume)

        return tailored

    # ── Job summary builder ───────────────────────────────────────────────────

    def _summarize_job(self, ja: dict, verbose: bool = False) -> str:
        lines = []
        if ja.get("job_title"):
            lines.append(f"Role: {ja['job_title']}")
        if ja.get("company"):
            lines.append(f"Company: {ja['company']}")

        req = ja.get("required_skills", [])
        if req:
            limit = 20 if verbose else 15
            lines.append(f"Required skills: {', '.join(req[:limit])}")

        pref = ja.get("preferred_skills", [])
        if pref:
            limit = 15 if verbose else 10
            lines.append(f"Preferred skills: {', '.join(pref[:limit])}")

        kw = ja.get("keywords", [])
        if kw:
            limit = 20 if verbose else 15
            lines.append(f"Keywords: {', '.join(kw[:limit])}")

        resp = ja.get("responsibilities", [])
        if resp:
            lines.append("Key responsibilities:")
            limit = 8 if verbose else 5
            for r in resp[:limit]:
                lines.append(f"  - {r}")

        if verbose:
            reqs = ja.get("requirements", [])
            if reqs:
                lines.append("Requirements:")
                for r in reqs[:5]:
                    lines.append(f"  - {r}")

        return "\n".join(lines)

    # ── Compression ───────────────────────────────────────────────────────────

    def _compress_resume(self, resume: dict, max_bullets: int = 3) -> str:
        r = copy.deepcopy(resume)
        for job in r.get("experience", []):
            job["responsibilities"] = job.get("responsibilities", [])[:max_bullets]
        return json.dumps(r, indent=2)

    # ── Verbose content enforcer ──────────────────────────────────────────────

    def _ensure_verbose_content(self, tailored: dict, original: dict) -> dict:
        """
        Post-process: if AI returned fewer than 4 bullets per job,
        pad with expanded versions of the original bullets.
        """
        orig_jobs = {
            (j.get("company", "") + j.get("position", "")): j
            for j in original.get("experience", [])
            if isinstance(j, dict)
        }

        for job in tailored.get("experience", []):
            if not isinstance(job, dict):
                continue
            resps = job.get("responsibilities", [])
            if len(resps) >= 4:
                continue  # AI already gave enough bullets

            # Find original matching job to pull from
            key = (job.get("company", "") + job.get("position", ""))
            orig_job = orig_jobs.get(key, {})
            orig_resps = orig_job.get("responsibilities", [])

            # Pad with any remaining original bullets not already present
            for orig_bullet in orig_resps:
                txt = self._to_str(orig_bullet)
                if txt and txt not in resps and len(resps) < 6:
                    resps.append(txt)

            job["responsibilities"] = resps

        # Ensure projects have at least 5 highlight bullets
        MIN_PROJ_BULLETS = 5
        for proj in tailored.get("projects", []):
            if not isinstance(proj, dict):
                continue
            # Collect existing bullets across all bullet fields
            existing = []
            for f in ("highlights", "bullets", "responsibilities"):
                existing += [self._to_str(b) for b in proj.get(f, []) if self._to_str(b)]

            # If fewer than minimum, pad with generated placeholder lines from description
            if len(existing) < MIN_PROJ_BULLETS:
                desc = self._to_str(proj.get("description", ""))
                name = self._to_str(proj.get("name", proj.get("title", "this project")))
                tech_list = proj.get("technologies", [])
                tech_str = ", ".join(self._to_str(t) for t in tech_list if self._to_str(t)) if tech_list else "modern technologies"
                # Generate padding bullets from available context
                padding = [
                    f"Developed {name} to solve a real-world problem using {tech_str}.",
                    f"Designed the system architecture and selected appropriate technologies for scalability.",
                    f"Implemented core functionality using {tech_str}, ensuring reliability and performance.",
                    f"Conducted thorough testing and debugging to achieve a stable and production-ready release.",
                    f"Documented the project architecture and deployment steps to support future development.",
                ]
                for pad_bullet in padding:
                    if pad_bullet not in existing and len(existing) < MIN_PROJ_BULLETS:
                        existing.append(pad_bullet)

            proj["highlights"] = existing

        return tailored

    # ── JSON parser ───────────────────────────────────────────────────────────

    def _parse_response(self, response: str):
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        cleaned = re.sub(r"```(?:json)?", "", response).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _normalize(self, tailored: dict, original: dict) -> dict:
        for job in tailored.get("experience", []):
            raw = job.get("responsibilities", [])
            if isinstance(raw, list):
                job["responsibilities"] = [
                    self._to_str(r) for r in raw if self._to_str(r)
                ]
            elif isinstance(raw, str):
                job["responsibilities"] = [s.strip() for s in raw.split("\n") if s.strip()]

        for proj in tailored.get("projects", []):
            if not isinstance(proj, dict):
                continue
            for field in ("highlights", "bullets", "responsibilities"):
                raw = proj.get(field, [])
                if isinstance(raw, list):
                    proj[field] = [self._to_str(r) for r in raw if self._to_str(r)]
                elif isinstance(raw, str):
                    proj[field] = [s.strip() for s in raw.split("\n") if s.strip()]
            tech = proj.get("technologies", [])
            if isinstance(tech, str):
                proj["technologies"] = [t.strip() for t in tech.split(",") if t.strip()]

        skills = tailored.get("skills", {})
        if isinstance(skills, dict):
            for k, v in skills.items():
                if isinstance(v, str):
                    skills[k] = [s.strip() for s in v.split(",") if s.strip()]
                elif isinstance(v, list):
                    skills[k] = [self._to_str(s) for s in v if self._to_str(s)]

        return tailored

    def _to_str(self, item) -> str:
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            for key in ("bullet_point", "text", "description", "point", "highlight",
                        "responsibility", "detail", "content"):
                if key in item and isinstance(item[key], str) and item[key].strip():
                    return item[key].strip()
            for v in item.values():
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""
        return str(item).strip()

    # ── Match score ───────────────────────────────────────────────────────────

    def calculate_match_score(self, resume: dict, job_analysis: dict) -> dict:
        resume_text = json.dumps(resume).lower()
        req_skills  = [s.lower() for s in job_analysis.get("required_skills",  [])]
        pref_skills = [s.lower() for s in job_analysis.get("preferred_skills", [])]
        keywords    = [k.lower() for k in job_analysis.get("keywords",          [])]

        all_skills = []
        for v in resume.get("skills", {}).values():
            if isinstance(v, list):
                all_skills += [s.lower() for s in v if isinstance(s, str)]

        req_matched  = sum(1 for s in req_skills  if s in all_skills or s in resume_text)
        pref_matched = sum(1 for s in pref_skills if s in all_skills or s in resume_text)
        kw_matched   = sum(1 for k in keywords    if k in resume_text)

        skill_score = 0
        if req_skills:  skill_score += (req_matched  / len(req_skills))  * 35
        if pref_skills: skill_score += (pref_matched / len(pref_skills)) * 15

        kw_score  = (kw_matched / max(len(keywords), 1)) * 30

        exp_score = 0
        if resume.get("experience"): exp_score += 10
        if resume.get("summary"):    exp_score += 5
        if resume.get("education"):  exp_score += 5

        overall = round(min(skill_score + kw_score + exp_score, 100), 1)
        return {
            "overall_score":    overall,
            "skill_score":      round(skill_score, 1),
            "keyword_score":    round(kw_score, 1),
            "experience_score": exp_score,
        }
