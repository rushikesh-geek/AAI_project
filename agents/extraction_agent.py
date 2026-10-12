"""
Agent 4 — Field Extraction Agent
Extracts structured fields from document text using regex + heuristics.
Falls back to LLM when ENABLE_LLM_EXTRACTION=True.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from core.config import ENABLE_LLM_EXTRACTION, llm_available
from core.logging_config import get_logger
from core.schemas import (
    ClaimExtraction, ContractExtraction, ContractParty,
    InvoiceExtraction, KYCExtraction, LineItem, OtherExtraction,
)

logger = get_logger(__name__)


# ── Regex helpers ─────────────────────────────────────────────────────────────

# Currency/prefix chars to strip from amounts (includes ₹ and PDF replacement char \ufffd)
_CURRENCY_CHARS = r"[,\s\u20b9\u00a3\u20ac\$\uFFFD\xff]"
# Separator pattern that matches :, whitespace, currency symbols
_SEP = r"[:\s\u20b9\uFFFD\u00a3\$]*"


def _find(pattern: str, text: str, group: int = 1,
          flags: int = re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def _find_amount(pattern: str, text: str) -> Optional[float]:
    """Extract numeric amount, handling ₹ symbol variants including PDF encoding."""
    val = _find(pattern, text)
    if val:
        # Strip any currency chars, commas, spaces, and Unicode replacement chars
        val = re.sub(r"[,\s\u20b9\uFFFD\u00a3\$\u20ac]", "", val)
        try:
            return float(val)
        except ValueError:
            return None
    return None


def _find_amount_line(label: str, text: str) -> Optional[float]:
    """Find an amount on a line starting with a label keyword."""
    # Handles: 'Subtotal: �42,300.00' or 'Total Amount: �44,300.00'
    pattern = rf"^{re.escape(label)}[^\d\n]{{0,10}}([\d,]+\.?\d{{0,2}})\s*$"
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _parse_date(text: str) -> Optional[str]:
    """Try to parse various date formats, return ISO or original string."""
    if not text:
        return None
    # Already clean ISO-ish
    text = text.strip()
    patterns = [
        (r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", "%d/%m/%Y"),
        (r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", "%Y/%m/%d"),
        (r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", None),
    ]
    from datetime import datetime
    for pat, fmt in patterns[:2]:
        m = re.match(pat, text)
        if m:
            try:
                if fmt == "%d/%m/%Y":
                    return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
                elif fmt == "%Y/%m/%d":
                    return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            except Exception:
                pass
    # Try month name
    m = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", text, re.IGNORECASE)
    if m:
        months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05",
                  "jun": "06", "jul": "07", "aug": "08", "sep": "09",
                  "oct": "10", "nov": "11", "dec": "12"}
        mo = months.get(m.group(2).lower()[:3], "01")
        return f"{m.group(3)}-{mo}-{m.group(1).zfill(2)}"
    return text  # Return as-is


def _extract_invoice(text: str) -> tuple[InvoiceExtraction, list[dict]]:
    inv = InvoiceExtraction()
    provenance: list[dict] = []

    def _prov(field, value, method="regex"):
        if value is not None:
            provenance.append({
                "field_name": field,
                "raw_value": str(value),
                "normalized_value": str(value),
                "extraction_method": method,
                "confidence": 0.85,
            })

    # Vendor
    inv.vendor_name = _find(r"(?:from|vendor|supplier|bill\s+from)[:\s]+([A-Z][A-Za-z\s&.,]+?)(?:\n|pvt|ltd|co\.|$)", text)
    if not inv.vendor_name:
        inv.vendor_name = _find(r"^([A-Z][A-Za-z\s&.,]+(?:Pvt\.?\s*Ltd\.?|Ltd\.?|Co\.|Trading|Traders|Enterprises))", text, flags=re.MULTILINE | re.IGNORECASE)
    _prov("vendor_name", inv.vendor_name)

    inv.vendor_gstin = _find(r"GSTIN?[:\s]+([0-9A-Z]{15})", text, flags=re.IGNORECASE)
    _prov("vendor_gstin", inv.vendor_gstin)

    inv.invoice_number = _find(r"(?:invoice|inv)[\s#\-:no.]*([A-Z0-9\-/]+)", text, flags=re.IGNORECASE)
    _prov("invoice_number", inv.invoice_number)

    date_raw = _find(r"(?:invoice|bill)\s+date[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    if not date_raw:
        date_raw = _find(r"date[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    inv.invoice_date = _parse_date(date_raw) if date_raw else None
    _prov("invoice_date", inv.invoice_date)

    due_raw = _find(r"(?:due|payment)\s+date[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    inv.due_date = _parse_date(due_raw) if due_raw else None
    _prov("due_date", inv.due_date)

    inv.po_number = _find(r"(?:po|purchase\s+order)[\s#\-:no.]+([A-Z0-9\-/]+)", text, flags=re.IGNORECASE)
    _prov("po_number", inv.po_number)

    # Amounts — use generic separator to handle ₹ as \uFFFD in PDF text
    # Try line-based matching first (most reliable for formatted invoices)
    inv.subtotal = (
        _find_amount_line("Subtotal", text) or
        _find_amount_line("Sub-total", text) or
        _find_amount(r"(?:sub[-\s]?total|net\s+amount)[^\d\n]{0,10}([\d,]+\.?\d{0,2})", text)
    )
    _prov("subtotal", inv.subtotal)

    inv.tax_amount = (
        _find_amount_line("GST (18%)", text) or
        _find_amount_line("GST (12%)", text) or
        _find_amount_line("GST (28%)", text) or
        _find_amount_line("GST", text) or
        _find_amount_line("IGST", text) or
        _find_amount_line("Tax Amount", text) or
        # Last resort: GST NOT followed by IN (to avoid GSTIN matches), with numeric amount after colon
        _find_amount(r"(?:GST|IGST|CGST|SGST)(?!IN)\s*(?:\([^)]*\))?\s*:\s*([\d,]+\.?\d{0,2})", text)
    )
    _prov("tax_amount", inv.tax_amount)


    inv.tax_rate = _find_amount(r"(?:gst|tax)\s+@?\s*(\d+\.?\d*)\s*%", text)
    _prov("tax_rate", inv.tax_rate)

    inv.discount = _find_amount(r"(?:discount)[^\d\n]{0,10}([\d,]+\.?\d{0,2})", text)
    _prov("discount", inv.discount)

    # Total — line-based first, then pattern matching
    inv.stated_total = (
        _find_amount_line("Total Amount", text) or
        _find_amount_line("Grand Total", text) or
        _find_amount_line("Amount Due", text) or
        _find_amount_line("Net Payable", text) or
        _find_amount(r"(?:total\s+amount|grand\s+total|amount\s+due|total\s+due)[^\d\n]{0,10}([\d,]+\.?\d{0,2})", text)
    )
    _prov("stated_total", inv.stated_total)

    inv.payment_terms = _find(r"payment\s+terms?[:\s]+(.{5,60}?)(?:\n|$)", text, flags=re.IGNORECASE)
    _prov("payment_terms", inv.payment_terms)

    # Line items — basic extraction
    line_items = _extract_line_items(text)
    inv.line_items = line_items
    for i, li in enumerate(line_items):
        _prov(f"line_item_{i+1}", f"{li.description} × {li.quantity} @ {li.unit_price}", "regex")

    return inv, provenance


def _extract_line_items(text: str) -> list[LineItem]:
    """Extract tabular line items from invoice text."""
    items: list[LineItem] = []
    # Pattern: description + quantity + rate + amount on same line
    pattern = re.compile(
        r"^(.{5,50}?)\s+(\d+\.?\d*)\s+(\d[\d,]+\.?\d*)\s+(\d[\d,]+\.?\d*)\s*$",
        re.MULTILINE
    )
    for m in pattern.finditer(text):
        try:
            qty = float(m.group(2))
            rate = float(m.group(3).replace(",", ""))
            amt = float(m.group(4).replace(",", ""))
            # Sanity check: qty × rate ≈ amount
            if abs(qty * rate - amt) < max(1.0, amt * 0.05):
                items.append(LineItem(
                    description=m.group(1).strip(),
                    quantity=qty,
                    unit_price=rate,
                    amount=amt,
                ))
        except ValueError:
            continue
    # If no structured items found, try simpler pattern
    if not items:
        pattern2 = re.compile(
            r"([A-Za-z][A-Za-z\s/\-]{3,40})\s+(\d[\d,]*\.?\d*)\s*(?:nos?|units?|pcs?|kgs?|hrs?)?\s+(\d[\d,]*\.?\d*)",
            re.IGNORECASE
        )
        for m in list(pattern2.finditer(text))[:10]:
            try:
                amt = float(m.group(3).replace(",", ""))
                if amt > 0:
                    items.append(LineItem(
                        description=m.group(1).strip(),
                        quantity=None,
                        unit_price=None,
                        amount=amt,
                    ))
            except ValueError:
                continue
    return items[:20]  # cap


def _extract_kyc(text: str) -> tuple[KYCExtraction, list[dict]]:
    kyc = KYCExtraction()
    provenance: list[dict] = []

    def _prov(field, value, method="regex"):
        if value is not None:
            provenance.append({
                "field_name": field,
                "raw_value": str(value),
                "normalized_value": str(value),
                "extraction_method": method,
                "confidence": 0.80,
            })

    kyc.full_name = _find(r"(?:name|full\s+name)[:\s]+([A-Z][A-Za-z\s.]+?)(?:\n|$|\b(?:dob|date|d\.?o\.?b))", text, flags=re.IGNORECASE)
    _prov("full_name", kyc.full_name)

    # Detect document type
    for dtype in ["Passport", "Aadhaar", "PAN Card", "Driving Licence", "Voter ID"]:
        if dtype.lower() in text.lower():
            kyc.document_type = dtype
            break
    _prov("document_type", kyc.document_type)

    # Document number patterns
    kyc.document_number = (
        _find(r"(?:passport\s+no\.?|document\s+no\.?)[:\s]+([A-Z0-9]{6,12})", text, flags=re.IGNORECASE) or
        _find(r"\b([A-Z]{1,2}[0-9]{7,8})\b", text) or  # Passport style
        _find(r"\b([0-9]{4}\s[0-9]{4}\s[0-9]{4})\b", text) or  # Aadhaar style
        _find(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)   # PAN style
    )
    _prov("document_number", kyc.document_number)

    dob_raw = _find(r"(?:dob|date\s+of\s+birth|born)[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    kyc.date_of_birth = _parse_date(dob_raw) if dob_raw else None
    _prov("date_of_birth", kyc.date_of_birth)

    addr_raw = _find(r"(?:address|addr)[:\s]+(.{10,150}?)(?:\n\n|date|dob|doc|$)", text, flags=re.IGNORECASE | re.DOTALL)
    if addr_raw:
        kyc.address = re.sub(r"\s+", " ", addr_raw).strip()
    _prov("address", kyc.address)

    issue_raw = _find(r"(?:issue\s+date|date\s+of\s+issue)[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    kyc.issue_date = _parse_date(issue_raw) if issue_raw else None
    _prov("issue_date", kyc.issue_date)

    expiry_raw = _find(r"(?:expiry|expiry\s+date|exp\.?\s*date|valid\s+until|valid\s+through)[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    kyc.expiry_date = _parse_date(expiry_raw) if expiry_raw else None
    _prov("expiry_date", kyc.expiry_date)

    kyc.nationality = _find(r"(?:nationality|country)[:\s]+([A-Za-z]+)", text, flags=re.IGNORECASE)
    _prov("nationality", kyc.nationality)

    kyc.has_signature = bool(re.search(r"signature", text, re.IGNORECASE))
    kyc.has_photo = bool(re.search(r"photo|photograph|picture", text, re.IGNORECASE))

    return kyc, provenance


def _extract_contract(text: str) -> tuple[ContractExtraction, list[dict]]:
    ctr = ContractExtraction()
    provenance: list[dict] = []

    def _prov(field, value, method="regex"):
        if value is not None:
            provenance.append({
                "field_name": field,
                "raw_value": str(value),
                "normalized_value": str(value),
                "extraction_method": method,
                "confidence": 0.75,
            })

    # Parties
    party_matches = re.findall(
        r"(?:between|party\s+[a-z]|hereinafter)[:\s]+([A-Z][A-Za-z\s.,&()\-]{3,60}?)(?:,\s*(?:a|an)\s+[A-Z]|\s*\(|and\s+[A-Z]|\n)",
        text, re.IGNORECASE
    )
    for i, p in enumerate(party_matches[:4]):
        name = p.strip().rstrip(",.")
        if len(name) > 3:
            ctr.parties.append(ContractParty(name=name, role=f"Party {i+1}"))
    _prov("parties", [p.name for p in ctr.parties])

    eff_raw = _find(r"(?:effective\s+date|commencing|starting)[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    ctr.effective_date = _parse_date(eff_raw) if eff_raw else None
    _prov("effective_date", ctr.effective_date)

    exp_raw = _find(r"(?:expiry|expiration|end\s+date|termination\s+date)[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    ctr.expiry_date = _parse_date(exp_raw) if exp_raw else None
    _prov("expiry_date", ctr.expiry_date)

    ctr.payment_terms = _find(r"payment\s+(?:terms?|conditions?)[:\s]+(.{10,100}?)(?:\n\n|\.|$)", text, flags=re.IGNORECASE)
    _prov("payment_terms", ctr.payment_terms)

    ctr.termination_notice = _find(r"termination[^.]{0,30}?(\d+)\s*(?:days?|months?)", text, flags=re.IGNORECASE)
    if ctr.termination_notice:
        ctr.termination_notice = f"{ctr.termination_notice} days notice"
    _prov("termination_notice", ctr.termination_notice)

    ctr.renewal_terms = _find(r"(?:renew|renewal)[^.]{0,50}(.{10,80}?)(?:\.|$)", text, flags=re.IGNORECASE)
    _prov("renewal_terms", ctr.renewal_terms)

    ctr.governing_law = _find(r"(?:governing\s+law|jurisdiction)[:\s]+(.{5,60}?)(?:\.|$|\n)", text, flags=re.IGNORECASE)
    _prov("governing_law", ctr.governing_law)

    # Key clauses
    clause_patterns = {
        "payment_terms": r"(?:payment|invoice)[^.]{0,20}?(\d+)\s*days?",
        "termination_notice": r"termination[^.]{0,20}?(\d+)\s*days?",
        "confidentiality": r"(confidential[^.]{0,100}\.)",
        "liability_cap": r"(liabilit[^.]{0,100}\.)",
        "force_majeure": r"(force\s+majeure[^.]{0,100}\.)",
    }
    for clause_name, pat in clause_patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            ctr.key_clauses[clause_name] = m.group(0)[:200].strip()

    _prov("key_clauses", str(list(ctr.key_clauses.keys())))

    return ctr, provenance


def _extract_claim(text: str) -> tuple[ClaimExtraction, list[dict]]:
    clm = ClaimExtraction()
    provenance: list[dict] = []

    def _prov(field, value):
        if value is not None:
            provenance.append({
                "field_name": field,
                "raw_value": str(value),
                "normalized_value": str(value),
                "extraction_method": "regex",
                "confidence": 0.78,
            })

    clm.claimant_name = _find(r"(?:claimant|policyholder|insured)[:\s]+([A-Z][A-Za-z\s.]+?)(?:\n|$)", text, flags=re.IGNORECASE)
    _prov("claimant_name", clm.claimant_name)

    clm.claim_id = _find(r"(?:claim\s+id|claim\s+no\.?|reference)[:\s]+([A-Z0-9\-/]+)", text, flags=re.IGNORECASE)
    _prov("claim_id", clm.claim_id)

    incident_raw = _find(r"(?:incident|accident|event)\s+date[:\s]+(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text, flags=re.IGNORECASE)
    clm.incident_date = _parse_date(incident_raw) if incident_raw else None
    _prov("incident_date", clm.incident_date)

    clm.claim_amount = _find_amount(r"(?:claim\s+amount|amount\s+claimed)[:\s₹]+([0-9,]+\.?\d*)", text)
    _prov("claim_amount", clm.claim_amount)

    clm.claim_type = _find(r"(?:type\s+of\s+claim|claim\s+type)[:\s]+(.{5,40}?)(?:\n|$)", text, flags=re.IGNORECASE)
    _prov("claim_type", clm.claim_type)

    clm.status = _find(r"(?:status|current\s+status)[:\s]+(.{3,30}?)(?:\n|$)", text, flags=re.IGNORECASE)
    _prov("status", clm.status)

    return clm, provenance


def run(text: str, doc_type: str, doc_id: str = "") -> dict:
    """
    Returns:
      extracted: dict of the extracted model
      fields: list of field provenance dicts
      method: extraction_method used
      error: optional
    """
    result = {
        "agent": "ExtractionAgent",
        "status": "success",
        "doc_type": doc_type,
        "extracted": {},
        "fields": [],
        "method": "regex",
        "error": None,
    }

    if not text or len(text.strip()) < 5:
        result["status"] = "failed"
        result["error"] = "Insufficient text for extraction."
        result["extracted"] = OtherExtraction(reason="No text available.").model_dump()
        return result

    try:
        if doc_type == "Invoice":
            extracted, fields = _extract_invoice(text)
        elif doc_type == "KYC":
            extracted, fields = _extract_kyc(text)
        elif doc_type == "Contract":
            extracted, fields = _extract_contract(text)
        elif doc_type == "Claim":
            extracted, fields = _extract_claim(text)
        else:
            words = len(text.split())
            extracted = OtherExtraction(
                raw_text=text[:2000],
                reason=f"Document type '{doc_type}' has no specific schema."
            )
            fields = [{
                "field_name": "raw_text",
                "raw_value": text[:200],
                "normalized_value": text[:200],
                "extraction_method": "text",
                "confidence": 0.5,
            }]

        # Optional LLM enhancement
        if ENABLE_LLM_EXTRACTION and llm_available() and doc_type in ("Invoice", "KYC", "Contract", "Claim"):
            try:
                from services.openrouter_client import llm_extract_fields
                llm_fields, llm_err = llm_extract_fields(text, doc_type)
                if llm_fields and not llm_err:
                    # Merge LLM fields into extracted — fill missing only
                    extracted_dict = extracted.model_dump()
                    for k, v in llm_fields.items():
                        if v is not None and extracted_dict.get(k) is None:
                            extracted_dict[k] = v
                            fields.append({
                                "field_name": k,
                                "raw_value": str(v),
                                "normalized_value": str(v),
                                "extraction_method": "llm",
                                "confidence": 0.75,
                            })
                    result["method"] = "regex+llm"
            except Exception as exc:
                logger.warning("LLM extraction failed: %s", exc)

        result["extracted"] = extracted.model_dump() if hasattr(extracted, "model_dump") else {}
        result["fields"] = fields
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", doc_type, exc)
        result["status"] = "failed"
        result["error"] = str(exc)

    return result
