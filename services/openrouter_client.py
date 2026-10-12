"""
DocuMind AI — OpenRouter LLM client.
All LLM calls go through here. Fails gracefully when unconfigured.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from core.config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL,
    LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES, llm_available
)
from core.logging_config import get_logger

logger = get_logger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None and llm_available():
        try:
            from openai import OpenAI
            _client = OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except ImportError:
            logger.warning("openai package not installed — LLM unavailable")
    return _client


def llm_complete(
    prompt: str,
    system: str = "You are a document analysis assistant. Be precise and concise.",
    max_tokens: int = 512,
    temperature: float = 0.0,
    model: str = None,
    response_format: str = "text",   # "text" | "json"
) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (result_text, error_message).
    result_text is None when the call fails.
    """
    if not llm_available():
        return None, "LLM not configured — no API key."

    client = _get_client()
    if client is None:
        return None, "LLM client initialization failed."

    _model = model or OPENROUTER_MODEL
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": _model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            return content.strip(), None
        except Exception as exc:
            err = str(exc)
            logger.warning("LLM attempt %d/%d failed: %s", attempt + 1, LLM_MAX_RETRIES + 1, err)
            if attempt < LLM_MAX_RETRIES:
                time.sleep(1.5 ** attempt)
            else:
                return None, f"LLM error after {LLM_MAX_RETRIES + 1} attempts: {err}"

    return None, "Unknown LLM error."


def llm_classify_document(text_snippet: str) -> tuple[Optional[str], float, str]:
    """
    Returns (doc_type, confidence, explanation).
    doc_type: Invoice | KYC | Contract | Claim | Other
    """
    prompt = f"""Classify the following document excerpt into exactly one category:
Invoice, KYC, Contract, Claim, or Other.

Document excerpt (first 800 chars):
---
{text_snippet[:800]}
---

Respond with valid JSON only:
{{"type": "Invoice", "confidence": 0.92, "explanation": "Contains vendor name, invoice number, line items and totals."}}
"""
    result, err = llm_complete(prompt, max_tokens=200, response_format="json")
    if err or not result:
        return None, 0.0, f"LLM unavailable: {err}"
    try:
        data = json.loads(result)
        doc_type = data.get("type", "Other")
        confidence = float(data.get("confidence", 0.5))
        explanation = data.get("explanation", "")
        # Validate type
        valid = {"Invoice", "KYC", "Contract", "Claim", "Other"}
        if doc_type not in valid:
            doc_type = "Other"
        return doc_type, min(max(confidence, 0.0), 1.0), explanation
    except (json.JSONDecodeError, ValueError) as exc:
        # Retry with raw parse
        for t in ("Invoice", "KYC", "Contract", "Claim"):
            if t.lower() in (result or "").lower():
                return t, 0.6, "Parsed from LLM text response."
        return "Other", 0.3, f"Could not parse LLM response: {exc}"


def llm_extract_fields(text: str, doc_type: str) -> tuple[Optional[dict], Optional[str]]:
    """Returns (fields_dict, error). Only called when ENABLE_LLM_EXTRACTION=True."""
    type_hints = {
        "Invoice": "vendor_name, invoice_number, invoice_date, due_date, po_number, stated_total, tax_amount, currency",
        "KYC": "full_name, document_type, document_number, date_of_birth, expiry_date, address",
        "Contract": "parties (list), effective_date, expiry_date, payment_terms, termination_notice, governing_law",
        "Claim": "claimant_name, claim_id, incident_date, claim_amount, claim_type",
    }
    hint = type_hints.get(doc_type, "key fields")
    prompt = f"""Extract fields from this {doc_type} document.
Fields to extract: {hint}.
Return null for missing fields. Never invent values.

Document text (max 1200 chars):
---
{text[:1200]}
---

Return valid JSON with the extracted fields only.
"""
    result, err = llm_complete(prompt, max_tokens=600, response_format="json")
    if err or not result:
        return None, err
    try:
        return json.loads(result), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON from LLM: {exc}"


def verify_connectivity() -> tuple[bool, str]:
    """Quick connectivity test. Returns (ok, message)."""
    if not llm_available():
        return False, "No API key configured."
    result, err = llm_complete("Reply with: OK", max_tokens=10)
    if err:
        return False, err
    return True, f"Connected. Response: {result}"
