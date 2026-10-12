"""Full pipeline E2E test"""
import sys
sys.path.insert(0, '.')

from core.database import init_db, clear_demo_data
init_db()
clear_demo_data()  # Fresh start for test
print('DB initialized, demo data cleared')

from core.config import DEMO_DIR
from assets.demo.demo_generator import create_demo_documents
files = create_demo_documents(DEMO_DIR)

from agents.orchestrator_agent import run_pipeline

# ── Invoice test ──────────────────────────────────────────────────────────
inv_path = files['invoice']
result = run_pipeline(inv_path.name, inv_path.read_bytes(), is_demo=True)
print('\n=== INVOICE PIPELINE ===')
print('Success:', result.get('success'))
print('Type:', result.get('doc_type'))
print('Status:', result.get('status'))
print('Risk Score:', result.get('risk_score'))

doc_id = result.get('doc_id')
if doc_id:
    from core.database import get_validation_findings, get_extracted_fields
    fields = get_extracted_fields(doc_id)
    print('Fields:', [(f['field_name'], f['normalized_value']) for f in fields])
    findings = get_validation_findings(doc_id)
    for f in findings:
        status = 'PASS' if f.get('passed') else 'FAIL'
        print(f'  [{status}][{f["severity"]}] {f["rule_id"]}: {f["message"][:100]}')

# Verify discrepancy found
total_mismatch = any(f.get('rule_id') == 'INV_TOTAL_MISMATCH' for f in findings)
print(f'\n>>> Total mismatch detected: {total_mismatch} (REQUIRED: True)')

# ── Review decision ────────────────────────────────────────────────────────
print('\n=== REVIEW DECISION ===')
from agents.review_routing_agent import record_review_decision
review_id = record_review_decision(
    doc_id=doc_id, field_name='stated_total', action='correct',
    original_value='44300.0', corrected_value='42300.0',
    reviewer='Test Reviewer', comment='Confirmed subtotal matches; total is incorrect'
)
print(f'Review recorded: {review_id}')

# Verify persistence
from core.database import get_review_decisions, get_audit_events
reviews = get_review_decisions(doc_id)
print(f'Review decisions persisted: {len(reviews)}')
audit = get_audit_events(doc_id)
review_events = [e for e in audit if e.get('event_type') == 'REVIEW']
print(f'Audit events (REVIEW): {len(review_events)}')

# ── Export ─────────────────────────────────────────────────────────────────
print('\n=== EXPORT ===')
from core.database import get_all_documents, get_validation_findings
from agents.structured_output_agent import export_json, export_csv
doc_info = next(d for d in get_all_documents() if d['doc_id'] == doc_id)
json_bytes = export_json(doc_info, get_extracted_fields(doc_id), get_validation_findings(doc_id), reviews, {})
csv_bytes = export_csv(doc_info, get_extracted_fields(doc_id), get_validation_findings(doc_id), reviews, {})
print(f'JSON export: {len(json_bytes)} bytes')
print(f'CSV export: {len(csv_bytes)} bytes')

import json
export_data = json.loads(json_bytes)
corrections = export_data.get('reviewer_corrections', {})
print(f'Reviewer corrections in export: {corrections}')

# ── KYC expired ─────────────────────────────────────────────────────────────
print('\n=== KYC (EXPIRED) ===')
kyc_result = run_pipeline(files['kyc_expired'].name, files['kyc_expired'].read_bytes(), is_demo=True)
print('Type:', kyc_result.get('doc_type'))
print('Status:', kyc_result.get('status'))
if kyc_result.get('doc_id'):
    kyc_findings = get_validation_findings(kyc_result['doc_id'])
    expired = any(f.get('rule_id') == 'KYC_EXPIRED' for f in kyc_findings)
    print(f'>>> KYC_EXPIRED detected: {expired} (REQUIRED: True)')

print('\n=== ALL TESTS COMPLETE ===')
