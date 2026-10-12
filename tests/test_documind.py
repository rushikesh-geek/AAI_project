"""
DocuMind AI — Automated Test Suite
Tests all 20 acceptance criteria using synthetic fixtures and mocked API calls.
"""
import json
import sys
import os
import pytest
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Each test uses a fresh in-memory-style database."""
    import core.config as cfg
    import core.database as db
    test_db = tmp_path / "test.db"
    original_db = cfg.DB_PATH
    cfg.DB_PATH = test_db
    db._initialized = False
    db.DB_PATH = test_db
    db.init_db()
    yield
    cfg.DB_PATH = original_db
    db.DB_PATH = original_db
    db._initialized = False


def _make_invoice_pdf(subtotal=42300.0, tax=0.0, total=44300.0, vendor="Shree Traders",
                       invoice_num="INV-0847") -> bytes:
    """Create a minimal invoice PDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = f"""{vendor}
GST Tax Invoice
GSTIN: 27AAACS1234A1Z5
Invoice No: {invoice_num}
Invoice Date: 15/09/2024
Due Date: 15/10/2024
Purchase Order: PO-2024-0156

Item Description   Qty   Rate (Rs.)   Amount (Rs.)
Widget A          10    2000.00      20000.00
Widget B           5    1200.00       6000.00
Widget C           4    4075.00      16300.00

Subtotal: Rs.{subtotal:.2f}
Total Amount: Rs.{total:.2f}
Payment Terms: Net 30 days
"""
    y = 50
    for line in text.split('\n'):
        page.insert_text((50, y), line, fontsize=10)
        y += 14
    buf = __import__('io').BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_kyc_pdf(expiry_date: str, name="RAVI KUMAR SHARMA") -> bytes:
    import fitz, io
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = f"""SYNTHETIC IDENTITY DOCUMENT (DEMO ONLY)
Document Type: Passport
Document Number: Z9876543
Name: {name}
Date of Birth: 12/05/1985
Nationality: Indian
Issue Date: 01/06/2019
Expiry Date: {expiry_date}
Address: 789, Test Colony, Mumbai - 400001
Signature Present Photo Present
"""
    y = 50
    for line in text.split('\n'):
        page.insert_text((50, y), line, fontsize=10)
        y += 14
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_contract_pdf(payment_days=45) -> bytes:
    import fitz, io
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = f"""VENDOR SERVICES AGREEMENT
Between: ABC Technologies Pvt Ltd and Shree Traders
Effective Date: 01/04/2024
Expiry Date: 31/03/2025

Payment Terms: Payment shall be made within {payment_days} days of invoice receipt.
Termination: Either party may terminate with 30 days written notice.
Governing Law: Laws of India.
Confidentiality: Both parties shall maintain confidentiality.
"""
    y = 50
    for line in text.split('\n'):
        page.insert_text((50, y), line, fontsize=10)
        y += 14
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_corrupt_file() -> bytes:
    return b"THIS IS NOT A VALID PDF OR IMAGE FILE %PDF-1.99 corrupted"


# ── Test 1: Correct invoice totals ────────────────────────────────────────────

def test_correct_invoice_totals():
    """Invoice with matching subtotal+tax=total should pass validation."""
    from agents import extraction_agent, cross_validation_agent
    text = """Shree Traders
Invoice No: INV-001
Invoice Date: 01/01/2024
GSTIN: 27AAACS1234A1Z5
Purchase Order: PO-001
Subtotal: Rs.10000.00
Total Amount: Rs.10000.00
Payment Terms: Net 30 days
"""
    ext = extraction_agent.run(text, "Invoice")
    extracted = ext["extracted"]
    val = cross_validation_agent.run("Invoice", extracted)
    findings = val["findings"]
    mismatch = [f for f in findings if f["rule_id"] == "INV_TOTAL_MISMATCH"]
    assert not mismatch or all(f["passed"] for f in mismatch), "Should not flag correct totals"


# ── Test 2: ₹2,000 invoice discrepancy ────────────────────────────────────────

def test_invoice_2000_discrepancy():
    """The demo invoice discrepancy must be detected."""
    from agents import orchestrator_agent
    invoice_bytes = _make_invoice_pdf(subtotal=42300.0, total=44300.0)
    result = orchestrator_agent.run_pipeline("test_invoice.pdf", invoice_bytes, is_demo=True)
    assert result.get("success"), f"Pipeline failed: {result.get('error')}"
    
    from core.database import get_validation_findings
    findings = get_validation_findings(result["doc_id"])
    mismatch = [f for f in findings if f["rule_id"] == "INV_TOTAL_MISMATCH" and not f["passed"]]
    assert mismatch, f"Expected INV_TOTAL_MISMATCH. Findings: {[f['rule_id'] for f in findings]}"
    assert result.get("status") in ("Needs Review", "High Risk"), "Discrepant invoice must need review"


# ── Test 3: Missing mandatory fields ────────────────────────────────────────────

def test_missing_mandatory_fields():
    """Invoice with no vendor or invoice number should flag mandatory field errors."""
    from agents import extraction_agent, cross_validation_agent
    text = "Just some random text without any invoice fields.\nTotal Amount: Rs.5000.00"
    ext = extraction_agent.run(text, "Invoice")
    val = cross_validation_agent.run("Invoice", ext["extracted"])
    findings = val["findings"]
    missing_findings = [f for f in findings if "MISSING" in f["rule_id"] and not f["passed"]]
    assert len(missing_findings) >= 1, "Should flag missing mandatory fields"


# ── Test 4a: Expired KYC ──────────────────────────────────────────────────────

def test_expired_kyc():
    """Expired KYC document must be flagged Critical."""
    from agents import orchestrator_agent
    past_date = (date.today() - timedelta(days=365)).strftime("%d/%m/%Y")
    kyc_bytes = _make_kyc_pdf(expiry_date=past_date)
    result = orchestrator_agent.run_pipeline("test_kyc_expired.pdf", kyc_bytes, is_demo=True)
    assert result.get("success")
    
    from core.database import get_validation_findings
    findings = get_validation_findings(result["doc_id"])
    expired = [f for f in findings if f["rule_id"] == "KYC_EXPIRED" and not f["passed"]]
    assert expired, "Expired KYC must be flagged"
    assert expired[0]["severity"] == "Critical"


# ── Test 4b: Unexpired KYC ────────────────────────────────────────────────────

def test_unexpired_kyc():
    """Valid (non-expired) KYC should pass expiry check."""
    from agents import extraction_agent, cross_validation_agent
    future_date = (date.today() + timedelta(days=365)).strftime("%d/%m/%Y")
    text = f"""SYNTHETIC DEMO
Document Type: Passport
Document Number: Z9876543
Name: RAVI KUMAR SHARMA
Date of Birth: 12/05/1985
Expiry Date: {future_date}
"""
    ext = extraction_agent.run(text, "KYC")
    val = cross_validation_agent.run("KYC", ext["extracted"])
    expired = [f for f in val["findings"] if f["rule_id"] == "KYC_EXPIRED" and not f["passed"]]
    assert not expired, "Non-expired KYC must not flag as expired"
    ok = [f for f in val["findings"] if f["rule_id"] == "KYC_EXPIRY_OK" and f["passed"]]
    assert ok, "Non-expired KYC should have passing expiry check"


# ── Test 5: Registered vs unregistered vendor ────────────────────────────────

def test_registered_vendor():
    from agents import reference_matching_agent
    result = reference_matching_agent.run("Invoice", {"vendor_name": "Shree Traders"})
    matched = [f for f in result["findings"] if f["rule_id"] == "REF_VENDOR_MATCH" and f["passed"]]
    assert matched, "Known vendor must match"


def test_unregistered_vendor():
    from agents import reference_matching_agent
    result = reference_matching_agent.run("Invoice", {"vendor_name": "Totally Unknown Corp XYZ"})
    unregistered = [f for f in result["findings"] if f["rule_id"] == "REF_VENDOR_UNREGISTERED" and not f["passed"]]
    assert unregistered, "Unknown vendor must be flagged"


# ── Test 6: Unknown document classification ───────────────────────────────────

def test_unknown_classification():
    from agents import classification_agent
    result = classification_agent.run("The quick brown fox jumped over the lazy dog. No business context.")
    assert result["doc_type"] == "Other", f"Unknown doc should classify as Other, got {result['doc_type']}"
    assert result["confidence"] <= 0.7


# ── Test 7: Invalid LLM response handling ─────────────────────────────────────

def test_invalid_llm_response():
    """LLM returning invalid JSON must not crash classification."""
    from services import openrouter_client
    with patch.object(openrouter_client, "llm_complete", return_value=("NOT VALID JSON {{{", None)):
        from services.openrouter_client import llm_classify_document
        doc_type, conf, expl = llm_classify_document("Some invoice text")
        # Should fall back gracefully
        assert doc_type in ("Invoice", "KYC", "Contract", "Claim", "Other")
        assert 0.0 <= conf <= 1.0


# ── Test 8: Missing API key / API failure ─────────────────────────────────────

def test_no_api_key():
    """Application must work without API key."""
    import core.config as cfg
    original = cfg.OPENROUTER_API_KEY
    cfg.OPENROUTER_API_KEY = ""
    try:
        assert not cfg.llm_available()
        from agents import classification_agent
        # Must still work using rule-based classification
        result = classification_agent.run("Invoice No: INV-001\nSubtotal: Rs.5000\nTotal Amount: Rs.5000")
        assert result["doc_type"] == "Invoice"
        assert result["method"] == "rule"
    finally:
        cfg.OPENROUTER_API_KEY = original


def test_api_failure_graceful():
    """API failure must return fallback, not exception."""
    from services.openrouter_client import llm_complete
    with patch("openai.OpenAI") as mock_cls:
        mock_inst = MagicMock()
        mock_cls.return_value = mock_inst
        mock_inst.chat.completions.create.side_effect = Exception("API timeout")
        result, err = llm_complete("test prompt")
        assert result is None
        assert err is not None


# ── Test 9: Corrupt file handling ─────────────────────────────────────────────

def test_corrupt_file():
    from agents import ingestion_agent
    result = ingestion_agent.run("corrupt.pdf", _make_corrupt_file())
    assert result["status"] == "failed"
    assert result["error"] is not None


def test_unsupported_file():
    from core.security import validate_upload
    ok, err = validate_upload("malware.exe", b"MZ\x90\x00fake exe content")
    assert not ok
    assert "Unsupported" in err


# ── Test 10: Duplicate detection ─────────────────────────────────────────────

def test_duplicate_invoice_detection():
    """Same invoice number should be flagged as duplicate."""
    from agents import orchestrator_agent
    inv_bytes = _make_invoice_pdf(invoice_num="INV-DUPE-001")
    r1 = orchestrator_agent.run_pipeline("invoice1.pdf", inv_bytes, is_demo=True)
    assert r1.get("success")
    
    inv_bytes2 = _make_invoice_pdf(invoice_num="INV-DUPE-001", total=44300.0)
    r2 = orchestrator_agent.run_pipeline("invoice2.pdf", inv_bytes2, is_demo=True)
    assert r2.get("success")
    
    from core.database import get_validation_findings
    findings2 = get_validation_findings(r2["doc_id"])
    dup = [f for f in findings2 if f["rule_id"] == "INV_DUPLICATE" and not f["passed"]]
    assert dup, "Duplicate invoice number must be flagged"


def test_duplicate_hash_detection():
    """Same file bytes processed twice should detect duplicate hash on second run."""
    from agents import orchestrator_agent
    from core.database import check_duplicate_hash
    from core.security import compute_sha256

    inv_bytes = _make_invoice_pdf(invoice_num="INV-HASH-001")
    r1 = orchestrator_agent.run_pipeline("inv_a.pdf", inv_bytes, is_demo=True)
    doc_id1 = r1.get("doc_id")
    assert doc_id1

    # Process identical bytes again — simulates a duplicate upload
    r2 = orchestrator_agent.run_pipeline("inv_a_copy.pdf", inv_bytes, is_demo=True)
    doc_id2 = r2.get("doc_id")
    assert doc_id2
    assert doc_id2 != doc_id1  # New doc_id but same hash

    # Querying the hash of the second doc while excluding it should find the first
    file_hash = compute_sha256(inv_bytes)
    dup = check_duplicate_hash(file_hash, exclude_doc_id=doc_id2)
    assert dup == doc_id1, f"Expected {doc_id1}, got {dup}"



# ── Test 11: Review correction persistence ────────────────────────────────────

def test_review_correction_persistence():
    from agents import orchestrator_agent, review_routing_agent
    inv_bytes = _make_invoice_pdf()
    result = orchestrator_agent.run_pipeline("review_test.pdf", inv_bytes, is_demo=True)
    doc_id = result["doc_id"]
    
    review_id = review_routing_agent.record_review_decision(
        doc_id=doc_id, field_name="stated_total",
        action="correct", original_value="44300.0", corrected_value="42300.0",
        reviewer="TestReviewer", comment="Correcting discrepancy"
    )
    assert review_id
    
    from core.database import get_review_decisions
    reviews = get_review_decisions(doc_id)
    assert len(reviews) == 1
    assert reviews[0]["corrected_value"] == "42300.0"
    assert reviews[0]["reviewer"] == "TestReviewer"


# ── Test 12: Business rule persistence ────────────────────────────────────────

def test_business_rule_persistence():
    from core.database import upsert_business_rule, get_business_rules
    upsert_business_rule({
        "rule_id": "TEST_RULE_001",
        "rule_type": "threshold",
        "name": "Test Rule",
        "description": "Test",
        "parameters": {"field": "stated_total", "operator": "gt", "value": 1000},
        "severity": "High",
        "active": 1,
    })
    rules = get_business_rules(active_only=True)
    rule_ids = [r["rule_id"] for r in rules]
    assert "TEST_RULE_001" in rule_ids


def test_business_rule_applied():
    """A custom threshold rule must be applied during processing."""
    from core.database import upsert_business_rule
    upsert_business_rule({
        "rule_id": "TEST_THRESHOLD",
        "rule_type": "threshold",
        "name": "Low Value Test",
        "description": "Flag invoices > 100",
        "parameters": {"field": "stated_total", "operator": "gt", "value": 100},
        "severity": "Medium",
        "active": 1,
    })
    
    from agents import orchestrator_agent
    inv_bytes = _make_invoice_pdf(subtotal=42300.0, total=44300.0)
    result = orchestrator_agent.run_pipeline("rule_test.pdf", inv_bytes, is_demo=True)
    
    from core.database import get_validation_findings
    findings = get_validation_findings(result["doc_id"])
    rule_finding = [f for f in findings if f["rule_id"] == "TEST_THRESHOLD"]
    assert rule_finding, "Custom rule must be evaluated"


# ── Test 13: Audit event creation ─────────────────────────────────────────────

def test_audit_event_created():
    from agents import orchestrator_agent
    from core.database import get_audit_events
    inv_bytes = _make_invoice_pdf()
    result = orchestrator_agent.run_pipeline("audit_test.pdf", inv_bytes, is_demo=True)
    events = get_audit_events(result["doc_id"])
    assert len(events) > 0
    event_types = [e["event_type"] for e in events]
    assert "PIPELINE" in event_types or "AGENT" in event_types


# ── Test 14: JSON and CSV export ──────────────────────────────────────────────

def test_json_export():
    from agents import orchestrator_agent, structured_output_agent
    from core.database import get_all_documents, get_extracted_fields, get_validation_findings, get_review_decisions
    inv_bytes = _make_invoice_pdf()
    result = orchestrator_agent.run_pipeline("export_test.pdf", inv_bytes, is_demo=True)
    doc_id = result["doc_id"]
    doc = next(d for d in get_all_documents() if d["doc_id"] == doc_id)
    json_bytes = structured_output_agent.export_json(
        doc, get_extracted_fields(doc_id),
        get_validation_findings(doc_id), get_review_decisions(doc_id), {}
    )
    data = json.loads(json_bytes)
    assert data["doc_id"] == doc_id
    assert "extracted_fields" in data
    assert "validation_findings" in data
    assert "schema_version" in data


def test_csv_export():
    from agents import orchestrator_agent, structured_output_agent
    from core.database import get_all_documents, get_extracted_fields, get_validation_findings, get_review_decisions
    inv_bytes = _make_invoice_pdf()
    result = orchestrator_agent.run_pipeline("csv_test.pdf", inv_bytes, is_demo=True)
    doc_id = result["doc_id"]
    doc = next(d for d in get_all_documents() if d["doc_id"] == doc_id)
    csv_bytes = structured_output_agent.export_csv(
        doc, get_extracted_fields(doc_id),
        get_validation_findings(doc_id), get_review_decisions(doc_id), {}
    )
    lines = csv_bytes.decode("utf-8").splitlines()
    assert lines[0].startswith("doc_id")
    assert len(lines) > 1


# ── Test 15: Batch processing with one failed doc ─────────────────────────────

def test_batch_isolation():
    """One corrupt document must not stop batch processing of other documents."""
    from agents import orchestrator_agent
    valid_bytes = _make_invoice_pdf()
    corrupt_bytes = _make_corrupt_file()
    
    r1 = orchestrator_agent.run_pipeline("valid.pdf", valid_bytes, is_demo=True)
    r2 = orchestrator_agent.run_pipeline("corrupt.pdf", corrupt_bytes, is_demo=True)
    
    assert r1.get("success"), "Valid document should succeed"
    assert not r2.get("success"), "Corrupt document should fail"
    # But valid should still have results
    from core.database import get_all_documents
    docs = get_all_documents()
    valid_doc = next((d for d in docs if d["doc_id"] == r1["doc_id"]), None)
    assert valid_doc is not None
    assert valid_doc["status"] != "Failed"


# ── Test 16: Source provenance integrity ─────────────────────────────────────

def test_source_provenance():
    """Extracted fields must have provenance (extraction_method, confidence)."""
    from agents import extraction_agent
    text = "Shree Traders\nInvoice No: INV-001\nSubtotal: Rs.10000.00\nTotal Amount: Rs.10000.00"
    result = extraction_agent.run(text, "Invoice")
    fields = result["fields"]
    assert len(fields) > 0
    for f in fields:
        assert "extraction_method" in f
        assert "confidence" in f
        assert f["confidence"] > 0.0


# ── Test 17: SQLite persistence across restart ────────────────────────────────

def test_sqlite_persistence(tmp_path):
    """Data must persist when database module is re-initialized."""
    import core.config as cfg
    import core.database as db
    
    test_db = tmp_path / "persist_test.db"
    cfg.DB_PATH = test_db
    db.DB_PATH = test_db
    db._initialized = False
    db.init_db()
    
    from agents import orchestrator_agent
    inv_bytes = _make_invoice_pdf()
    result = orchestrator_agent.run_pipeline("persist_test.pdf", inv_bytes, is_demo=True)
    doc_id = result["doc_id"]
    
    # Simulate restart: reinitialize
    db._initialized = False
    db.init_db()
    
    from core.database import get_document
    doc = get_document(doc_id)
    assert doc is not None, "Document must persist after DB re-init"
    assert doc["doc_id"] == doc_id


# ── Test 18: No-LLM fallback mode ────────────────────────────────────────────

def test_no_llm_fallback():
    """Without LLM, classification must still work using rule-based approach."""
    import core.config as cfg
    cfg.OPENROUTER_API_KEY = ""
    cfg.ENABLE_LLM_CLASSIFICATION = False
    
    from agents import classification_agent
    result = classification_agent.run(
        "Invoice No: INV-001\nVendor: Test Corp\nTotal Amount: Rs.5000\nPayment Terms: Net 30"
    )
    assert result["doc_type"] == "Invoice"
    assert result["method"] == "rule"


# ── Test 19: Orchestrator sequencing ─────────────────────────────────────────

def test_orchestrator_agent_trace():
    """Orchestrator must record all agent execution events."""
    from agents import orchestrator_agent
    inv_bytes = _make_invoice_pdf()
    result = orchestrator_agent.run_pipeline("trace_test.pdf", inv_bytes, is_demo=True)
    
    assert result.get("success")
    from core.database import get_agent_events
    events = get_agent_events(result["doc_id"])
    agent_names = [e["agent_name"] for e in events]
    
    expected = ["IngestionAgent", "OCRLayoutAgent", "ClassificationAgent",
                "ExtractionAgent", "CrossValidationAgent", "ReferenceMatchingAgent",
                "RiskScoringAgent", "ReviewRoutingAgent", "StructuredOutputAgent"]
    for expected_agent in expected:
        assert expected_agent in agent_names, f"Missing agent: {expected_agent}"


# ── Test 20: Contract clause comparison ───────────────────────────────────────

def test_contract_clause_comparison():
    """Contract clauses must be compared against template."""
    from agents import extraction_agent
    text = """VENDOR AGREEMENT
Between: ABC Corp and XYZ Ltd
Effective Date: 01/01/2024
Expiry Date: 31/12/2024
Payment Terms: Payment shall be made within 45 days of invoice receipt.
Termination: Either party may terminate with 30 days written notice.
Governing Law: Laws of India.
"""
    result = extraction_agent.run(text, "Contract")
    extracted = result["extracted"]
    
    from pages.contracts import _compare_clauses
    template_clauses = {
        "payment_terms": "Payment shall be made within 30 days of invoice receipt.",
        "termination_notice": "Either party may terminate this agreement with 30 days written notice.",
        "governing_law": "This agreement shall be governed by the laws of India.",
    }
    comparisons = _compare_clauses(extracted.get("key_clauses", {}), template_clauses)
    assert len(comparisons) > 0
    statuses = {c["clause_name"]: c["status"] for c in comparisons}
    # Payment terms deviated (45 vs 30 days)
    # At least some should be missing or partial
    assert any(c["status"] in ("missing", "partial", "deviation") for c in comparisons)


# ── Additional smoke tests ────────────────────────────────────────────────────

def test_db_init():
    from core.database import get_dashboard_metrics
    m = get_dashboard_metrics()
    assert isinstance(m, dict)
    assert "total" in m


def test_schemas_importable():
    from core.schemas import (
        DocumentType, ProcessingStatus, InvoiceExtraction,
        KYCExtraction, ContractExtraction, ValidationFinding
    )
    inv = InvoiceExtraction(vendor_name="Test", invoice_number="INV-001", stated_total=5000.0)
    assert inv.vendor_name == "Test"


def test_security_upload_validation():
    from core.security import validate_upload
    ok, _ = validate_upload("test.pdf", b"%PDF-1.4 fake content here for testing minimum size validation")
    assert ok
    
    ok2, err = validate_upload("bad.exe", b"MZ fake exe")
    assert not ok2
