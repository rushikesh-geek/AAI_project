"""
Agent 5 — Cross-Field Validation Agent
Deterministic, explainable validation rules for all document types.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

from core.logging_config import get_logger
from core.schemas import FindingSeverity

logger = get_logger(__name__)

ROUNDING_TOLERANCE = 2.0  # ₹ tolerance for arithmetic checks


def _parse_date_str(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _finding(rule_id: str, field: Optional[str], severity: FindingSeverity,
             message: str, passed: bool = False,
             expected: str = None, observed: str = None,
             source_ref: str = None, suggestion: str = None) -> dict:
    return {
        "rule_id": rule_id,
        "field": field,
        "severity": severity.value,
        "message": message,
        "passed": passed,
        "expected": expected,
        "observed": observed,
        "source_ref": source_ref,
        "suggestion": suggestion,
    }


def _validate_invoice(extracted: dict, doc_id: str) -> list[dict]:
    findings = []
    today = date.today()

    # Mandatory fields
    mandatory = ["vendor_name", "invoice_number", "invoice_date", "stated_total"]
    for field in mandatory:
        val = extracted.get(field)
        if not val:
            findings.append(_finding(
                f"INV_MISSING_{field.upper()}", field, FindingSeverity.HIGH,
                f"Mandatory field '{field}' is missing.",
                suggestion=f"Ensure the invoice clearly states the {field.replace('_', ' ')}."
            ))

    # Line-item arithmetic
    line_items = extracted.get("line_items", [])
    if line_items:
        computed_subtotal = 0.0
        valid_items = []
        for item in line_items:
            if isinstance(item, dict):
                amt = item.get("amount")
                qty = item.get("quantity")
                rate = item.get("unit_price")
                if amt is not None:
                    computed_subtotal += float(amt)
                    # Check qty × rate = amount
                    if qty is not None and rate is not None:
                        expected_amt = round(float(qty) * float(rate), 2)
                        if abs(expected_amt - float(amt)) > ROUNDING_TOLERANCE:
                            findings.append(_finding(
                                "INV_LINE_MATH", f"line_item:{item.get('description','')}",
                                FindingSeverity.MEDIUM,
                                f"Line item arithmetic error: {qty} × {rate} ≠ {amt}",
                                expected=str(expected_amt), observed=str(amt),
                                suggestion="Verify the line item calculation."
                            ))

        # Subtotal check
        stated_subtotal = extracted.get("subtotal")
        if stated_subtotal is not None and computed_subtotal > 0:
            diff = abs(float(stated_subtotal) - computed_subtotal)
            if diff > ROUNDING_TOLERANCE:
                findings.append(_finding(
                    "INV_SUBTOTAL", "subtotal", FindingSeverity.HIGH,
                    f"Stated subtotal ₹{stated_subtotal:,.2f} does not match computed sum ₹{computed_subtotal:,.2f} (diff: ₹{diff:,.2f})",
                    expected=f"₹{computed_subtotal:,.2f}", observed=f"₹{stated_subtotal:,.2f}",
                    suggestion="Recheck line item amounts and subtotal."
                ))
        elif computed_subtotal > 0 and not stated_subtotal:
            # Use computed as reference
            stated_subtotal = computed_subtotal

    # Tax + total reconciliation
    stated_total = extracted.get("stated_total")
    subtotal = extracted.get("subtotal")
    tax_amount = extracted.get("tax_amount") or 0.0
    discount = extracted.get("discount") or 0.0

    if stated_total is not None and subtotal is not None:
        expected_total = round(float(subtotal) + float(tax_amount) - float(discount), 2)
        diff = abs(float(stated_total) - expected_total)
        if diff > ROUNDING_TOLERANCE:
            findings.append(_finding(
                "INV_TOTAL_MISMATCH", "stated_total", FindingSeverity.CRITICAL,
                f"Total discrepancy: stated ₹{stated_total:,.2f} ≠ "
                f"subtotal({subtotal:,.2f}) + tax({tax_amount:,.2f}) - discount({discount:,.2f}) = ₹{expected_total:,.2f}. "
                f"Difference: ₹{diff:,.2f}",
                expected=f"₹{expected_total:,.2f}", observed=f"₹{stated_total:,.2f}",
                source_ref="INV total reconciliation",
                suggestion=f"Verify the invoice total. Discrepancy of ₹{diff:,.2f} found."
            ))
        else:
            findings.append(_finding(
                "INV_TOTAL_OK", "stated_total", FindingSeverity.INFO,
                "Invoice total reconciles correctly with subtotal and taxes.",
                passed=True
            ))

    # Date checks
    invoice_date = _parse_date_str(extracted.get("invoice_date"))
    due_date = _parse_date_str(extracted.get("due_date"))

    if invoice_date and invoice_date > today:
        findings.append(_finding(
            "INV_FUTURE_DATE", "invoice_date", FindingSeverity.MEDIUM,
            f"Invoice date {invoice_date} is in the future.",
            expected=f"≤ {today}", observed=str(invoice_date),
            suggestion="Verify the invoice date."
        ))

    if invoice_date and due_date:
        if due_date < invoice_date:
            findings.append(_finding(
                "INV_DUE_BEFORE_ISSUE", "due_date", FindingSeverity.HIGH,
                f"Due date {due_date} is before invoice date {invoice_date}.",
                suggestion="Verify payment terms and dates."
            ))

    # Duplicate invoice number check
    inv_num = extracted.get("invoice_number")
    if inv_num and doc_id:
        try:
            from core.database import check_duplicate_invoice_number
            dup = check_duplicate_invoice_number(inv_num, doc_id)
            if dup:
                findings.append(_finding(
                    "INV_DUPLICATE", "invoice_number", FindingSeverity.CRITICAL,
                    f"Duplicate invoice number '{inv_num}' already processed (doc_id: {dup}).",
                    observed=inv_num,
                    suggestion="Verify this is not a duplicate submission."
                ))
        except Exception as exc:
            logger.warning("Duplicate check failed: %s", exc)

    return findings


def _validate_kyc(extracted: dict) -> list[dict]:
    findings = []
    today = date.today()

    mandatory = ["full_name", "document_number", "document_type"]
    for field in mandatory:
        if not extracted.get(field):
            findings.append(_finding(
                f"KYC_MISSING_{field.upper()}", field, FindingSeverity.HIGH,
                f"Mandatory field '{field}' is missing.",
                suggestion=f"Ensure the KYC document includes {field.replace('_', ' ')}."
            ))

    # Expiry check
    expiry = _parse_date_str(extracted.get("expiry_date"))
    if expiry:
        if expiry < today:
            findings.append(_finding(
                "KYC_EXPIRED", "expiry_date", FindingSeverity.CRITICAL,
                f"Document expired on {expiry} (today: {today}). This document is no longer valid.",
                expected=f"> {today}", observed=str(expiry),
                suggestion="Request updated identification document."
            ))
        else:
            days_left = (expiry - today).days
            findings.append(_finding(
                "KYC_EXPIRY_OK", "expiry_date", FindingSeverity.INFO,
                f"Document valid. Expires {expiry} ({days_left} days remaining).",
                passed=True
            ))
    else:
        findings.append(_finding(
            "KYC_MISSING_EXPIRY", "expiry_date", FindingSeverity.MEDIUM,
            "Expiry date not found or could not be parsed.",
            suggestion="Locate and verify the document expiry date."
        ))

    # DOB sanity
    dob = _parse_date_str(extracted.get("date_of_birth"))
    if dob:
        age = (today - dob).days // 365
        if age < 0 or age > 120:
            findings.append(_finding(
                "KYC_DOB_INVALID", "date_of_birth", FindingSeverity.HIGH,
                f"Date of birth {dob} yields unreasonable age ({age} years).",
                suggestion="Verify the date of birth on the document."
            ))

    # Issue ≤ today
    issue = _parse_date_str(extracted.get("issue_date"))
    if issue and issue > today:
        findings.append(_finding(
            "KYC_FUTURE_ISSUE", "issue_date", FindingSeverity.HIGH,
            f"Issue date {issue} is in the future.",
            suggestion="Verify the issue date."
        ))

    return findings


def _validate_contract(extracted: dict) -> list[dict]:
    findings = []
    today = date.today()

    if not extracted.get("parties"):
        findings.append(_finding(
            "CTR_MISSING_PARTIES", "parties", FindingSeverity.HIGH,
            "No contracting parties identified.",
            suggestion="Ensure the contract clearly identifies all parties."
        ))

    eff = _parse_date_str(extracted.get("effective_date"))
    exp = _parse_date_str(extracted.get("expiry_date"))

    if not eff:
        findings.append(_finding(
            "CTR_MISSING_EFF_DATE", "effective_date", FindingSeverity.MEDIUM,
            "Effective date not found.",
            suggestion="Verify the contract start date."
        ))

    if exp and exp < today:
        findings.append(_finding(
            "CTR_EXPIRED", "expiry_date", FindingSeverity.HIGH,
            f"Contract expired on {exp}.",
            observed=str(exp), expected=f"> {today}",
            suggestion="Renew the contract or obtain an extension."
        ))
    elif exp and eff and exp <= eff:
        findings.append(_finding(
            "CTR_INVALID_DATES", "expiry_date", FindingSeverity.HIGH,
            f"Contract expiry {exp} is not after effective date {eff}.",
            suggestion="Verify contract date range."
        ))

    if not extracted.get("payment_terms"):
        findings.append(_finding(
            "CTR_MISSING_PAYMENT", "payment_terms", FindingSeverity.MEDIUM,
            "Payment terms not found.",
            suggestion="Ensure contract specifies payment terms."
        ))

    if not extracted.get("termination_notice"):
        findings.append(_finding(
            "CTR_MISSING_TERM", "termination_notice", FindingSeverity.LOW,
            "Termination notice period not found.",
            suggestion="Consider adding explicit termination provisions."
        ))

    return findings


def _validate_claim(extracted: dict) -> list[dict]:
    findings = []
    today = date.today()

    mandatory = ["claimant_name", "claim_id", "claim_amount"]
    for field in mandatory:
        if not extracted.get(field):
            findings.append(_finding(
                f"CLM_MISSING_{field.upper()}", field, FindingSeverity.HIGH,
                f"Mandatory claim field '{field}' is missing.",
                suggestion=f"Provide {field.replace('_', ' ')}."
            ))

    incident = _parse_date_str(extracted.get("incident_date"))
    if incident and incident > today:
        findings.append(_finding(
            "CLM_FUTURE_INCIDENT", "incident_date", FindingSeverity.HIGH,
            f"Incident date {incident} is in the future.",
            suggestion="Verify the incident date."
        ))

    amount = extracted.get("claim_amount")
    if amount is not None:
        if float(amount) <= 0:
            findings.append(_finding(
                "CLM_INVALID_AMOUNT", "claim_amount", FindingSeverity.HIGH,
                f"Claim amount ₹{amount} is not positive.",
                suggestion="Verify the claimed amount."
            ))

    return findings


def run(doc_type: str, extracted: dict, doc_id: str = "") -> dict:
    """
    Returns:
      findings: list of finding dicts
      has_critical: bool
      has_errors: bool
      summary: str
    """
    result = {
        "agent": "CrossValidationAgent",
        "status": "success",
        "findings": [],
        "has_critical": False,
        "has_errors": False,
        "summary": "",
        "error": None,
    }

    try:
        if doc_type == "Invoice":
            findings = _validate_invoice(extracted, doc_id)
        elif doc_type == "KYC":
            findings = _validate_kyc(extracted)
        elif doc_type == "Contract":
            findings = _validate_contract(extracted)
        elif doc_type == "Claim":
            findings = _validate_claim(extracted)
        else:
            findings = [_finding(
                "OTHER_NO_RULES", None, FindingSeverity.INFO,
                "No specific validation rules for this document type.",
                passed=True
            )]

        result["findings"] = findings
        failures = [f for f in findings if not f["passed"]]
        critical = [f for f in failures if f["severity"] in ("Critical", "High")]
        result["has_critical"] = len(critical) > 0
        result["has_errors"] = len(failures) > 0
        result["summary"] = (
            f"{len(findings)} checks: {len(critical)} critical/high issues, "
            f"{len(failures) - len(critical)} warnings, "
            f"{len(findings) - len(failures)} passed."
        )

    except Exception as exc:
        logger.error("Validation failed for %s: %s", doc_type, exc)
        result["status"] = "failed"
        result["error"] = str(exc)

    return result
