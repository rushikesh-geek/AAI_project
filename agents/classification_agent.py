"""
Agent 2 — Document Classification Agent
Classifies documents using rule-based patterns first, LLM for ambiguous cases.
"""
from __future__ import annotations

import re
from typing import Optional

from core.config import ENABLE_LLM_CLASSIFICATION, llm_available
from core.logging_config import get_logger

logger = get_logger(__name__)

# Rule-based keyword patterns (order matters — more specific first)
_RULES: list[tuple[str, list[str], float]] = [
    ("Invoice", [
        r"\binvoice\b", r"\binv[-\s]?\d+", r"\bbill\s+to\b",
        r"\bline\s+item", r"\bgst\b|\bgstin\b", r"\btax\s+invoice\b",
        r"\bsubtotal\b", r"\bamount\s+due\b", r"\bpayment\s+terms\b",
        r"\bunit\s+price\b", r"\bquantity\b",
    ], 0.88),
    ("KYC", [
        r"\bpassport\b", r"\baadhaar\b", r"\bdriving\s+licen[sc]e\b",
        r"\bpan\s+card\b|\bpancard\b", r"\bdate\s+of\s+birth\b|\bdob\b",
        r"\bknow\s+your\s+customer\b|\bkyc\b",
        r"\bnationality\b", r"\bexpiry\s+date\b", r"\bidentity\b",
    ], 0.85),
    ("Contract", [
        r"\bagreement\b", r"\bcontract\b", r"\bhereinafter\b",
        r"\bparty\s+of\s+the\b", r"\bgoverning\s+law\b",
        r"\btermination\b", r"\bforce\s+majeure\b",
        r"\bindemnif", r"\bconfidentiality\b", r"\bliabilit",
    ], 0.85),
    ("Claim", [
        r"\bclaim\b", r"\bclaimant\b", r"\bincident\b",
        r"\binsurance\b", r"\bdamage[sd]?\b", r"\bcompensation\b",
        r"\bloss\s+of\b", r"\bpolicyholder\b",
    ], 0.82),
]


def _rule_based_classify(text: str) -> tuple[Optional[str], float, str]:
    """Returns (doc_type, confidence, explanation)."""
    text_lower = text.lower()
    scores: dict[str, float] = {}

    for doc_type, patterns, base_conf in _RULES:
        matches = sum(1 for p in patterns if re.search(p, text_lower))
        if matches > 0:
            # Scale: 1 match → base_conf * 0.6; all matches → base_conf
            ratio = min(matches / max(len(patterns) * 0.4, 1), 1.0)
            scores[doc_type] = base_conf * (0.5 + 0.5 * ratio)

    if not scores:
        return "Other", 0.5, "No matching patterns found."

    best = max(scores, key=lambda k: scores[k])
    second = sorted(scores.values(), reverse=True)
    conf = scores[best]

    # If two types are close, lower confidence
    if len(second) >= 2 and (second[0] - second[1]) < 0.1:
        conf *= 0.85

    explanation = f"Rule-based: matched {best} patterns (score={conf:.2f})."
    return best, round(conf, 3), explanation


def run(text: str, page_count: int = 1, filename: str = "") -> dict:
    """
    Returns:
      doc_type, confidence, method, explanation
    """
    result = {
        "agent": "ClassificationAgent",
        "status": "success",
        "doc_type": "Other",
        "confidence": 0.5,
        "method": "rule",
        "explanation": "",
        "error": None,
    }

    if not text or len(text.strip()) < 10:
        result["doc_type"] = "Other"
        result["confidence"] = 0.3
        result["explanation"] = "Insufficient text for classification."
        return result

    # Rule-based first
    rule_type, rule_conf, rule_expl = _rule_based_classify(text)

    # If confident enough, return rule result
    if rule_conf >= 0.75:
        result["doc_type"] = rule_type
        result["confidence"] = rule_conf
        result["explanation"] = rule_expl
        result["method"] = "rule"
        return result

    # Try LLM for ambiguous cases
    if ENABLE_LLM_CLASSIFICATION and llm_available():
        try:
            from services.openrouter_client import llm_classify_document
            llm_type, llm_conf, llm_expl = llm_classify_document(text)
            if llm_type and llm_conf > rule_conf:
                result["doc_type"] = llm_type
                result["confidence"] = llm_conf
                result["explanation"] = llm_expl
                result["method"] = "llm"
                return result
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)

    # Fall back to rule result
    result["doc_type"] = rule_type
    result["confidence"] = rule_conf
    result["explanation"] = rule_expl + " (LLM unavailable or not more confident.)"
    return result
