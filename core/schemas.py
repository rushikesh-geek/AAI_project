"""
DocuMind AI — Pydantic schemas for all domain objects.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Enumerations ────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    INVOICE = "Invoice"
    KYC = "KYC"
    CONTRACT = "Contract"
    CLAIM = "Claim"
    OTHER = "Other"


class ProcessingStatus(str, Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    READY = "Ready"
    NEEDS_REVIEW = "Needs Review"
    HIGH_RISK = "High Risk"
    FAILED = "Failed"
    REJECTED = "Rejected"


class FindingSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Field Provenance ────────────────────────────────────────────────────────

class FieldProvenance(BaseModel):
    field_name: str
    page_number: Optional[int] = None
    bbox: Optional[list[float]] = None          # [x0, y0, x1, y1]
    source_text: Optional[str] = None
    extraction_method: str = "text"             # text | ocr | llm | rule
    confidence: float = 1.0


# ── Extracted Fields ────────────────────────────────────────────────────────

class LineItem(BaseModel):
    description: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    hsn_code: Optional[str] = None


class InvoiceExtraction(BaseModel):
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    currency: str = "INR"
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    stated_total: Optional[float] = None
    payment_terms: Optional[str] = None
    bank_details: Optional[str] = None
    notes: Optional[str] = None


class KYCExtraction(BaseModel):
    full_name: Optional[str] = None
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None
    has_signature: Optional[bool] = None
    has_photo: Optional[bool] = None
    issuing_authority: Optional[str] = None


class ContractParty(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    address: Optional[str] = None


class ContractExtraction(BaseModel):
    parties: list[ContractParty] = Field(default_factory=list)
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    contract_value: Optional[float] = None
    currency: str = "INR"
    payment_terms: Optional[str] = None
    termination_notice: Optional[str] = None
    renewal_terms: Optional[str] = None
    governing_law: Optional[str] = None
    key_clauses: dict[str, str] = Field(default_factory=dict)
    obligations: list[str] = Field(default_factory=list)


class ClaimExtraction(BaseModel):
    claimant_name: Optional[str] = None
    claim_id: Optional[str] = None
    incident_date: Optional[str] = None
    claim_date: Optional[str] = None
    claim_amount: Optional[float] = None
    claim_type: Optional[str] = None
    supporting_docs: list[str] = Field(default_factory=list)
    status: Optional[str] = None
    description: Optional[str] = None


class OtherExtraction(BaseModel):
    raw_text: Optional[str] = None
    detected_fields: dict[str, Any] = Field(default_factory=dict)
    reason: str = "Document could not be mapped to a known schema."


# ── Validation Findings ─────────────────────────────────────────────────────

class ValidationFinding(BaseModel):
    rule_id: str
    field: Optional[str] = None
    severity: FindingSeverity
    message: str
    expected: Optional[str] = None
    observed: Optional[str] = None
    source_ref: Optional[str] = None
    suggestion: Optional[str] = None
    passed: bool = False


# ── Agent Execution Event ───────────────────────────────────────────────────

class AgentEvent(BaseModel):
    agent_name: str
    status: AgentStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    summary: str = ""
    error: Optional[str] = None
    output_keys: list[str] = Field(default_factory=list)


# ── Document Record ─────────────────────────────────────────────────────────

class DocumentRecord(BaseModel):
    doc_id: str
    filename: str
    file_path: str
    file_hash: str
    file_size: int
    doc_type: Optional[DocumentType] = None
    classification_confidence: float = 0.0
    classification_method: str = "unknown"
    page_count: int = 0
    status: ProcessingStatus = ProcessingStatus.PENDING
    risk_score: float = 0.0
    risk_label: str = "Unknown"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_demo: bool = False
    language: str = "en"
    processing_mode: str = "local"    # local | llm
    error_message: Optional[str] = None


# ── Review Decision ─────────────────────────────────────────────────────────

class ReviewDecision(BaseModel):
    review_id: str
    doc_id: str
    field_name: str
    original_value: Optional[str]
    corrected_value: Optional[str]
    action: str         # accept | correct | mark_unreadable | reject
    reviewer: str
    comment: Optional[str] = None
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)


# ── Export Record ───────────────────────────────────────────────────────────

class ExportRecord(BaseModel):
    doc_id: str
    schema_version: str = "1.0"
    status: str
    doc_type: Optional[str]
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    reviewer_corrections: dict[str, Any] = Field(default_factory=dict)
    validation_findings: list[dict[str, Any]] = Field(default_factory=list)
    risk_score: float
    processing_mode: str
    exported_at: datetime = Field(default_factory=datetime.utcnow)
