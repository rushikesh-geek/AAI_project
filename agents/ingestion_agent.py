"""
Agent 1 — Document Ingestion Agent
Validates, stores, and extracts initial metadata from uploaded documents.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from core.config import UPLOAD_DIR
from core.logging_config import get_logger
from core.security import compute_sha256, get_upload_path, validate_upload

logger = get_logger(__name__)


def run(filename: str, file_bytes: bytes, is_demo: bool = False) -> dict:
    """
    Returns result dict with:
      doc_id, file_path, file_hash, page_count, embedded_text_available,
      quality_indicators, error (if any)
    """
    result: dict = {
        "agent": "IngestionAgent",
        "status": "success",
        "doc_id": None,
        "filename": filename,
        "file_path": None,
        "file_hash": None,
        "file_size": len(file_bytes),
        "page_count": 0,
        "embedded_text_available": False,
        "is_image_doc": False,
        "page_info": [],
        "error": None,
        "is_demo": is_demo,
    }

    # 1. Validate
    ok, err_msg = validate_upload(filename, file_bytes)
    if not ok:
        result["status"] = "failed"
        result["error"] = err_msg
        return result

    # 2. Assign ID and hash
    doc_id = str(uuid.uuid4())[:8].upper()
    result["doc_id"] = doc_id
    file_hash = compute_sha256(file_bytes)
    result["file_hash"] = file_hash

    # 3. Save file
    file_path = get_upload_path(doc_id, filename)
    try:
        file_path.write_bytes(file_bytes)
        result["file_path"] = str(file_path)
    except OSError as exc:
        result["status"] = "failed"
        result["error"] = f"Cannot save file: {exc}"
        return result

    # 4. Inspect file
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        _inspect_pdf(file_bytes, result)
    else:
        _inspect_image(file_bytes, ext, result)

    return result


def _inspect_pdf(file_bytes: bytes, result: dict) -> None:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Cannot open PDF: {exc}"
        return

    if doc.is_encrypted:
        result["status"] = "failed"
        result["error"] = "PDF is encrypted/password-protected."
        doc.close()
        return

    result["page_count"] = len(doc)
    page_info = []
    total_chars = 0

    for page_num, page in enumerate(doc, 1):
        text = page.get_text("text") or ""
        char_count = len(text.strip())
        total_chars += char_count
        page_info.append({
            "page_number": page_num,
            "text_length": char_count,
            "has_embedded_text": char_count > 20,
            "width": page.rect.width,
            "height": page.rect.height,
        })

    doc.close()
    result["page_info"] = page_info
    result["embedded_text_available"] = total_chars > 50
    result["is_image_doc"] = total_chars < 50 and result["page_count"] > 0


def _inspect_image(file_bytes: bytes, ext: str, result: dict) -> None:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        result["page_count"] = 1
        result["is_image_doc"] = True
        result["embedded_text_available"] = False
        result["page_info"] = [{
            "page_number": 1,
            "width": img.width,
            "height": img.height,
            "has_embedded_text": False,
            "text_length": 0,
        }]
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Cannot open image: {exc}"


def render_page_image(file_path: str, page_number: int = 1, dpi: int = 150) -> Optional[bytes]:
    """
    Render a PDF page to PNG bytes for display.
    Returns None on failure.
    """
    path = Path(file_path)
    if not path.exists():
        return None

    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            doc = fitz.open(str(path))
            idx = page_number - 1
            if idx >= len(doc):
                idx = 0
            page = doc[idx]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            doc.close()
            return img_bytes
        except Exception as exc:
            logger.warning("Page render failed: %s", exc)
            return None
    else:
        # Image file — return as-is
        try:
            return path.read_bytes()
        except Exception:
            return None
