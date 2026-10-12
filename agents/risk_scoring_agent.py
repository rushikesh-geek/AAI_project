"""
Agent 7 — Confidence and Anomaly Scoring Agent
Computes a transparent, documented risk score for each document.
"""
from __future__ import annotations

from typing import Any

from core.config import LOW_RISK_THRESHOLD, HIGH_RISK_THRESHOLD
from core.logging_config import get_logger
from core.schemas import ProcessingStatus

logger = get_logger(__name__)


def run(doc_type: str, extracted: dict, validation_findings: list[dict],
        reference_findings: list[dict], extraction_fields: list[dict],
        ingestion_result: dict) -> dict:
    """
    Returns:
      risk_score: float 0.0–1.0
      risk_label: str
      status: ProcessingStatus str
      score_breakdown: dict explaining each component
      confidence: float extraction confidence
    """
    score = 0.0
    breakdown: dict[str, float] = {}

    # ── Component 1: Missing mandatory fields ──────────────────────────────
    mandatory_by_type = {
        "Invoice": ["vendor_name", "invoice_number", "invoice_date", "stated_total"],
        "KYC": ["full_name", "document_number", "document_type"],
        "Contract": ["effective_date"],
        "Claim": ["claimant_name", "claim_id", "claim_amount"],
    }
    mandatory = mandatory_by_type.get(doc_type, [])
    missing = sum(1 for f in mandatory if not extracted.get(f))
    missing_penalty = (missing / max(len(mandatory), 1)) * 0.25
    score += missing_penalty
    breakdown["missing_fields"] = round(missing_penalty, 3)

    # ── Component 2: Validation failures ──────────────────────────────────
    all_findings = validation_findings + reference_findings
    severity_weights = {"Critical": 0.20, "High": 0.12, "Medium": 0.07, "Low": 0.03, "Info": 0.0}
    validation_penalty = 0.0
    for f in all_findings:
        if not f.get("passed"):
            validation_penalty += severity_weights.get(f.get("severity", "Low"), 0.03)
    validation_penalty = min(validation_penalty, 0.40)
    score += validation_penalty
    breakdown["validation_failures"] = round(validation_penalty, 3)

    # ── Component 3: Extraction confidence ────────────────────────────────
    confidences = [f.get("confidence", 1.0) for f in extraction_fields if f.get("confidence") is not None]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
    conf_penalty = (1.0 - avg_conf) * 0.15
    score += conf_penalty
    breakdown["low_extraction_confidence"] = round(conf_penalty, 3)

    # ── Component 4: Duplicate detection ──────────────────────────────────
    duplicate_penalty = 0.0
    if any(f.get("rule_id") in ("INV_DUPLICATE",) for f in all_findings):
        duplicate_penalty = 0.20
    score += duplicate_penalty
    breakdown["duplicate_document"] = round(duplicate_penalty, 3)

    # ── Component 5: OCR quality ───────────────────────────────────────────
    ocr_used = ingestion_result.get("is_image_doc", False)
    page_info = ingestion_result.get("page_info", [])
    low_quality_pages = sum(1 for p in page_info if p.get("quality_score", 1.0) < 0.6)
    ocr_penalty = (low_quality_pages / max(len(page_info), 1)) * 0.10 if ocr_used else 0.0
    score += ocr_penalty
    breakdown["ocr_quality"] = round(ocr_penalty, 3)

    score = round(min(score, 1.0), 4)

    # ── Determine status ───────────────────────────────────────────────────
    has_critical = any(
        f.get("severity") in ("Critical", "High") and not f.get("passed")
        for f in all_findings
    )

    if score < LOW_RISK_THRESHOLD and not has_critical:
        status = ProcessingStatus.READY.value
        risk_label = "Low Risk"
    elif score < HIGH_RISK_THRESHOLD or (has_critical and score < HIGH_RISK_THRESHOLD + 0.1):
        status = ProcessingStatus.NEEDS_REVIEW.value
        risk_label = "Medium Risk"
    else:
        status = ProcessingStatus.HIGH_RISK.value
        risk_label = "High Risk"

    return {
        "agent": "RiskScoringAgent",
        "status": "success",
        "risk_score": score,
        "risk_label": risk_label,
        "processing_status": status,
        "score_breakdown": breakdown,
        "extraction_confidence": round(avg_conf, 3),
        "has_critical_findings": has_critical,
        "error": None,
    }
