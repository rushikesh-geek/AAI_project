"""
DocuMind AI — SQLite database layer.
Handles schema initialization and all CRUD operations.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from core.config import DB_PATH

_lock = threading.Lock()


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema Init ─────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    doc_type TEXT,
    classification_confidence REAL DEFAULT 0,
    classification_method TEXT DEFAULT 'unknown',
    page_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Pending',
    risk_score REAL DEFAULT 0,
    risk_label TEXT DEFAULT 'Unknown',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_demo INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en',
    processing_mode TEXT DEFAULT 'local',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    page_number INTEGER NOT NULL,
    text_content TEXT,
    ocr_used INTEGER DEFAULT 0,
    quality_score REAL DEFAULT 1.0,
    word_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    field_name TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    page_number INTEGER,
    bbox TEXT,
    source_text TEXT,
    extraction_method TEXT DEFAULT 'text',
    confidence REAL DEFAULT 1.0,
    is_missing INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS validation_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    rule_id TEXT NOT NULL,
    field TEXT,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    expected TEXT,
    observed TEXT,
    source_ref TEXT,
    suggestion TEXT,
    passed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    metadata TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT UNIQUE NOT NULL,
    rule_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    parameters TEXT NOT NULL,
    severity TEXT DEFAULT 'Medium',
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_decisions (
    review_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    field_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    action TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    comment TEXT,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER,
    summary TEXT,
    error TEXT,
    output_keys TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    doc_id TEXT,
    agent TEXT,
    action TEXT NOT NULL,
    previous_value TEXT,
    new_value TEXT,
    details TEXT,
    actor TEXT DEFAULT 'system',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    clauses TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clause_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    template_id INTEGER REFERENCES contract_templates(id),
    clause_name TEXT NOT NULL,
    template_text TEXT,
    extracted_text TEXT,
    match_score REAL DEFAULT 0,
    status TEXT DEFAULT 'missing',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_doc_id ON audit_events(doc_id);
CREATE INDEX IF NOT EXISTS idx_validation_findings_doc_id ON validation_findings(doc_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_doc_id ON agent_events(doc_id);
"""

_initialized = False


def init_db() -> None:
    global _initialized
    with _lock:
        if _initialized:
            return
        with _get_conn() as conn:
            conn.executescript(SCHEMA_SQL)
        _initialized = True
        _seed_default_data()


# ── Seeding ──────────────────────────────────────────────────────────────────

def _seed_default_data() -> None:
    """Insert default vendors, rules, and contract template if absent."""
    now = _now()

    # Default vendors
    vendors = [
        "Shree Traders", "Raj Enterprises", "Global Supplies Ltd",
        "ABC Technologies", "XYZ Corporation", "Prime Vendors",
        "Sunrise Distributors", "Metro Logistics"
    ]
    with _get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM reference_entities WHERE entity_type='vendor'").fetchone()[0]
        if existing == 0:
            for v in vendors:
                conn.execute(
                    "INSERT INTO reference_entities(entity_type, name, normalized_name, active, created_at) VALUES (?,?,?,1,?)",
                    ("vendor", v, v.lower().strip(), now)
                )

        # Default business rules
        existing_rules = conn.execute("SELECT COUNT(*) FROM business_rules").fetchone()[0]
        if existing_rules == 0:
            default_rules = [
                ("RULE_HIGH_VALUE", "threshold", "High Value Invoice",
                 "Flag invoices exceeding ₹50,000", json.dumps({"field": "stated_total", "operator": "gt", "value": 50000}),
                 "High"),
                ("RULE_UNREGISTERED_VENDOR", "vendor_check", "Unregistered Vendor",
                 "Flag invoices from vendors not in reference list", json.dumps({"match_threshold": 80}),
                 "High"),
                ("RULE_REQUIRE_PO", "required_field", "Require PO Number",
                 "Invoice must have a purchase order number", json.dumps({"field": "po_number"}),
                 "Medium"),
                ("RULE_DUE_SOON", "due_date", "Due Date Warning",
                 "Flag invoices due within 7 days", json.dumps({"days": 7}),
                 "Low"),
                ("RULE_REQUIRE_GSTIN", "required_field", "Require GSTIN",
                 "Vendor GSTIN must be present", json.dumps({"field": "vendor_gstin"}),
                 "Medium"),
            ]
            for r in default_rules:
                conn.execute(
                    "INSERT INTO business_rules(rule_id,rule_type,name,description,parameters,severity,active,created_at,updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
                    (r[0], r[1], r[2], r[3], r[4], r[5], now, now)
                )

        # Default contract template
        existing_tmpl = conn.execute("SELECT COUNT(*) FROM contract_templates").fetchone()[0]
        if existing_tmpl == 0:
            default_clauses = json.dumps({
                "payment_terms": "Payment shall be made within 30 days of invoice receipt.",
                "termination_notice": "Either party may terminate this agreement with 30 days written notice.",
                "governing_law": "This agreement shall be governed by the laws of India.",
                "liability_cap": "Total liability shall not exceed the contract value for the preceding 12 months.",
                "confidentiality": "Both parties shall maintain strict confidentiality of shared information.",
                "force_majeure": "Neither party shall be liable for delays due to circumstances beyond reasonable control.",
            })
            conn.execute(
                "INSERT INTO contract_templates(name, clauses, created_at, updated_at) VALUES (?,?,?,?)",
                ("Standard Vendor Agreement", default_clauses, now, now)
            )


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Document CRUD ────────────────────────────────────────────────────────────

def insert_document(doc: dict) -> None:
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO documents
            (doc_id, filename, file_path, file_hash, file_size, doc_type,
             classification_confidence, classification_method, page_count, status,
             risk_score, risk_label, created_at, updated_at, is_demo, language,
             processing_mode, error_message)
            VALUES (:doc_id,:filename,:file_path,:file_hash,:file_size,:doc_type,
                    :classification_confidence,:classification_method,:page_count,:status,
                    :risk_score,:risk_label,:created_at,:updated_at,:is_demo,:language,
                    :processing_mode,:error_message)
        """, doc)


def update_document_status(doc_id: str, status: str, risk_score: float = None,
                            risk_label: str = None, error: str = None,
                            doc_type: str = None) -> None:
    fields = ["status=?", "updated_at=?"]
    values: list[Any] = [status, _now()]
    if risk_score is not None:
        fields.append("risk_score=?"); values.append(risk_score)
    if risk_label is not None:
        fields.append("risk_label=?"); values.append(risk_label)
    if error is not None:
        fields.append("error_message=?"); values.append(error)
    if doc_type is not None:
        fields.append("doc_type=?"); values.append(doc_type)
    values.append(doc_id)
    with _get_conn() as conn:
        conn.execute(f"UPDATE documents SET {', '.join(fields)} WHERE doc_id=?", values)


def get_document(doc_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return dict(row) if row else None


def get_all_documents(limit: int = 200) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def check_duplicate_hash(file_hash: str, exclude_doc_id: str = "") -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT doc_id FROM documents WHERE file_hash=? AND doc_id!=?",
            (file_hash, exclude_doc_id)
        ).fetchone()
        return row["doc_id"] if row else None


def check_duplicate_invoice_number(invoice_number: str, exclude_doc_id: str = "") -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT doc_id FROM extracted_fields
            WHERE field_name='invoice_number' AND normalized_value=? AND doc_id!=?
        """, (invoice_number.upper().strip(), exclude_doc_id)).fetchone()
        return row["doc_id"] if row else None


# ── Pages ────────────────────────────────────────────────────────────────────

def insert_pages(doc_id: str, pages: list[dict]) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))
        for p in pages:
            conn.execute("""
                INSERT INTO pages(doc_id, page_number, text_content, ocr_used, quality_score, word_count)
                VALUES (?,?,?,?,?,?)
            """, (doc_id, p.get("page_number"), p.get("text_content"),
                  int(p.get("ocr_used", False)), p.get("quality_score", 1.0),
                  p.get("word_count", 0)))


def get_pages(doc_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM pages WHERE doc_id=? ORDER BY page_number", (doc_id,)).fetchall()
        return [dict(r) for r in rows]


# ── Extracted Fields ─────────────────────────────────────────────────────────

def insert_extracted_fields(doc_id: str, fields: list[dict]) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM extracted_fields WHERE doc_id=?", (doc_id,))
        for f in fields:
            conn.execute("""
                INSERT INTO extracted_fields
                (doc_id, field_name, raw_value, normalized_value, page_number,
                 bbox, source_text, extraction_method, confidence, is_missing)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (doc_id, f.get("field_name"), f.get("raw_value"),
                  f.get("normalized_value"), f.get("page_number"),
                  json.dumps(f.get("bbox")) if f.get("bbox") else None,
                  f.get("source_text"), f.get("extraction_method", "text"),
                  f.get("confidence", 1.0), int(f.get("is_missing", False))))


def get_extracted_fields(doc_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM extracted_fields WHERE doc_id=?", (doc_id,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("bbox"):
                try:
                    d["bbox"] = json.loads(d["bbox"])
                except Exception:
                    d["bbox"] = None
            result.append(d)
        return result


def get_field_value(doc_id: str, field_name: str) -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT normalized_value FROM extracted_fields WHERE doc_id=? AND field_name=?",
            (doc_id, field_name)
        ).fetchone()
        return row[0] if row else None


# ── Validation Findings ──────────────────────────────────────────────────────

def insert_validation_findings(doc_id: str, findings: list[dict]) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM validation_findings WHERE doc_id=?", (doc_id,))
        now = _now()
        for f in findings:
            conn.execute("""
                INSERT INTO validation_findings
                (doc_id, rule_id, field, severity, message, expected, observed,
                 source_ref, suggestion, passed, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (doc_id, f.get("rule_id"), f.get("field"), f.get("severity"),
                  f.get("message"), f.get("expected"), f.get("observed"),
                  f.get("source_ref"), f.get("suggestion"),
                  int(f.get("passed", False)), now))


def get_validation_findings(doc_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM validation_findings WHERE doc_id=? ORDER BY severity", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Reference Entities ───────────────────────────────────────────────────────

def get_reference_entities(entity_type: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reference_entities WHERE entity_type=? AND active=1 ORDER BY name",
            (entity_type,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_reference_entity(entity_type: str, name: str, metadata: dict = None) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO reference_entities(entity_type, name, normalized_name, metadata, active, created_at) VALUES (?,?,?,?,1,?)",
            (entity_type, name, name.lower().strip(),
             json.dumps(metadata) if metadata else None, _now())
        )


def delete_reference_entity(entity_id: int) -> None:
    with _get_conn() as conn:
        conn.execute("UPDATE reference_entities SET active=0 WHERE id=?", (entity_id,))


# ── Business Rules ───────────────────────────────────────────────────────────

def get_business_rules(active_only: bool = True) -> list[dict]:
    with _get_conn() as conn:
        q = "SELECT * FROM business_rules"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY rule_type, name"
        rows = conn.execute(q).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["parameters"] = json.loads(d["parameters"]) if d.get("parameters") else {}
            result.append(d)
        return result


def upsert_business_rule(rule: dict) -> None:
    now = _now()
    params = rule.get("parameters", {})
    if isinstance(params, dict):
        params = json.dumps(params)
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO business_rules(rule_id, rule_type, name, description, parameters, severity, active, created_at, updated_at)
            VALUES (:rule_id,:rule_type,:name,:description,:parameters,:severity,:active,:now,:now)
            ON CONFLICT(rule_id) DO UPDATE SET
            name=excluded.name, description=excluded.description,
            parameters=excluded.parameters, severity=excluded.severity,
            active=excluded.active, updated_at=excluded.updated_at
        """, {**rule, "parameters": params, "now": now})


def toggle_business_rule(rule_id: str, active: bool) -> None:
    with _get_conn() as conn:
        conn.execute("UPDATE business_rules SET active=?, updated_at=? WHERE rule_id=?",
                     (int(active), _now(), rule_id))


def delete_business_rule(rule_id: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM business_rules WHERE rule_id=?", (rule_id,))


# ── Review Decisions ─────────────────────────────────────────────────────────

def insert_review_decision(decision: dict) -> None:
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO review_decisions
            (review_id, doc_id, field_name, original_value, corrected_value,
             action, reviewer, comment, reviewed_at)
            VALUES (:review_id,:doc_id,:field_name,:original_value,:corrected_value,
                    :action,:reviewer,:comment,:reviewed_at)
        """, decision)


def get_review_decisions(doc_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM review_decisions WHERE doc_id=? ORDER BY reviewed_at", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_review_decisions() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM review_decisions ORDER BY reviewed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── Agent Events ─────────────────────────────────────────────────────────────

def insert_agent_event(event: dict) -> None:
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO agent_events
            (doc_id, agent_name, status, started_at, completed_at, duration_ms,
             summary, error, output_keys)
            VALUES (:doc_id,:agent_name,:status,:started_at,:completed_at,:duration_ms,
                    :summary,:error,:output_keys)
        """, {**event, "output_keys": json.dumps(event.get("output_keys", []))})


def get_agent_events(doc_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_events WHERE doc_id=? ORDER BY started_at", (doc_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["output_keys"] = json.loads(d.get("output_keys") or "[]")
            except Exception:
                d["output_keys"] = []
            result.append(d)
        return result


# ── Audit Events ─────────────────────────────────────────────────────────────

def insert_audit_event(event_type: str, action: str, doc_id: str = None,
                       agent: str = None, previous_value: str = None,
                       new_value: str = None, details: str = None,
                       actor: str = "system") -> None:
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO audit_events
            (event_type, doc_id, agent, action, previous_value, new_value,
             details, actor, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (event_type, doc_id, agent, action, previous_value,
              new_value, details, actor, _now()))


def get_audit_events(doc_id: str = None, limit: int = 500) -> list[dict]:
    with _get_conn() as conn:
        if doc_id:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE doc_id=? ORDER BY created_at DESC LIMIT ?",
                (doc_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ── Analytics Queries ─────────────────────────────────────────────────────────

def get_dashboard_metrics() -> dict:
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        ready = conn.execute("SELECT COUNT(*) FROM documents WHERE status='Ready'").fetchone()[0]
        needs_review = conn.execute("SELECT COUNT(*) FROM documents WHERE status='Needs Review'").fetchone()[0]
        high_risk = conn.execute("SELECT COUNT(*) FROM documents WHERE status='High Risk'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM documents WHERE status='Failed'").fetchone()[0]

        type_dist = conn.execute(
            "SELECT doc_type, COUNT(*) as cnt FROM documents WHERE doc_type IS NOT NULL GROUP BY doc_type"
        ).fetchall()

        avg_risk = conn.execute("SELECT AVG(risk_score) FROM documents").fetchone()[0] or 0.0

        critical_findings = conn.execute(
            "SELECT COUNT(*) FROM validation_findings WHERE severity IN ('Critical','High') AND passed=0"
        ).fetchone()[0]

        agent_failures = conn.execute(
            "SELECT COUNT(*) FROM agent_events WHERE status='failed'"
        ).fetchone()[0]

        total_agents = conn.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0]
        agent_failure_rate = (agent_failures / total_agents * 100) if total_agents > 0 else 0

        review_backlog = conn.execute(
            "SELECT COUNT(DISTINCT doc_id) FROM documents WHERE status IN ('Needs Review','High Risk')"
        ).fetchone()[0]

        return {
            "total": total,
            "ready": ready,
            "needs_review": needs_review,
            "high_risk": high_risk,
            "failed": failed,
            "avg_risk": round(avg_risk, 3),
            "critical_findings": critical_findings,
            "agent_failure_rate": round(agent_failure_rate, 1),
            "review_backlog": review_backlog,
            "type_distribution": {row[0]: row[1] for row in type_dist},
        }


# ── Contract Templates ────────────────────────────────────────────────────────

def get_contract_templates() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM contract_templates ORDER BY name").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["clauses"] = json.loads(d["clauses"])
            except Exception:
                d["clauses"] = {}
            result.append(d)
        return result


def update_contract_template(template_id: int, clauses: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE contract_templates SET clauses=?, updated_at=? WHERE id=?",
            (json.dumps(clauses), _now(), template_id)
        )


def insert_clause_comparisons(doc_id: str, comparisons: list[dict]) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM clause_comparisons WHERE doc_id=?", (doc_id,))
        now = _now()
        for c in comparisons:
            conn.execute("""
                INSERT INTO clause_comparisons
                (doc_id, template_id, clause_name, template_text, extracted_text,
                 match_score, status, created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (doc_id, c.get("template_id"), c.get("clause_name"),
                  c.get("template_text"), c.get("extracted_text"),
                  c.get("match_score", 0), c.get("status", "missing"), now))


def get_clause_comparisons(doc_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM clause_comparisons WHERE doc_id=? ORDER BY clause_name", (doc_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Utilities ─────────────────────────────────────────────────────────────────

def clear_demo_data() -> None:
    """Remove all documents marked as demo, cascading to related tables."""
    with _get_conn() as conn:
        demo_ids = [row[0] for row in conn.execute(
            "SELECT doc_id FROM documents WHERE is_demo=1"
        ).fetchall()]
        for did in demo_ids:
            for tbl in ("pages", "extracted_fields", "validation_findings",
                        "review_decisions", "agent_events", "clause_comparisons"):
                conn.execute(f"DELETE FROM {tbl} WHERE doc_id=?", (did,))
            conn.execute("DELETE FROM audit_events WHERE doc_id=?", (did,))
        if demo_ids:
            placeholders = ",".join("?" * len(demo_ids))
            conn.execute(f"DELETE FROM documents WHERE doc_id IN ({placeholders})", demo_ids)
