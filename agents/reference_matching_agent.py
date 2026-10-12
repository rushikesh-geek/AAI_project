"""
Agent 6 — Reference and Business Rule Matching Agent
Matches document fields against reference data and applies configured business rules.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

from core.logging_config import get_logger
from core.schemas import FindingSeverity

logger = get_logger(__name__)


def _parse_date_str(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _fuzzy_match(name: str, candidates: list[str], threshold: int = 80) -> tuple[Optional[str], int]:
    """Return (best_match, score). Returns None if below threshold."""
    if not candidates:
        return None, 0
    try:
        from rapidfuzz import process, fuzz
        result = process.extractOne(
            name.lower().strip(),
            [c.lower().strip() for c in candidates],
            scorer=fuzz.token_sort_ratio
        )
        if result and result[1] >= threshold:
            # Return the original (non-lowered) candidate
            idx = [c.lower().strip() for c in candidates].index(result[0])
            return candidates[idx], result[1]
    except Exception as exc:
        logger.warning("Fuzzy match error: %s", exc)
        # Exact fallback
        name_lower = name.lower().strip()
        for c in candidates:
            if c.lower().strip() == name_lower:
                return c, 100
    return None, 0


def _finding(rule_id: str, field: Optional[str], severity: str,
             message: str, passed: bool = False,
             expected: str = None, observed: str = None,
             suggestion: str = None) -> dict:
    return {
        "rule_id": rule_id,
        "field": field,
        "severity": severity,
        "message": message,
        "passed": passed,
        "expected": expected,
        "observed": observed,
        "suggestion": suggestion,
    }


def run(doc_type: str, extracted: dict, doc_id: str = "") -> dict:
    """
    Returns:
      findings: list of rule-match finding dicts
      vendor_match: optional match result for invoices
      summary: str
    """
    result = {
        "agent": "ReferenceMatchingAgent",
        "status": "success",
        "findings": [],
        "vendor_match": None,
        "summary": "",
        "error": None,
    }

    try:
        from core.database import get_reference_entities, get_business_rules
        rules = get_business_rules(active_only=True)
        findings: list[dict] = []

        if doc_type == "Invoice":
            vendors = get_reference_entities("vendor")
            vendor_names = [v["name"] for v in vendors]
            vendor_name = extracted.get("vendor_name") or ""

            # Vendor match rule
            vendor_rule = next((r for r in rules if r["rule_id"] == "RULE_UNREGISTERED_VENDOR"), None)
            threshold = 80
            if vendor_rule:
                threshold = vendor_rule.get("parameters", {}).get("match_threshold", 80)

            if vendor_name and vendor_names:
                match, score = _fuzzy_match(vendor_name, vendor_names, threshold)
                result["vendor_match"] = {"matched": match, "score": score, "query": vendor_name}
                if match:
                    findings.append(_finding(
                        "REF_VENDOR_MATCH", "vendor_name", FindingSeverity.INFO.value,
                        f"Vendor '{vendor_name}' matched reference: '{match}' (score: {score}%)",
                        passed=True, observed=vendor_name, expected=match
                    ))
                else:
                    findings.append(_finding(
                        "REF_VENDOR_UNREGISTERED", "vendor_name", FindingSeverity.HIGH.value,
                        f"Vendor '{vendor_name}' not found in registered vendor list (best score: {score}%).",
                        observed=vendor_name,
                        suggestion="Add vendor to the reference list or verify vendor details."
                    ))
            elif not vendor_name:
                findings.append(_finding(
                    "REF_VENDOR_MISSING", "vendor_name", FindingSeverity.HIGH.value,
                    "Cannot perform vendor reference check — vendor name is missing.",
                    suggestion="Extract or manually enter the vendor name."
                ))

            # Apply business rules
            for rule in rules:
                rtype = rule.get("rule_type")
                params = rule.get("parameters") if isinstance(rule.get("parameters"), dict) else {}
                severity = rule.get("severity", "Medium")
                rid = rule.get("rule_id")

                if rtype == "threshold":
                    field = params.get("field", "stated_total")
                    operator = params.get("operator", "gt")
                    threshold_val = params.get("value", 50000)
                    val = extracted.get(field)
                    if val is not None:
                        try:
                            fval = float(val)
                            triggered = False
                            if operator == "gt" and fval > threshold_val:
                                triggered = True
                            elif operator == "gte" and fval >= threshold_val:
                                triggered = True
                            elif operator == "lt" and fval < threshold_val:
                                triggered = True

                            if triggered:
                                findings.append(_finding(
                                    rid, field, severity,
                                    f"Rule '{rule['name']}': {field} = ₹{fval:,.2f} {operator} ₹{threshold_val:,.2f}",
                                    observed=f"₹{fval:,.2f}",
                                    suggestion=f"Review as per policy: {rule.get('description','')}"
                                ))
                            else:
                                findings.append(_finding(
                                    rid, field, FindingSeverity.INFO.value,
                                    f"Rule '{rule['name']}': {field} = ₹{fval:,.2f} — within threshold.",
                                    passed=True
                                ))
                        except (ValueError, TypeError):
                            pass

                elif rtype == "required_field":
                    field = params.get("field")
                    if field:
                        val = extracted.get(field)
                        if not val:
                            findings.append(_finding(
                                rid, field, severity,
                                f"Business rule '{rule['name']}': required field '{field}' is missing.",
                                suggestion=rule.get("description", "")
                            ))
                        else:
                            findings.append(_finding(
                                rid, field, FindingSeverity.INFO.value,
                                f"Rule '{rule['name']}': field '{field}' is present.",
                                passed=True
                            ))

                elif rtype == "due_date":
                    days_warning = params.get("days", 7)
                    due_date = _parse_date_str(extracted.get("due_date"))
                    if due_date:
                        days_until = (due_date - date.today()).days
                        if 0 <= days_until <= days_warning:
                            findings.append(_finding(
                                rid, "due_date", severity,
                                f"Invoice due in {days_until} days ({due_date}). Requires prompt attention.",
                                observed=str(due_date),
                                suggestion="Process payment promptly."
                            ))

        elif doc_type == "KYC":
            # Match customer entities
            customers = get_reference_entities("customer")
            if customers:
                cust_names = [c["name"] for c in customers]
                full_name = extracted.get("full_name") or ""
                if full_name:
                    match, score = _fuzzy_match(full_name, cust_names, threshold=85)
                    if match:
                        findings.append(_finding(
                            "REF_CUSTOMER_MATCH", "full_name", FindingSeverity.INFO.value,
                            f"Name '{full_name}' matched customer: '{match}' (score: {score}%)",
                            passed=True
                        ))

        result["findings"] = findings
        passed = sum(1 for f in findings if f["passed"])
        failed = len(findings) - passed
        result["summary"] = f"{len(rules)} rules evaluated: {passed} passed, {failed} flagged."

    except Exception as exc:
        logger.error("Reference matching failed: %s", exc)
        result["status"] = "failed"
        result["error"] = str(exc)

    return result
