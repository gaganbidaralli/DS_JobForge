"""Extract text from PDF files."""
from pathlib import Path


def extract_text_pdf(file_path: str) -> str:
    path = Path(file_path)
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        if text.strip():
            return text
    except Exception:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise RuntimeError(f"PDF extraction failed: {exc}")
