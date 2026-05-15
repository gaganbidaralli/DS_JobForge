"""
LaunchPad Settings Configuration
"""

import os
from pathlib import Path

class Settings:
    """Application settings"""
    
    # Base directories
    BASE_DIR = Path(__file__).parent.parent
    INPUT_DIR = BASE_DIR / "data" / "input"
    OUTPUT_DIR = BASE_DIR / "data" / "output"
    
    # Create directories if they don't exist
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # API Settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("DEBUG", "True").lower() == "true"
    
    # Ollama Settings
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama2")
    
    # Email Settings (optional)
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
    
    def __repr__(self):
        return f"<Settings port={self.PORT} ollama={self.OLLAMA_URL}>"

# Global settings instance
settings = Settings()
