"""
DocuMind AI — Core Configuration
Loads settings from environment / .env file.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if it exists
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _getenv(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _getenv_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _getenv_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default


# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / _getenv("UPLOAD_DIR", "data/uploads")
DB_PATH = BASE_DIR / _getenv("DB_PATH", "data/documind.db")
DEMO_DIR = BASE_DIR / "assets" / "demo"
TEMPLATE_DIR = BASE_DIR / "assets" / "templates"

# Ensure directories exist
for _d in (UPLOAD_DIR, DB_PATH.parent, DEMO_DIR, TEMPLATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── OpenRouter ─────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = _getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL: str = _getenv("OPENROUTER_MODEL", "google/gemini-flash-1.5")
OPENROUTER_BASE_URL: str = _getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# ── OCR ────────────────────────────────────────────────────────────────────
TESSERACT_CMD: str = _getenv("TESSERACT_CMD", "tesseract")

# ── Limits ─────────────────────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB: int = _getenv_int("MAX_UPLOAD_SIZE_MB", 50)
MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024
SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}

# ── Processing ─────────────────────────────────────────────────────────────
ENABLE_LLM_CLASSIFICATION: bool = _getenv_bool("ENABLE_LLM_CLASSIFICATION", True)
ENABLE_LLM_EXTRACTION: bool = _getenv_bool("ENABLE_LLM_EXTRACTION", False)
LLM_TIMEOUT_SECONDS: int = _getenv_int("LLM_TIMEOUT_SECONDS", 30)
LLM_MAX_RETRIES: int = _getenv_int("LLM_MAX_RETRIES", 1)
DEMO_MODE: bool = _getenv_bool("DEMO_MODE", True)

# ── Scoring thresholds ──────────────────────────────────────────────────────
LOW_RISK_THRESHOLD: float = 0.35
HIGH_RISK_THRESHOLD: float = 0.70

APP_VERSION = "1.0.0"
APP_NAME = "DocuMind AI"
APP_TAGLINE = "From unstructured documents to verified business records."


def llm_available() -> bool:
    """Returns True when an OpenRouter API key is configured."""
    return bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your_openrouter_api_key_here")
