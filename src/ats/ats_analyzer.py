"""ATS compatibility analyzer — heuristic scoring, no AI calls needed."""
import json


class ATSAnalyzer:

    def analyze_resume(self, resume: dict, job_analysis: dict) -> dict:
        resume_text = json.dumps(resume).lower()

        kw_result    = self._score_keywords(resume_text, resume, job_analysis)
        fmt_result   = self._score_format(resume)
        cont_result  = self._score_content(resume)
        skill_result = self._score_skills(resume, job_analysis)

        overall = kw_result["score"] + fmt_result["score"] + cont_result["score"] + skill_result["score"]

        recs = (
            kw_result.get("recommendations", []) +
            fmt_result.get("recommendations", []) +
            cont_result.get("recommendations", []) +
            skill_result.get("recommendations", [])
        )

        return {
            "overall_score":  round(overall, 1),
            "grade":          self._grade(overall),
            "keyword_score":  kw_result["score"],
            "format_score":   fmt_result["score"],
            "content_score":  cont_result["score"],
            "skills_score":   skill_result["score"],
            "recommendations": recs,
            "keyword_details": kw_result["details"],
            "format_details":  fmt_result["details"],
            "skills_details":  skill_result["details"],
        }

    def _score_keywords(self, resume_text: str, resume: dict, job: dict) -> dict:
        req_kws  = [k.lower() for k in job.get("required_skills", [])]
        pref_kws = [k.lower() for k in job.get("preferred_skills", [])]
        all_kws  = list(dict.fromkeys(req_kws + pref_kws + [k.lower() for k in job.get("keywords", [])]))

        matched = [k for k in all_kws if k in resume_text]
        missing = [k for k in all_kws if k not in resume_text]
        density = {k: resume_text.count(k) for k in matched}
        rate    = len(matched) / max(len(all_kws), 1)
        score   = round(rate * 40, 1)

        recs = []
        if missing[:5]:
            recs.append(f"Add missing keywords to your resume: {', '.join(missing[:5])}")

        return {
            "score": score,
            "details": {
                "matched": matched, "missing": missing,
                "match_rate": round(rate * 100, 1), "density": density,
            },
            "recommendations": recs,
        }

    def _score_format(self, resume: dict) -> dict:
        score  = 20
        checks = []
        issues = []
        recs   = []

        info = resume.get("personal_info", {})
        if info.get("email"):   checks.append("Email address present")
        else:                   issues.append("Missing email"); score -= 4; recs.append("Add email to contact info")

        if info.get("phone"):   checks.append("Phone number present")
        else:                   issues.append("Missing phone"); score -= 2; recs.append("Add phone number")

        if resume.get("experience"): checks.append("Work experience section present")
        else:                        issues.append("No work experience section"); score -= 6

        if resume.get("education"):  checks.append("Education section present")
        else:                        issues.append("No education section"); score -= 3

        if resume.get("skills"):     checks.append("Skills section present")
        else:                        issues.append("No skills section"); score -= 4; recs.append("Add a dedicated skills section")

        if len(json.dumps(resume)) > 500: checks.append("Resume has sufficient content")
        else:                             issues.append("Resume content seems too brief"); score -= 3

        return {
            "score": max(score, 0),
            "details": {"checks": checks, "issues": issues},
            "recommendations": recs,
        }

    def _score_content(self, resume: dict) -> dict:
        score = 0
        recs  = []

        if resume.get("summary"):    score += 5
        else: recs.append("Add a professional summary targeting the role")

        exp = resume.get("experience", [])
        if exp:
            score += 5
            action_verbs = ["led","built","developed","managed","increased","reduced",
                            "designed","implemented","delivered","improved","created",
                            "launched","optimised","architected","mentored","shipped"]
            exp_text = json.dumps(exp).lower()
            if sum(1 for v in action_verbs if v in exp_text) >= 5:
                score += 5
            else:
                recs.append("Use more strong action verbs in experience bullets")

        if resume.get("education"):      score += 3
        if resume.get("certifications"): score += 2

        return {"score": min(score, 20), "details": {}, "recommendations": recs}

    def _score_skills(self, resume: dict, job: dict) -> dict:
        skills_obj = resume.get("skills", {})
        all_resume_skills = []
        for v in skills_obj.values():
            if isinstance(v, list):
                all_resume_skills += [s.lower() for s in v]

        resume_full = json.dumps(resume).lower()
        req  = [s.lower() for s in job.get("required_skills", [])]
        pref = [s.lower() for s in job.get("preferred_skills", [])]

        matched_req  = [s for s in req  if s in all_resume_skills or s in resume_full]
        missing_req  = [s for s in req  if s not in all_resume_skills and s not in resume_full]
        matched_pref = [s for s in pref if s in all_resume_skills]

        req_rate  = len(matched_req)  / max(len(req),  1)
        pref_rate = len(matched_pref) / max(len(pref), 1)
        score     = round(req_rate * 15 + pref_rate * 5, 1)

        recs = []
        if missing_req:
            recs.append(f"Add required skills you have: {', '.join(missing_req[:4])}")

        return {
            "score": min(score, 20),
            "details": {
                "matched_required": matched_req,
                "missing_required": missing_req,
                "matched_preferred": matched_pref,
            },
            "recommendations": recs,
        }

    def _grade(self, score: float) -> str:
        if score >= 90: return "A+"
        if score >= 80: return "A"
        if score >= 70: return "B+"
        if score >= 60: return "B"
        return "C"
