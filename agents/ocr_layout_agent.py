"""
Agent 3 — Layout and OCR Agent
Extracts text from PDF (embedded) or images (OCR). Preserves page structure.
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from core.config import TESSERACT_CMD
from core.logging_config import get_logger

logger = get_logger(__name__)

# Check OCR availability at import time
_TESSERACT_AVAILABLE: Optional[bool] = None
_OCR_ERROR: str = ""


def _check_tesseract() -> bool:
    global _TESSERACT_AVAILABLE, _OCR_ERROR
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE
    # Check if tesseract is on PATH or at configured path
    found = shutil.which(TESSERACT_CMD) or shutil.which("tesseract")
    if found:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            _TESSERACT_AVAILABLE = True
            _OCR_ERROR = ""
            logger.info("Tesseract OCR available at: %s", found)
        except Exception as exc:
            _TESSERACT_AVAILABLE = False
            _OCR_ERROR = f"Tesseract found but not working: {exc}"
    else:
        _TESSERACT_AVAILABLE = False
        _OCR_ERROR = (
            "Tesseract OCR not found on PATH. "
            "Install from https://github.com/UB-Mannheim/tesseract/wiki "
            "and add to PATH, or set TESSERACT_CMD in .env"
        )
    return _TESSERACT_AVAILABLE


def ocr_available() -> bool:
    return _check_tesseract()


def ocr_error_message() -> str:
    _check_tesseract()
    return _OCR_ERROR


def _preprocess_image(pil_img):
    """Basic preprocessing: grayscale + threshold to improve OCR."""
    try:
        import cv2
        import numpy as np
        img_array = np.array(pil_img.convert("RGB"))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        # Deskew using moments
        coords = np.column_stack(np.where(gray < 200))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if abs(angle) < 45:
                angle = angle if angle > -45 else 90 + angle
                (h, w) = gray.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                gray = cv2.warpAffine(gray, M, (w, h),
                                      flags=cv2.INTER_CUBIC,
                                      borderMode=cv2.BORDER_REPLICATE)
        # Threshold
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        from PIL import Image
        return Image.fromarray(thresh)
    except Exception:
        return pil_img


def _ocr_image(pil_img, lang: str = "eng") -> tuple[str, float]:
    """Returns (text, confidence)."""
    if not _check_tesseract():
        return "", 0.0
    try:
        import pytesseract
        if TESSERACT_CMD and TESSERACT_CMD != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        data = pytesseract.image_to_data(
            pil_img, lang=lang, output_type=pytesseract.Output.DICT
        )
        confidences = [int(c) for c in data["conf"] if c != -1 and str(c).isdigit()]
        avg_conf = sum(confidences) / len(confidences) / 100.0 if confidences else 0.5
        text = pytesseract.image_to_string(pil_img, lang=lang)
        return text, round(avg_conf, 3)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        return "", 0.0


def _pdf_page_to_pil(doc: fitz.Document, page_idx: int, dpi: int = 200):
    """Render PDF page to PIL Image."""
    from PIL import Image
    page = doc[page_idx]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img


def run(file_path: str, is_image_doc: bool = False,
        embedded_text_available: bool = False) -> dict:
    """
    Returns:
      pages: list of {page_number, text_content, ocr_used, quality_score, word_count}
      full_text: concatenated text
      ocr_used: bool
      language: detected language code
      error: optional
    """
    result = {
        "agent": "OCRLayoutAgent",
        "status": "success",
        "pages": [],
        "full_text": "",
        "ocr_used": False,
        "language": "en",
        "error": None,
    }

    path = Path(file_path)
    if not path.exists():
        result["status"] = "failed"
        result["error"] = f"File not found: {file_path}"
        return result

    ext = path.suffix.lower()

    if ext == ".pdf":
        _extract_pdf(path, embedded_text_available, result)
    else:
        _extract_image_file(path, result)

    # Detect Hindi content
    full = result.get("full_text", "")
    if full and _has_devanagari(full):
        result["language"] = "hi"

    return result


def _extract_pdf(path: Path, embedded_text_available: bool, result: dict) -> None:
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Cannot open PDF: {exc}"
        return

    pages = []
    all_text_parts = []
    ocr_used = False

    for page_num, page in enumerate(doc, 1):
        embedded = page.get_text("text") or ""
        char_count = len(embedded.strip())

        if char_count >= 30:
            # Use embedded text
            word_count = len(embedded.split())
            pages.append({
                "page_number": page_num,
                "text_content": embedded,
                "ocr_used": False,
                "quality_score": 1.0,
                "word_count": word_count,
            })
            all_text_parts.append(embedded)
        else:
            # Try OCR
            if _check_tesseract():
                try:
                    pil_img = _pdf_page_to_pil(doc, page_num - 1)
                    preprocessed = _preprocess_image(pil_img)
                    ocr_text, conf = _ocr_image(preprocessed)
                    ocr_used = True
                    pages.append({
                        "page_number": page_num,
                        "text_content": ocr_text,
                        "ocr_used": True,
                        "quality_score": conf,
                        "word_count": len(ocr_text.split()),
                    })
                    all_text_parts.append(ocr_text)
                except Exception as exc:
                    logger.warning("OCR failed for page %d: %s", page_num, exc)
                    pages.append({
                        "page_number": page_num,
                        "text_content": "[OCR FAILED]",
                        "ocr_used": True,
                        "quality_score": 0.0,
                        "word_count": 0,
                    })
            else:
                pages.append({
                    "page_number": page_num,
                    "text_content": f"[Page {page_num}: Scanned image — OCR unavailable]",
                    "ocr_used": False,
                    "quality_score": 0.0,
                    "word_count": 0,
                })

    doc.close()
    result["pages"] = pages
    result["full_text"] = "\n\n".join(all_text_parts)
    result["ocr_used"] = ocr_used


def _extract_image_file(path: Path, result: dict) -> None:
    try:
        from PIL import Image
        img = Image.open(str(path))
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"Cannot open image: {exc}"
        return

    if _check_tesseract():
        preprocessed = _preprocess_image(img)
        ocr_text, conf = _ocr_image(preprocessed)
        result["pages"] = [{
            "page_number": 1,
            "text_content": ocr_text,
            "ocr_used": True,
            "quality_score": conf,
            "word_count": len(ocr_text.split()),
        }]
        result["full_text"] = ocr_text
        result["ocr_used"] = True
    else:
        result["pages"] = [{
            "page_number": 1,
            "text_content": "[Image file — OCR unavailable. Install Tesseract to extract text.]",
            "ocr_used": False,
            "quality_score": 0.0,
            "word_count": 0,
        }]
        result["full_text"] = ""
        result["error"] = _OCR_ERROR


def _has_devanagari(text: str) -> bool:
    """Detect Hindi/Devanagari script."""
    return any('\u0900' <= c <= '\u097F' for c in text[:500])
