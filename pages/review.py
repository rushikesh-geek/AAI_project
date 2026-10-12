"""Human Review Center page"""
from __future__ import annotations

import streamlit as st
from pathlib import Path
import pandas as pd


def _severity_color(sev: str) -> str:
    return {"Critical": "#EF4444", "High": "#F97316", "Medium": "#F59E0B",
            "Low": "#3B82F6", "Info": "#22D3EE"}.get(sev, "#94A3B8")


def render():
    st.markdown("## 👁️ Human Review Center")

    from core.database import get_all_documents, get_validation_findings, get_extracted_fields
    from core.schemas import ProcessingStatus
    from agents.review_routing_agent import get_review_queue

    queue = get_review_queue()

    if not queue:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("""
<div style="text-align:center; padding:3rem; color:#64748B;">
  <div style="font-size:3.5rem; margin-bottom:1rem;">✅</div>
  <div style="font-size:1.2rem; font-weight:600; color:#10B981;">Review Queue Empty</div>
  <div style="margin-top:0.5rem;">All documents have been reviewed or no documents require review.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Show completed reviews
        _show_completed_reviews()
        return

    # Queue summary
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(f'<div class="dm-metric"><div class="value" style="color:#FCD34D;">{len(queue)}</div><div class="label">In Review Queue</div></div>', unsafe_allow_html=True)
    with col_b:
        high_risk = sum(1 for d in queue if d.get("status") == "High Risk")
        st.markdown(f'<div class="dm-metric"><div class="value" style="color:#EF4444;">{high_risk}</div><div class="label">High Risk</div></div>', unsafe_allow_html=True)
    with col_c:
        needs_review = sum(1 for d in queue if d.get("status") == "Needs Review")
        st.markdown(f'<div class="dm-metric"><div class="value" style="color:#F59E0B;">{needs_review}</div><div class="label">Needs Review</div></div>', unsafe_allow_html=True)

    st.markdown("")

    # Document selector
    doc_options = {}
    for d in sorted(queue, key=lambda x: x.get("risk_score", 0), reverse=True):
        risk_pct = int(d.get("risk_score", 0) * 100)
        status = d.get("status", "")
        label = f"[{status}] {d['doc_id']} — {d['filename'][:35]} (Risk: {risk_pct}%)"
        doc_options[label] = d["doc_id"]

    selected_label = st.selectbox("Select document to review", list(doc_options.keys()), key="review_select")
    doc_id = doc_options[selected_label]
    doc = next(d for d in queue if d["doc_id"] == doc_id)

    _render_review_form(doc)
    _show_completed_reviews()


def _render_review_form(doc: dict):
    from core.database import get_extracted_fields, get_validation_findings, get_review_decisions
    from agents.ingestion_agent import render_page_image
    from agents.review_routing_agent import record_review_decision

    doc_id = doc["doc_id"]
    fields = get_extracted_fields(doc_id)
    findings = get_validation_findings(doc_id)
    existing_reviews = get_review_decisions(doc_id)
    corrections_map = {r["field_name"]: r for r in existing_reviews}
    failures = [f for f in findings if not f.get("passed")]

    st.markdown("---")
    col_prev, col_form = st.columns([1, 1])

    with col_prev:
        st.markdown("#### 📄 Source Document")
        file_path = doc.get("file_path", "")
        if file_path and Path(file_path).exists():
            img = render_page_image(file_path, page_number=1, dpi=120)
            if img:
                st.image(img, caption=f"Page 1 — {doc.get('filename', '')}", use_container_width=True)
        else:
            st.warning("Source file not available for preview.")

        # Findings summary
        st.markdown("#### ⚠️ Validation Findings")
        for f in failures[:8]:
            sev = f.get("severity", "Info")
            color = _severity_color(sev)
            st.markdown(f"""
<div style="border-left:3px solid {color}; padding:0.4rem 0.6rem; margin:0.25rem 0; background:#0F172A; border-radius:0 4px 4px 0; font-size:0.78rem;">
  <span style="color:{color}; font-weight:600;">[{sev}]</span>
  <span style="color:#CBD5E1;"> {f.get('message','')[:100]}</span>
</div>""", unsafe_allow_html=True)

        if not failures:
            st.success("No critical validation findings.")

    with col_form:
        st.markdown("#### ✏️ Review & Correct Fields")

        reviewer = st.text_input("Reviewer name / ID", value="Demo Reviewer", key=f"reviewer_{doc_id}")
        comment = st.text_area("General comment (optional)", key=f"comment_{doc_id}", height=60)

        if not fields:
            st.info("No extracted fields to review.")
            return

        review_actions: list[dict] = []

        for f in fields[:20]:
            fname = f.get("field_name", "")
            current_val = f.get("normalized_value") or ""
            prior_review = corrections_map.get(fname)

            is_flagged = any(
                fin.get("field") == fname and not fin.get("passed")
                for fin in findings
            )
            flag_indicator = " 🚩" if is_flagged else ""

            with st.expander(f"{fname}{flag_indicator}", expanded=is_flagged):
                col_orig, col_action = st.columns([1.5, 1])
                with col_orig:
                    st.markdown(f'<span style="color:#94A3B8; font-size:0.7rem;">Current value:</span>', unsafe_allow_html=True)
                    st.code(current_val if current_val else "(empty)", language=None)
                    if prior_review:
                        st.markdown(f'<span style="color:#818CF8; font-size:0.7rem;">✓ Already reviewed ({prior_review["action"]})</span>', unsafe_allow_html=True)

                with col_action:
                    action = st.selectbox(
                        "Action",
                        ["accept", "correct", "mark_unreadable", "reject"],
                        key=f"action_{doc_id}_{fname}",
                        index=0,
                    )

                corrected_val = current_val
                if action == "correct":
                    corrected_val = st.text_input(
                        "Corrected value",
                        value=prior_review.get("corrected_value", current_val) if prior_review else current_val,
                        key=f"corrected_{doc_id}_{fname}",
                    )

                review_actions.append({
                    "field_name": fname,
                    "action": action,
                    "original_value": current_val,
                    "corrected_value": corrected_val if action == "correct" else None,
                })

        col_save, col_approve = st.columns(2)
        with col_save:
            if st.button("💾 Save Review Decisions", key=f"save_review_{doc_id}"):
                _save_reviews(doc_id, reviewer, comment, review_actions)

        with col_approve:
            if st.button("✅ Mark as Reviewed (Ready)", key=f"approve_{doc_id}"):
                _save_reviews(doc_id, reviewer, comment, review_actions)
                from core.database import update_document_status
                update_document_status(doc_id, "Ready")
                from core.database import insert_audit_event
                insert_audit_event("REVIEW", "Marked Ready by reviewer", doc_id=doc_id,
                                   actor=reviewer, details=comment)
                st.success(f"✅ Document {doc_id} marked as Ready.")
                st.rerun()


def _save_reviews(doc_id: str, reviewer: str, comment: str, actions: list):
    from agents.review_routing_agent import record_review_decision
    saved = 0
    for a in actions:
        if a["action"] != "accept":  # Only record non-accept actions
            record_review_decision(
                doc_id=doc_id,
                field_name=a["field_name"],
                action=a["action"],
                original_value=a["original_value"],
                corrected_value=a["corrected_value"],
                reviewer=reviewer,
                comment=comment if comment else None,
            )
            saved += 1
    if saved:
        st.success(f"✅ Saved {saved} review decision(s).")
    else:
        st.info("No changes recorded (all fields accepted).")
    st.rerun()


def _show_completed_reviews():
    from core.database import get_all_review_decisions, get_all_documents
    reviews = get_all_review_decisions()
    if not reviews:
        return

    st.markdown("---")
    st.markdown("### 📋 Correction History")

    docs = get_all_documents(200)
    doc_names = {d["doc_id"]: d["filename"] for d in docs}

    rows = []
    for r in reviews[:30]:
        orig = r.get("original_value") or "—"
        corr = r.get("corrected_value") or "—"
        rows.append({
            "Doc ID": r.get("doc_id", ""),
            "Filename": doc_names.get(r.get("doc_id", ""), "—")[:30],
            "Field": r.get("field_name", ""),
            "Action": r.get("action", ""),
            "Original": orig[:30],
            "Corrected": corr[:30],
            "Reviewer": r.get("reviewer", ""),
            "Reviewed At": r.get("reviewed_at", "")[:16],
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
