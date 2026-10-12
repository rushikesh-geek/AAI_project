"""
Agent 8 — Human Review Routing Agent
Creates and manages review queues. Returns review-ready package for the UI.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from core.logging_config import get_logger
from core.schemas import ProcessingStatus

logger = get_logger(__name__)


def build_review_package(doc_id: str, doc_type: str, extracted: dict,
                         extraction_fields: list[dict],
                         validation_findings: list[dict],
                         reference_findings: list[dict],
                         risk_result: dict) -> dict:
    """
    Assembles a complete review package for the UI.
    Returns dict with all data needed for the Human Review Center.
    """
    all_findings = validation_findings + reference_findings
    critical = [f for f in all_findings if f.get("severity") in ("Critical", "High") and not f.get("passed")]
    warnings = [f for f in all_findings if f.get("severity") in ("Medium", "Low") and not f.get("passed")]

    # Prioritize fields needing attention
    flagged_fields = set(f.get("field") for f in all_findings if not f.get("passed") and f.get("field"))

    return {
        "agent": "ReviewRoutingAgent",
        "doc_id": doc_id,
        "doc_type": doc_type,
        "risk_score": risk_result.get("risk_score", 0.0),
        "risk_label": risk_result.get("risk_label", "Unknown"),
        "processing_status": risk_result.get("processing_status", ProcessingStatus.NEEDS_REVIEW.value),
        "critical_findings": critical,
        "warning_findings": warnings,
        "all_findings": all_findings,
        "flagged_fields": list(flagged_fields),
        "extracted_fields": extraction_fields,
        "extracted_data": extracted,
        "review_priority": _compute_priority(risk_result.get("risk_score", 0.5), len(critical)),
        "recommended_checks": _generate_recommendations(doc_type, all_findings),
    }


def _compute_priority(risk_score: float, critical_count: int) -> str:
    if critical_count >= 2 or risk_score >= 0.7:
        return "P1 — Urgent"
    elif critical_count >= 1 or risk_score >= 0.4:
        return "P2 — High"
    elif risk_score >= 0.2:
        return "P3 — Normal"
    return "P4 — Low"


def _generate_recommendations(doc_type: str, findings: list[dict]) -> list[str]:
    recs = []
    severity_map = {f.get("rule_id", ""): f for f in findings if not f.get("passed")}

    if doc_type == "Invoice":
        if "INV_TOTAL_MISMATCH" in severity_map:
            recs.append("Verify invoice arithmetic — total does not match subtotal + tax.")
        if "REF_VENDOR_UNREGISTERED" in severity_map:
            recs.append("Contact procurement to verify vendor registration.")
        if "INV_DUPLICATE" in severity_map:
            recs.append("Check for duplicate submission before processing payment.")
        if "INV_MISSING_INVOICE_NUMBER" in severity_map:
            recs.append("Request corrected invoice with proper invoice number.")
    elif doc_type == "KYC":
        if "KYC_EXPIRED" in severity_map:
            recs.append("Request renewed identification document from customer.")
    elif doc_type == "Contract":
        if "CTR_EXPIRED" in severity_map:
            recs.append("Contract has expired — initiate renewal process.")
        if "CTR_MISSING_PARTIES" in severity_map:
            recs.append("Verify all contracting parties are clearly identified.")

    if not recs:
        recs.append("Review extraction results and validate against source document.")
    return recs


def record_review_decision(doc_id: str, field_name: str, action: str,
                           original_value: Optional[str], corrected_value: Optional[str],
                           reviewer: str, comment: Optional[str] = None) -> str:
    """Persist a reviewer decision. Returns review_id."""
    review_id = str(uuid.uuid4())[:12].upper()
    decision = {
        "review_id": review_id,
        "doc_id": doc_id,
        "field_name": field_name,
        "original_value": original_value,
        "corrected_value": corrected_value,
        "action": action,
        "reviewer": reviewer,
        "comment": comment,
        "reviewed_at": datetime.utcnow().isoformat(),
    }
    try:
        from core.database import insert_review_decision, insert_audit_event
        insert_review_decision(decision)
        insert_audit_event(
            event_type="REVIEW",
            action=f"Reviewer {action}: {field_name}",
            doc_id=doc_id,
            previous_value=original_value,
            new_value=corrected_value,
            details=comment,
            actor=reviewer,
        )
    except Exception as exc:
        logger.error("Failed to persist review decision: %s", exc)
    return review_id


def get_review_queue(doc_type: Optional[str] = None) -> list[dict]:
    """Return documents in review queue, optionally filtered by type."""
    try:
        from core.database import get_all_documents
        docs = get_all_documents()
        queue = [
            d for d in docs
            if d.get("status") in (ProcessingStatus.NEEDS_REVIEW.value, ProcessingStatus.HIGH_RISK.value)
        ]
        if doc_type:
            queue = [d for d in queue if d.get("doc_type") == doc_type]
        return queue
    except Exception as exc:
        logger.error("Failed to get review queue: %s", exc)
        return []
