"""Process multiple job applications from a CSV file."""
import csv
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Callable

from config.settings import settings
from src.analyzers.job_analyzer import JobAnalyzer
from src.tailoring.resume_tailor import ResumeTailor
from src.generators.cover_letter_generator import CoverLetterGenerator
from src.exporters.cover_letter_exporter import CoverLetterExporter
from src.exporters.pdf_generator import PDFResumeGenerator
from src.exporters.docx_generator import DOCXResumeGenerator


class BatchProcessor:

    def __init__(self, structured_resume: dict):
        self.resume   = structured_resume
        self.results: list[dict] = []

    def process_from_csv(
        self,
        csv_path: str,
        tone: str = "professional",
        progress_callback: Callable | None = None,
    ) -> dict:
        jobs      = self._load_csv(csv_path)
        total     = len(jobs)
        results   = []
        failed    = []

        for i, job in enumerate(jobs, 1):
            company  = job.get("company",  "Company")
            position = job.get("position", "Role")

            if progress_callback:
                progress_callback(i, total, f"Processing {company} — {position}")

            try:
                result = self._process_one(job, tone)
                results.append(result)
            except Exception as exc:
                failed.append({"job": job, "error": str(exc)})

        self.results = results
        return {
            "total":      total,
            "successful": len(results),
            "failed":     len(failed),
            "results":    results,
            "failed_jobs": failed,
        }

    def _process_one(self, job: dict, tone: str) -> dict:
        company  = job.get("company",  "Company").replace(" ", "_")
        position = job.get("position", "Role").replace(" ", "_")
        desc     = job.get("description", "")

        ja     = JobAnalyzer().analyze_job_description(desc)
        tailor = ResumeTailor()
        before = tailor.calculate_match_score(self.resume, ja)
        tailored = tailor.tailor_resume(self.resume, ja)
        after  = tailor.calculate_match_score(tailored, ja)

        gen    = CoverLetterGenerator()
        body   = gen.generate_cover_letter(tailored, ja, tone)
        letter = gen.format_full_letter(body, tailored, ja)

        name   = self.resume.get("personal_info", {}).get("full_name", "User").replace(" ", "_")
        folder = settings.OUTPUT_DIR / "batch" / f"{company}_{position}"
        folder.mkdir(parents=True, exist_ok=True)

        resume_pdf = folder / f"{name}_{company}_Resume.pdf"
        cl_pdf     = folder / f"{name}_{company}_CoverLetter.pdf"

        PDFResumeGenerator().generate_resume(tailored, resume_pdf)
        CoverLetterExporter().export_to_pdf(letter, cl_pdf)

        return {
            "company":      job.get("company", ""),
            "position":     job.get("position", ""),
            "match_before": before["overall_score"],
            "match_after":  after["overall_score"],
            "improvement":  round(after["overall_score"] - before["overall_score"], 1),
            "resume_pdf":   str(resume_pdf),
            "cl_pdf":       str(cl_pdf),
        }

    def _load_csv(self, csv_path: str) -> list[dict]:
        rows = []
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k.strip().lower(): v.strip() for k, v in row.items()})
        return rows

    def create_zip(self) -> Path:
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path  = settings.OUTPUT_DIR / f"batch_applications_{ts}.zip"
        batch_dir = settings.OUTPUT_DIR / "batch"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in batch_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(settings.OUTPUT_DIR))

        return zip_path
