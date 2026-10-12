# DocuMind AI — Autonomous Document Intelligence & Verification Platform

**DocuMind AI** is a fully functional agentic document intelligence system for SMEs. It ingests PDFs and images, orchestrates 10 AI agents to extract, validate, score, and route documents for human review, and exports structured data.

---

## ✅ Quick Start

### 1. Prerequisites

```bash
# Python 3.10+ required
python --version

# (Windows) Install Tesseract OCR for image-based OCR (optional)
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
# Add to PATH or set TESSERACT_CMD in .env
```

### 2. Install dependencies

```bash
cd d:\AAI_Project
pip install -r requirements.txt
```

### 3. Configure environment

```bash
copy .env.example .env
# Edit .env and optionally add your OpenRouter API key
```

**.env example:**
```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
ENABLE_LLM_CLASSIFICATION=true
ENABLE_LLM_EXTRACTION=true
```

> **The application runs fully without an API key** using rule-based classification and regex extraction.

### 4. Run the application

```bash
python -m streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## 🧠 10-Agent Architecture

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | IngestionAgent | Validates, saves, and hashes uploaded documents |
| 2 | OCRLayoutAgent | Extracts text from PDF/images; Tesseract when available |
| 3 | ClassificationAgent | Rule-based → LLM classification (Invoice/KYC/Contract/Claim/Other) |
| 4 | ExtractionAgent | Schema-validated field extraction per document type |
| 5 | CrossValidationAgent | Deterministic rules: total mismatch, expiry, required fields, dates |
| 6 | ReferenceMatchingAgent | Vendor/PO lookup, duplicate invoice detection, custom rules |
| 7 | RiskScoringAgent | Weighted scoring from findings, confidence, and flags |
| 8 | ReviewRoutingAgent | Routes high-risk/flagged documents to human review queue |
| 9 | StructuredOutputAgent | JSON/CSV/Excel export with provenance |
| 10 | OrchestratorAgent | Coordinates all agents, handles failures, records traces |

---

## 📄 Document Types Supported

| Type | Fields Extracted |
|------|-----------------|
| **Invoice** | Vendor, GSTIN, invoice number, dates, PO number, line items, subtotal, tax, total, payment terms |
| **KYC** | Document type, number, name, DOB, nationality, address, issue/expiry dates |
| **Contract** | Parties, effective/expiry dates, payment terms, termination notice, governing law, clauses |
| **Claim** | Claimant, claim ID, incident date, amount, claim type, status |
| **Other** | Raw text preserved; classification uncertainty reported |

---

## 🔍 Validation Rules (Deterministic)

- **INV_TOTAL_MISMATCH** — Subtotal + Tax ≠ Stated Total (tolerates ±₹1 rounding)
- **INV_MISSING_VENDOR** — Vendor name absent
- **INV_MISSING_STATED_TOTAL** — Total absent
- **INV_DUPLICATE** — Duplicate invoice number from same vendor
- **KYC_EXPIRED** — Document expiry date in the past (Critical)
- **KYC_EXPIRY_OK** — Document valid
- **CONTRACT_MISSING_DATES** — Effective/expiry dates absent
- **CONTRACT_PAST_EXPIRY** — Contract already expired
- Custom rules via Business Rules editor (threshold/required_field/vendor_check/due_date)

---

## 🗄️ Database

SQLite at `data/documind.db`. WAL mode enabled. Schema:

- `documents` — one row per processed document
- `document_pages` — page-level text
- `extracted_fields` — per-field with provenance (method, confidence, page)
- `validation_findings` — all rule results (pass/fail with severity)
- `agent_events` — per-agent execution trace
- `audit_events` — immutable event log
- `review_decisions` — human corrections with before/after
- `business_rules` — configurable rules (persist across restarts)
- `reference_entities` — vendor/customer registry
- `contract_templates` / `clause_comparisons` — clause comparison

---

## 🖥️ Streamlit Pages

| Page | Feature |
|------|---------|
| Overview | KPI tiles, charts, recent activity, demo workflow button |
| Document Workspace | Upload, list, detail view (fields + findings + agent trace + exports) |
| Batch Processing | Multi-file upload, progress, batch CSV export |
| Human Review Center | Review queue, field corrections, before/after diff, mark Ready |
| Business Rules | CRUD for validation rules and reference entities |
| Contract Intelligence | Clause-by-clause comparison against editable templates |
| Audit Trail | Immutable event timeline with filtering and CSV export |
| Analytics | Risk distribution, issue breakdown, agent performance |
| Settings & Health | Dependency checks, config display, data management |

---

## 🧪 Running Tests

```bash
python -m pytest tests/test_documind.py -v
```

**30 tests covering:**
- Correct and discrepant invoice totals
- Missing mandatory fields
- Expired/unexpired KYC
- Registered/unregistered vendors
- Unknown document classification
- Invalid LLM response handling
- No API key / API failure graceful fallback
- Corrupt and unsupported files
- Duplicate invoice number detection
- Duplicate hash detection
- Review correction persistence
- Business rule persistence and application
- Audit event creation
- JSON and CSV export
- Batch isolation (one failure doesn't stop batch)
- Source provenance integrity
- SQLite persistence across restart
- No-LLM fallback mode
- Orchestrator sequencing and agent trace
- Contract clause comparison

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | *(empty)* | OpenRouter API key (optional) |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Model for LLM tasks |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API endpoint |
| `ENABLE_LLM_CLASSIFICATION` | `true` | Use LLM when key available |
| `ENABLE_LLM_EXTRACTION` | `true` | LLM field enhancement |
| `LLM_TIMEOUT_SECONDS` | `30` | API call timeout |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max file size |
| `LOW_RISK_THRESHOLD` | `0.35` | Below = Ready |
| `HIGH_RISK_THRESHOLD` | `0.70` | Above = High Risk |
| `TESSERACT_CMD` | *(auto-detect)* | Custom Tesseract path |
| `DEMO_MODE` | `false` | Enable demo mode globally |

---

## 🔒 Limitations

- **OCR**: Requires Tesseract installation for image-based documents. PDF embedded text works without it.
- **LLM**: OpenRouter API key required for AI-enhanced classification/extraction. Rule-based fallback always available.
- **No real authentication**: Multi-user isolation not implemented (single-user SME deployment).
- **Language**: Full support for English documents. Hindi/multilingual text works if Tesseract language packs installed.
- **Not a legal/financial authority**: This is a decision-support tool; all outputs require human verification.

---

## 🛠️ Troubleshooting

**App fails to start:**
```bash
pip install -r requirements.txt
```

**No text extracted from PDF:**
- Ensure the PDF is not scanned/image-only
- Install Tesseract for OCR: `choco install tesseract` (Windows)

**LLM features not working:**
- Check `OPENROUTER_API_KEY` in `.env`
- Use Settings > System Health > Test API Connectivity

**Database issues:**
- Delete `data/documind.db` and restart to reinitialize
- All persistent data will be cleared
