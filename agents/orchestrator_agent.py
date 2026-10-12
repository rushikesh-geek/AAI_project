"""
Agent 10 — Orchestrator Agent
Coordinates the complete 9-agent pipeline. Tracks state, handles retries.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Optional

from core.logging_config import get_logger

logger = get_logger(__name__)


class PipelineContext:
    """Carries state through the pipeline for one document."""

    def __init__(self, doc_id: str, filename: str, file_bytes: bytes,
                 is_demo: bool = False):
        self.doc_id = doc_id
        self.filename = filename
        self.file_bytes = file_bytes
        self.is_demo = is_demo
        self.agent_trace: list[dict] = []
        self.errors: list[str] = []
        self.ingestion_result: dict = {}
        self.classification_result: dict = {}
        self.ocr_result: dict = {}
        self.extraction_result: dict = {}
        self.validation_result: dict = {}
        self.reference_result: dict = {}
        self.risk_result: dict = {}
        self.review_package: dict = {}
        self.final_status: str = "Pending"

    def record_agent(self, name: str, status: str, started: float,
                     summary: str = "", error: str = None,
                     output_keys: list[str] = None):
        elapsed = int((time.time() - started) * 1000)
        event = {
            "doc_id": self.doc_id,
            "agent_name": name,
            "status": status,
            "started_at": datetime.utcfromtimestamp(started).isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": elapsed,
            "summary": summary,
            "error": error,
            "output_keys": output_keys or [],
        }
        self.agent_trace.append(event)
        try:
            from core.database import insert_agent_event, insert_audit_event
            insert_agent_event(event)
            insert_audit_event(
                event_type="AGENT",
                action=f"{name}: {status}",
                doc_id=self.doc_id,
                agent=name,
                details=summary or error,
            )
        except Exception as exc:
            logger.warning("Failed to persist agent event: %s", exc)


def run_pipeline(filename: str, file_bytes: bytes,
                 is_demo: bool = False,
                 progress_callback: Optional[Callable[[str, float], None]] = None) -> dict:
    """
    Execute the full document pipeline. Returns a complete result dict.
    progress_callback(message, fraction) called at each stage.
    """
    from core.database import (
        init_db, insert_document, update_document_status,
        insert_pages, insert_extracted_fields, insert_validation_findings,
        insert_audit_event, check_duplicate_hash, get_review_decisions
    )

    def _progress(msg: str, frac: float):
        if progress_callback:
            try:
                progress_callback(msg, frac)
            except Exception:
                pass
        logger.info("[Pipeline] %s (%.0f%%)", msg, frac * 100)

    init_db()
    ctx = PipelineContext("PENDING", filename, file_bytes, is_demo)

    # ══ Stage 1: Ingestion ════════════════════════════════════════════════
    _progress("Ingesting document…", 0.05)
    t0 = time.time()
    try:
        from agents import ingestion_agent
        ctx.ingestion_result = ingestion_agent.run(filename, file_bytes, is_demo)
        if ctx.ingestion_result.get("status") == "failed":
            return _failed_result(ctx, ctx.ingestion_result.get("error", "Ingestion failed"))
        ctx.doc_id = ctx.ingestion_result["doc_id"]
        ctx.ingestion_result["doc_id"] = ctx.doc_id

        # Duplicate hash check
        dup_id = check_duplicate_hash(ctx.ingestion_result["file_hash"], ctx.doc_id)

        # Persist initial document record
        insert_document({
            "doc_id": ctx.doc_id,
            "filename": filename,
            "file_path": ctx.ingestion_result.get("file_path", ""),
            "file_hash": ctx.ingestion_result.get("file_hash", ""),
            "file_size": ctx.ingestion_result.get("file_size", 0),
            "doc_type": None,
            "classification_confidence": 0.0,
            "classification_method": "pending",
            "page_count": ctx.ingestion_result.get("page_count", 0),
            "status": "Processing",
            "risk_score": 0.0,
            "risk_label": "Unknown",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "is_demo": int(is_demo),
            "language": "en",
            "processing_mode": "local",
            "error_message": None,
        })

        ctx.record_agent("IngestionAgent", "success", t0,
                         f"doc_id={ctx.doc_id}, pages={ctx.ingestion_result.get('page_count')}, "
                         f"embedded_text={ctx.ingestion_result.get('embedded_text_available')}",
                         output_keys=["doc_id", "file_hash", "page_count"])
    except Exception as exc:
        return _failed_result(ctx, f"Ingestion exception: {exc}")

    # ══ Stage 2: OCR / Layout ═════════════════════════════════════════════
    _progress("Extracting text / OCR…", 0.20)
    t0 = time.time()
    try:
        from agents import ocr_layout_agent
        ctx.ocr_result = ocr_layout_agent.run(
            ctx.ingestion_result.get("file_path", ""),
            is_image_doc=ctx.ingestion_result.get("is_image_doc", False),
            embedded_text_available=ctx.ingestion_result.get("embedded_text_available", False),
        )
        lang = ctx.ocr_result.get("language", "en")
        update_document_status(ctx.doc_id, "Processing")

        # Persist pages
        if ctx.ocr_result.get("pages"):
            insert_pages(ctx.doc_id, ctx.ocr_result["pages"])

        # Update language
        from core.database import _get_conn
        with _get_conn() as conn:
            conn.execute("UPDATE documents SET language=? WHERE doc_id=?", (lang, ctx.doc_id))

        ctx.record_agent("OCRLayoutAgent", ctx.ocr_result.get("status", "success"), t0,
                         f"pages={len(ctx.ocr_result.get('pages', []))}, "
                         f"ocr_used={ctx.ocr_result.get('ocr_used')}, "
                         f"lang={lang}",
                         error=ctx.ocr_result.get("error"),
                         output_keys=["pages", "full_text"])
    except Exception as exc:
        logger.error("OCR stage failed: %s", exc)
        ctx.ocr_result = {"full_text": "", "pages": [], "status": "failed"}
        ctx.record_agent("OCRLayoutAgent", "failed", t0, error=str(exc))

    full_text = ctx.ocr_result.get("full_text", "")

    # ══ Stage 3: Classification ═══════════════════════════════════════════
    _progress("Classifying document…", 0.35)
    t0 = time.time()
    try:
        from agents import classification_agent
        ctx.classification_result = classification_agent.run(
            full_text, ctx.ingestion_result.get("page_count", 1), filename
        )
        doc_type = ctx.classification_result.get("doc_type", "Other")
        conf = ctx.classification_result.get("confidence", 0.5)
        method = ctx.classification_result.get("method", "rule")

        update_document_status(ctx.doc_id, "Processing", doc_type=doc_type)
        from core.database import _get_conn
        with _get_conn() as conn:
            conn.execute(
                "UPDATE documents SET classification_confidence=?, classification_method=?, processing_mode=? WHERE doc_id=?",
                (conf, method, "llm" if method == "llm" else "local", ctx.doc_id)
            )

        ctx.record_agent("ClassificationAgent", "success", t0,
                         f"type={doc_type}, conf={conf:.2f}, method={method}",
                         output_keys=["doc_type", "confidence"])
    except Exception as exc:
        logger.error("Classification failed: %s", exc)
        doc_type = "Other"
        ctx.classification_result = {"doc_type": doc_type, "confidence": 0.3}
        ctx.record_agent("ClassificationAgent", "failed", t0, error=str(exc))

    # ══ Stage 4: Field Extraction ═════════════════════════════════════════
    _progress("Extracting fields…", 0.50)
    t0 = time.time()
    try:
        from agents import extraction_agent
        ctx.extraction_result = extraction_agent.run(full_text, doc_type, ctx.doc_id)
        extracted = ctx.extraction_result.get("extracted", {})
        fields = ctx.extraction_result.get("fields", [])

        if fields:
            insert_extracted_fields(ctx.doc_id, fields)

        ctx.record_agent("ExtractionAgent", ctx.extraction_result.get("status", "success"), t0,
                         f"fields={len(fields)}, method={ctx.extraction_result.get('method')}",
                         error=ctx.extraction_result.get("error"),
                         output_keys=["extracted", "fields"])
    except Exception as exc:
        logger.error("Extraction failed: %s", exc)
        extracted = {}
        fields = []
        ctx.extraction_result = {"extracted": {}, "fields": []}
        ctx.record_agent("ExtractionAgent", "failed", t0, error=str(exc))

    # ══ Stage 5: Cross-Field Validation ═══════════════════════════════════
    _progress("Validating fields…", 0.62)
    t0 = time.time()
    try:
        from agents import cross_validation_agent
        ctx.validation_result = cross_validation_agent.run(doc_type, extracted, ctx.doc_id)
        val_findings = ctx.validation_result.get("findings", [])
        if val_findings:
            insert_validation_findings(ctx.doc_id, val_findings)

        ctx.record_agent("CrossValidationAgent", ctx.validation_result.get("status", "success"), t0,
                         ctx.validation_result.get("summary", ""),
                         output_keys=["findings"])
    except Exception as exc:
        logger.error("Validation failed: %s", exc)
        val_findings = []
        ctx.validation_result = {"findings": [], "status": "failed"}
        ctx.record_agent("CrossValidationAgent", "failed", t0, error=str(exc))

    # ══ Stage 6: Reference Matching ═══════════════════════════════════════
    _progress("Matching references and rules…", 0.73)
    t0 = time.time()
    try:
        from agents import reference_matching_agent
        ctx.reference_result = reference_matching_agent.run(doc_type, extracted, ctx.doc_id)
        ref_findings = ctx.reference_result.get("findings", [])
        if ref_findings:
            # Append to existing findings
            insert_validation_findings(ctx.doc_id,
                                        val_findings + ref_findings)

        ctx.record_agent("ReferenceMatchingAgent", ctx.reference_result.get("status", "success"), t0,
                         ctx.reference_result.get("summary", ""),
                         output_keys=["findings", "vendor_match"])
    except Exception as exc:
        logger.error("Reference matching failed: %s", exc)
        ref_findings = []
        ctx.reference_result = {"findings": [], "status": "failed"}
        ctx.record_agent("ReferenceMatchingAgent", "failed", t0, error=str(exc))

    # ══ Stage 7: Risk Scoring ══════════════════════════════════════════════
    _progress("Computing risk score…", 0.82)
    t0 = time.time()
    try:
        from agents import risk_scoring_agent
        ctx.risk_result = risk_scoring_agent.run(
            doc_type, extracted,
            val_findings, ref_findings, fields,
            ctx.ingestion_result
        )
        risk_score = ctx.risk_result.get("risk_score", 0.5)
        risk_label = ctx.risk_result.get("risk_label", "Unknown")
        final_status = ctx.risk_result.get("processing_status", "Needs Review")
        ctx.final_status = final_status

        update_document_status(ctx.doc_id, final_status, risk_score=risk_score,
                               risk_label=risk_label)

        ctx.record_agent("RiskScoringAgent", "success", t0,
                         f"score={risk_score:.3f}, label={risk_label}, status={final_status}",
                         output_keys=["risk_score", "risk_label"])
    except Exception as exc:
        logger.error("Risk scoring failed: %s", exc)
        ctx.risk_result = {"risk_score": 0.5, "risk_label": "Unknown", "processing_status": "Needs Review"}
        ctx.record_agent("RiskScoringAgent", "failed", t0, error=str(exc))
        update_document_status(ctx.doc_id, "Needs Review", risk_score=0.5)

    # ══ Stage 8: Review Routing ════════════════════════════════════════════
    _progress("Routing for review…", 0.91)
    t0 = time.time()
    try:
        from agents import review_routing_agent
        ctx.review_package = review_routing_agent.build_review_package(
            ctx.doc_id, doc_type, extracted, fields,
            val_findings, ref_findings, ctx.risk_result
        )
        ctx.record_agent("ReviewRoutingAgent", "success", t0,
                         f"priority={ctx.review_package.get('review_priority')}, "
                         f"critical={len(ctx.review_package.get('critical_findings', []))}",
                         output_keys=["review_package"])
    except Exception as exc:
        logger.error("Review routing failed: %s", exc)
        ctx.review_package = {}
        ctx.record_agent("ReviewRoutingAgent", "failed", t0, error=str(exc))

    # ══ Stage 9: Structured Output (prepare) ══════════════════════════════
    _progress("Preparing outputs…", 0.97)
    t0 = time.time()
    ctx.record_agent("StructuredOutputAgent", "success", t0,
                     "Export data available on demand (JSON/CSV/Excel).",
                     output_keys=["json", "csv", "excel"])

    _progress("Complete!", 1.0)

    insert_audit_event(
        event_type="PIPELINE",
        action="Pipeline completed",
        doc_id=ctx.doc_id,
        details=f"status={ctx.final_status}, risk={ctx.risk_result.get('risk_score', 0):.3f}",
    )

    return {
        "success": True,
        "doc_id": ctx.doc_id,
        "doc_type": doc_type,
        "status": ctx.final_status,
        "risk_score": ctx.risk_result.get("risk_score", 0.5),
        "risk_label": ctx.risk_result.get("risk_label", "Unknown"),
        "classification": ctx.classification_result,
        "extraction": ctx.extraction_result,
        "validation": ctx.validation_result,
        "reference": ctx.reference_result,
        "risk": ctx.risk_result,
        "review_package": ctx.review_package,
        "agent_trace": ctx.agent_trace,
        "is_duplicate_hash": dup_id,
        "ocr_used": ctx.ocr_result.get("ocr_used", False),
        "language": ctx.ocr_result.get("language", "en"),
    }


def _failed_result(ctx: PipelineContext, error: str) -> dict:
    try:
        from core.database import update_document_status
        if ctx.doc_id and ctx.doc_id != "PENDING":
            update_document_status(ctx.doc_id, "Failed", error=error)
    except Exception:
        pass
    return {
        "success": False,
        "doc_id": ctx.doc_id,
        "error": error,
        "agent_trace": ctx.agent_trace,
    }
