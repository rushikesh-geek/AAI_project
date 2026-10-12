"""Contract Intelligence page"""
from __future__ import annotations

import json
import streamlit as st
import pandas as pd
from rapidfuzz import fuzz


def _compare_clauses(extracted: dict, template: dict) -> list[dict]:
    """Compare extracted contract clauses against template clauses."""
    comparisons = []
    for clause_name, template_text in template.items():
        extracted_text = extracted.get(clause_name) or ""
        if extracted_text:
            score = fuzz.token_sort_ratio(template_text.lower(), extracted_text.lower()) / 100.0
            if score > 0.8:
                status = "match"
            elif score > 0.5:
                status = "partial"
            else:
                status = "deviation"
        else:
            score = 0.0
            status = "missing"
        comparisons.append({
            "clause_name": clause_name,
            "template_text": template_text,
            "extracted_text": extracted_text or None,
            "match_score": round(score, 3),
            "status": status,
        })
    return comparisons


def render():
    st.markdown("## 📋 Contract Intelligence")

    tab_compare, tab_template = st.tabs(["🔍 Clause Comparison", "📝 Template Editor"])

    with tab_compare:
        _render_comparison()

    with tab_template:
        _render_template_editor()


def _render_comparison():
    from core.database import (
        get_all_documents, get_extracted_fields, get_contract_templates,
        insert_clause_comparisons, get_clause_comparisons
    )

    # Filter contract documents
    docs = get_all_documents(200)
    contract_docs = [d for d in docs if d.get("doc_type") == "Contract"]

    if not contract_docs:
        st.markdown("""
<div style="text-align:center; padding:3rem; color:#64748B;">
  <div style="font-size:3rem;">📋</div>
  <div style="margin-top:0.5rem;">No contract documents processed yet.</div>
  <div style="font-size:0.85rem; margin-top:0.3rem;">Upload a contract document in the Workspace.</div>
</div>""", unsafe_allow_html=True)
        return

    templates = get_contract_templates()
    if not templates:
        st.warning("No contract templates found. Add one in the Template Editor tab.")
        return

    col_doc, col_tmpl = st.columns([2, 1])
    with col_doc:
        doc_options = {f"{d['doc_id']} — {d['filename'][:40]}": d["doc_id"] for d in contract_docs}
        selected_doc_label = st.selectbox("Select Contract Document", list(doc_options.keys()), key="contract_doc_select")
        doc_id = doc_options[selected_doc_label]

    with col_tmpl:
        tmpl_options = {t["name"]: t for t in templates}
        selected_tmpl_name = st.selectbox("Reference Template", list(tmpl_options.keys()), key="contract_tmpl_select")
        template = tmpl_options[selected_tmpl_name]

    if st.button("🔍 Run Clause Comparison", key="run_comparison_btn"):
        fields = get_extracted_fields(doc_id)
        # Build extracted clauses dict from key_clauses field
        key_clauses_field = next((f for f in fields if f.get("field_name") == "key_clauses"), None)
        extracted_clauses = {}
        if key_clauses_field:
            raw = key_clauses_field.get("normalized_value") or "{}"
            try:
                extracted_clauses = json.loads(raw.replace("'", '"'))
            except Exception:
                pass

        # Also check payment_terms, termination_notice etc. directly
        for f in fields:
            fname = f.get("field_name", "")
            if fname in template["clauses"]:
                extracted_clauses[fname] = f.get("normalized_value") or ""

        comparisons = _compare_clauses(extracted_clauses, template["clauses"])

        # Persist
        for c in comparisons:
            c["template_id"] = template["id"]
        insert_clause_comparisons(doc_id, comparisons)

        st.success(f"Compared {len(comparisons)} clauses against '{template['name']}'")
        st.rerun()

    # Show existing comparisons
    comparisons = get_clause_comparisons(doc_id)
    if comparisons:
        st.markdown("---")
        st.markdown("#### Clause-by-Clause Comparison")

        status_colors = {
            "match": "#10B981", "partial": "#F59E0B",
            "deviation": "#EF4444", "missing": "#64748B"
        }
        status_icons = {"match": "✅", "partial": "⚠️", "deviation": "❌", "missing": "—"}

        # Summary row
        status_counts = {}
        for c in comparisons:
            s = c.get("status", "missing")
            status_counts[s] = status_counts.get(s, 0) + 1

        cols = st.columns(4)
        for col, (s, icon) in zip(cols, [("match", "✅"), ("partial", "⚠️"), ("deviation", "❌"), ("missing", "—")]):
            with col:
                cnt = status_counts.get(s, 0)
                color = status_colors[s]
                st.markdown(f'<div class="dm-metric"><div class="value" style="color:{color};">{icon} {cnt}</div><div class="label">{s.title()}</div></div>', unsafe_allow_html=True)

        st.markdown("")
        for c in comparisons:
            status = c.get("status", "missing")
            color = status_colors.get(status, "#94A3B8")
            icon = status_icons.get(status, "—")
            score = c.get("match_score", 0)
            clause = c.get("clause_name", "").replace("_", " ").title()

            with st.expander(f"{icon} **{clause}** — Match: {score:.0%}"):
                col_t, col_e = st.columns(2)
                with col_t:
                    st.markdown("**Template (Expected):**")
                    st.markdown(f'<div style="background:#0F172A; border:1px solid #334155; border-radius:6px; padding:0.75rem; font-size:0.8rem; color:#94A3B8;">{c.get("template_text","—")}</div>', unsafe_allow_html=True)
                with col_e:
                    st.markdown("**Extracted (Contract):**")
                    extracted = c.get("extracted_text") or "*(not found)*"
                    text_color = color if c.get("extracted_text") else "#64748B"
                    st.markdown(f'<div style="background:#0F172A; border:1px solid {color}; border-radius:6px; padding:0.75rem; font-size:0.8rem; color:{text_color};">{extracted}</div>', unsafe_allow_html=True)

                if status == "deviation":
                    st.warning(f"⚠️ Clause deviates from standard template. Manual review recommended.")
                elif status == "missing":
                    st.error("❌ This clause is missing from the contract.")
    else:
        st.info("Run clause comparison to see results.")


def _render_template_editor():
    from core.database import get_contract_templates, update_contract_template

    templates = get_contract_templates()
    if not templates:
        st.info("No templates available.")
        return

    tmpl_options = {t["name"]: t for t in templates}
    selected = st.selectbox("Select Template", list(tmpl_options.keys()), key="tmpl_editor_select")
    template = tmpl_options[selected]

    st.markdown(f"#### Editing: {template['name']}")
    st.markdown("Each clause will be compared against extracted contract clauses.")

    clauses = template.get("clauses", {})
    updated_clauses = {}

    for clause_name, clause_text in clauses.items():
        display_name = clause_name.replace("_", " ").title()
        updated_text = st.text_area(
            f"**{display_name}**",
            value=clause_text,
            key=f"tmpl_clause_{template['id']}_{clause_name}",
            height=80,
        )
        updated_clauses[clause_name] = updated_text

    # Add new clause
    st.markdown("---")
    st.markdown("**Add New Clause:**")
    col_cn, col_ct = st.columns([1, 2])
    with col_cn:
        new_clause_name = st.text_input("Clause name (snake_case)", key="new_clause_name",
                                         placeholder="e.g. liability_cap")
    with col_ct:
        new_clause_text = st.text_area("Clause text", key="new_clause_text", height=60)

    col_save, col_add = st.columns(2)
    with col_save:
        if st.button("💾 Save Template", key="save_template_btn"):
            update_contract_template(template["id"], updated_clauses)
            st.success("Template saved!")

    with col_add:
        if st.button("➕ Add Clause", key="add_clause_btn") and new_clause_name and new_clause_text:
            updated_clauses[new_clause_name.strip().lower().replace(" ", "_")] = new_clause_text
            update_contract_template(template["id"], updated_clauses)
            st.success(f"Clause '{new_clause_name}' added!")
            st.rerun()
