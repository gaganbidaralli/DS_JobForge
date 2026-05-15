"""Central settings loaded from .env"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    INPUT_DIR:  Path = BASE_DIR / os.getenv("INPUT_DIR",  "data/input")
    OUTPUT_DIR: Path = BASE_DIR / os.getenv("OUTPUT_DIR", "data/output")
    OLLAMA_URL:   str = os.getenv("OLLAMA_URL",   "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    EMAIL_ADDRESS:  str = os.getenv("EMAIL_ADDRESS",  "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
    SECRET_KEY: str = os.getenv("FLASK_SECRET", "dev-secret-change-me")
    PORT:       int = int(os.getenv("FLASK_PORT", "5000"))
    DEBUG:      bool = os.getenv("FLASK_DEBUG", "true").lower() == "true"

settings = Settings()
settings.INPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
