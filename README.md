# 🚀 JobForge — AI Job Application Generator

A fully local, AI-powered job application generator. Upload your resume, paste a
job description, and get a perfectly tailored resume + cover letter in seconds —
powered by **Ollama** (100% free, runs on your machine).

---

## 🐛 Bugs Fixed in This Version

### Bug 1 — Resume Content Showing as `{full_name}` / `{email}` (curly braces)
**Root cause:** Prompts used Python's `.format()` on strings containing JSON `{}` braces.
Python treated every `{"key": ""}` in the JSON schema as a format placeholder.
**Fix:** All prompts now use string concatenation (`+`) instead of `.format()`.
Affected files: `src/main.py`, `src/analyzers/job_analyzer.py`,
`src/tailoring/resume_tailor.py`, `src/generators/cover_letter_generator.py`

### Bug 2 — LinkedIn Bot Stops Mid-Application
**Root causes:**
- "Save this application?" dialog appeared but bot had no handler → froze & exited
- Easy Apply button selectors were outdated (LinkedIn changed their HTML)
- Flask's 60-second readline loop killed the bot process mid-application
**Fixes:**
- `_handle_save_dialog()` called before every card click, after Easy Apply, and
  inside every form step loop
- 7 updated Easy Apply button selectors tried in order
- Bot now runs as fully detached background process (`start_new_session=True`)
- Flask returns immediately; frontend polls `/api/linkedin/status` for live output

---

## 📁 Project Structure

```
jobforge/
├── api.py                              ← Flask REST API (entry point)
├── requirements.txt
├── .env                                ← Your config (edit this)
├── .gitignore
├── README.md
│
├── config/
│   ├── __init__.py
│   └── settings.py                     ← Loads settings from .env
│
├── frontend/
│   └── index.html                      ← Complete self-contained frontend
│
├── src/
│   ├── __init__.py
│   ├── main.py                         ← Resume parsing (BUG FIXED)
│   ├── ollama_client.py                ← Ollama HTTP wrapper
│   ├── parsers/
│   │   ├── pdf_parser.py
│   │   ├── docx_parser.py
│   │   └── txt_parser.py
│   ├── analyzers/
│   │   └── job_analyzer.py             ← JD analysis (BUG FIXED)
│   ├── tailoring/
│   │   └── resume_tailor.py            ← Resume tailoring (BUG FIXED)
│   ├── generators/
│   │   └── cover_letter_generator.py   ← Cover letter (BUG FIXED)
│   ├── exporters/
│   │   ├── pdf_generator.py
│   │   ├── docx_generator.py
│   │   └── cover_letter_exporter.py
│   ├── ats/
│   │   └── ats_analyzer.py
│   ├── batch/
│   │   └── batch_processor.py
│   ├── email/
│   │   └── email_sender.py
│   └── automation/
│       └── linkedin_bot_playwright.py  ← LinkedIn bot (BUG FIXED)
│
└── data/
    ├── input/                          ← Uploaded resumes + CSVs
    └── output/                         ← Generated PDFs, DOCXs, ZIPs
```

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.11+ (NOT 3.14 — use 3.11 for best compatibility)
- [Ollama](https://ollama.com) installed and running

```bash
ollama serve
ollama pull llama3.2
```

### 2. Install

```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install --prefer-binary -r requirements.txt

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
pip install --prefer-binary -r requirements.txt
```

### 3. Configure `.env`
Edit `.env` with your details (Ollama URL, email credentials, etc.)

### 4. Run

```bash
python api.py
```

Open **http://localhost:5000**

---

## 🔌 LinkedIn Bot Setup (optional)

```bash
pip install playwright
playwright install chromium
```

---

## 📧 Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Generate a 16-character app password
3. Add to `.env`: `EMAIL_PASSWORD=xxxx xxxx xxxx xxxx`

---

## 🛠 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Health check + Ollama status |
| GET | `/api/ollama/test` | Test Ollama connection |
| POST | `/api/resume/upload` | Upload resume file |
| POST | `/api/resume/parse` | Parse resume with AI |
| POST | `/api/generate` | Full pipeline: tailor + cover letter |
| POST | `/api/export/resume/pdf` | Download resume as PDF |
| POST | `/api/export/resume/docx` | Download resume as DOCX |
| POST | `/api/export/coverletter/pdf` | Download cover letter as PDF |
| POST | `/api/ats/analyze` | ATS compatibility check |
| POST | `/api/batch/upload` | Upload jobs CSV |
| POST | `/api/batch/process` | Process all CSV jobs |
| GET  | `/api/batch/download` | Download batch ZIP |
| POST | `/api/email/send` | Send application email |
| POST | `/api/linkedin/start` | Launch LinkedIn bot |
| GET  | `/api/linkedin/status` | Poll bot live output |
| POST | `/api/linkedin/stop` | Stop running bot |
| GET  | `/api/history` | Session history |
| POST | `/api/session/clear` | Clear session |

---

## 🔒 Privacy

Everything runs locally — Ollama on your machine, files in `data/`, no external API calls.
