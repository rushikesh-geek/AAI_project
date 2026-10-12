"""
DocuMind AI — Security utilities.
Upload validation, safe path handling, secret scrubbing.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from core.config import MAX_UPLOAD_SIZE_BYTES, SUPPORTED_EXTENSIONS, UPLOAD_DIR


def validate_upload(filename: str, file_bytes: bytes) -> tuple[bool, str]:
    """Return (ok, error_message)."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return False, f"Unsupported file type '{suffix}'. Allowed: {', '.join(SUPPORTED_EXTENSIONS)}"
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        mb = len(file_bytes) / (1024 * 1024)
        return False, f"File too large ({mb:.1f} MB). Maximum allowed: {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB"
    if len(file_bytes) == 0:
        return False, "File is empty."
    return True, ""


def safe_filename(filename: str) -> str:
    """Strip dangerous path characters and return a clean basename."""
    clean = re.sub(r"[^\w.\-]", "_", Path(filename).name)
    return clean[:200] if len(clean) > 200 else clean


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_upload_path(doc_id: str, filename: str) -> Path:
    """Return a safe upload path under UPLOAD_DIR."""
    ext = Path(filename).suffix.lower()
    return UPLOAD_DIR / f"{doc_id}{ext}"


def scrub_secrets(text: str) -> str:
    """Remove API keys and sensitive patterns from text."""
    # Remove common API key patterns
    text = re.sub(r"sk-[a-zA-Z0-9]{32,}", "sk-***REDACTED***", text)
    text = re.sub(r"Bearer [a-zA-Z0-9\-._~+/]+=*", "Bearer ***REDACTED***", text)
    return text


def is_path_safe(path: Path) -> bool:
    """Ensure path is under UPLOAD_DIR to prevent traversal."""
    try:
        path.resolve().relative_to(UPLOAD_DIR.resolve())
        return True
    except ValueError:
        return False
