"""Document Workspace page"""
from __future__ import annotations

import streamlit as st
from pathlib import Path
import pandas as pd


def _status_badge(status: str) -> str:
    colors = {
        "Ready": ("#064E3B", "#34D399"),
        "Needs Review": ("#713F12", "#FCD34D"),
        "High Risk": ("#7F1D1D", "#FCA5A5"),
        "Failed": ("#1E293B", "#64748B"),
        "Processing": ("#1E3A5F", "#60A5FA"),
    }
    bg, fg = colors.get(status, ("#1E293B", "#94A3B8"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:9999px;font-size:0.7rem;font-weight:600;">{status}</span>'


def _severity_color(sev: str) -> str:
    return {"Critical": "#EF4444", "High": "#F97316", "Medium": "#F59E0B",
            "Low": "#3B82F6", "Info": "#22D3EE"}.get(sev, "#94A3B8")


def render():
    st.markdown("## 📄 Document Workspace")

    tab_upload, tab_list, tab_detail = st.tabs(["📤 Upload & Process", "📋 Document List", "🔍 Detail View"])

    # ─── Upload Tab ────────────────────────────────────────────────────────
    with tab_upload:
        _render_upload()

    # ─── Document List Tab ─────────────────────────────────────────────────
    with tab_list:
        _render_list()

    # ─── Detail Tab ───────────────────────────────────────────────────────
    with tab_detail:
        _render_detail()


def _render_upload():
    from core.database import init_db
    init_db()

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("### Upload Documents")
        uploaded = st.file_uploader(
            "Drag & drop PDF, PNG, JPG, JPEG, or TIFF files",
            type=["pdf", "png", "jpg", "jpeg", "tiff", "tif"],
            accept_multiple_files=True,
            key="workspace_uploader",
        )
        
        col_a, col_b = st.columns(2)
        with col_a:
            is_demo = st.checkbox("Mark as demo data", value=False, key="ws_demo_flag")
        with col_b:
            run_btn = st.button("▶ Process All Uploads", key="ws_process_btn", disabled=not uploaded)

        if uploaded and run_btn:
            _process_uploads(uploaded, is_demo)

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("### Quick Demo")
        st.markdown("Load pre-built synthetic documents (Invoice, KYC, Contract)")
        if st.button("▶ Load & Process Demo Docs", key="ws_demo_btn"):
            _run_demo_quick()
        st.markdown('</div>', unsafe_allow_html=True)


def _process_uploads(uploaded_files, is_demo: bool):
    from agents.orchestrator_agent import run_pipeline

    results = []
    progress = st.progress(0.0, text="Starting…")
    status_container = st.empty()

    for idx, uf in enumerate(uploaded_files):
        file_bytes = uf.read()

        def _cb(msg, frac, _idx=idx, _total=len(uploaded_files)):
            overall = (_idx + frac) / _total
            progress.progress(overall, text=f"[{uf.name}] {msg}")

        status_container.info(f"⚙️ Processing: **{uf.name}**…")
        result = run_pipeline(uf.name, file_bytes, is_demo=is_demo, progress_callback=_cb)
        results.append((uf.name, result))

    progress.progress(1.0, text="Done!")
    status_container.empty()

    # Show results
    for filename, r in results:
        if r.get("success"):
            doc_type = r.get("doc_type", "Other")
            status = r.get("status", "Unknown")
            risk = r.get("risk_score", 0)
            doc_id = r.get("doc_id", "")
            st.success(f"✅ **{filename}** → `{doc_type}` | Status: `{status}` | Risk: `{risk:.1%}` | ID: `{doc_id}`")
        else:
            st.error(f"❌ **{filename}** failed: {r.get('error', 'Unknown error')}")

    if results:
        st.rerun()


def _run_demo_quick():
    from core.config import DEMO_DIR
    from assets.demo.demo_generator import create_demo_documents
    from agents.orchestrator_agent import run_pipeline

    with st.spinner("Generating and processing demo documents…"):
        demo_files = create_demo_documents(DEMO_DIR)
        progress = st.progress(0.0)
        for i, (name, path) in enumerate(demo_files.items()):
            if path.exists():
                def _cb(msg, frac, _i=i): progress.progress((_i + frac) / len(demo_files))
                run_pipeline(path.name, path.read_bytes(), is_demo=True, progress_callback=_cb)
    st.success("Demo documents processed! Check Document List.")
    st.rerun()


def _render_list():
    from core.database import get_all_documents

    col_filter, col_btn = st.columns([3, 1])
    with col_filter:
        filter_status = st.selectbox("Filter by status", ["All", "Ready", "Needs Review", "High Risk", "Failed"], key="ws_list_filter")
    with col_btn:
        if st.button("🗑 Clear Demo Data", key="ws_clear_demo"):
            from core.database import clear_demo_data
            clear_demo_data()
            st.rerun()

    docs = get_all_documents(200)
    if filter_status != "All":
        docs = [d for d in docs if d.get("status") == filter_status]

    if not docs:
        st.markdown("""
<div style="text-align:center; padding:3rem; color:#64748B;">
  <div style="font-size:3rem;">📭</div>
  <div style="margin-top:0.5rem;">No documents found. Upload files or run the demo.</div>
</div>""", unsafe_allow_html=True)
        return

    # Display as table
    rows = []
    for d in docs:
        rows.append({
            "ID": d.get("doc_id", ""),
            "Filename": (d.get("filename", ""))[:40],
            "Type": d.get("doc_type") or "—",
            "Status": d.get("status", ""),
            "Risk Score": d.get("risk_score", 0),
            "Pages": d.get("page_count", 0),
            "Demo": "✓" if d.get("is_demo") else "",
            "Processed": d.get("created_at", "")[:16],
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Risk Score": st.column_config.ProgressColumn("Risk Score", min_value=0, max_value=1, format="%.0%"),
        }
    )


def _render_detail():
    from core.database import (
        get_all_documents, get_extracted_fields, get_validation_findings,
        get_agent_events, get_review_decisions
    )
    from agents.structured_output_agent import export_json, export_csv, export_excel, generate_summary_report
    from agents.ingestion_agent import render_page_image

    docs = get_all_documents(200)
    if not docs:
        st.info("No documents available. Process some documents first.")
        return

    doc_options = {f"{d['doc_id']} — {d['filename'][:40]} ({d.get('status','')})": d["doc_id"] for d in docs}
    selected_label = st.selectbox("Select Document", list(doc_options.keys()), key="ws_detail_select")
    doc_id = doc_options[selected_label]

    # Find doc
    doc = next((d for d in docs if d["doc_id"] == doc_id), None)
    if not doc:
        return

    col_preview, col_data = st.columns([1, 1])

    with col_preview:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Document Preview")
        file_path = doc.get("file_path", "")
        if file_path and Path(file_path).exists():
            img_bytes = render_page_image(file_path, page_number=1, dpi=130)
            if img_bytes:
                st.image(img_bytes, caption="Page 1", use_container_width=True)
            else:
                st.warning("Preview unavailable for this file type.")
        else:
            st.warning("Source file not available for preview.")

        # Document metadata
        st.markdown(f"""
<div style="margin-top:1rem;">
  <div style="color:#64748B; font-size:0.7rem; text-transform:uppercase;">Metadata</div>
  <div style="color:#CBD5E1; font-size:0.82rem; margin-top:0.4rem;">
    <b>ID:</b> {doc.get('doc_id')}<br>
    <b>Type:</b> {doc.get('doc_type') or '—'}<br>
    <b>Pages:</b> {doc.get('page_count', 0)}<br>
    <b>Mode:</b> {doc.get('processing_mode', 'local')}<br>
    <b>Lang:</b> {doc.get('language', 'en')}<br>
    <b>Conf:</b> {doc.get('classification_confidence', 0):.0%}
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_data:
        status = doc.get("status", "Unknown")
        risk = doc.get("risk_score", 0)
        st.markdown(f"""
<div class="dm-card">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      {_status_badge(status)}
      <span style="color:#94A3B8; font-size:0.8rem; margin-left:0.5rem;">{doc.get('filename','')[:40]}</span>
    </div>
    <div style="color:{'#EF4444' if risk > 0.7 else '#F59E0B' if risk > 0.35 else '#10B981'}; font-weight:700;">
      Risk: {risk:.0%}
    </div>
  </div>
</div>""", unsafe_allow_html=True)

        # Tabs: Fields | Findings | Trace | Export
        inner_tabs = st.tabs(["📊 Fields", "⚠️ Findings", "🔄 Agent Trace", "⬇️ Export"])

        with inner_tabs[0]:
            fields = get_extracted_fields(doc_id)
            reviews = get_review_decisions(doc_id)
            corrections = {r["field_name"]: r["corrected_value"] for r in reviews if r["action"] == "correct"}

            if fields:
                for f in fields[:30]:
                    fname = f.get("field_name", "")
                    val = f.get("normalized_value") or "—"
                    corrected = corrections.get(fname)
                    conf = f.get("confidence", 1.0)
                    method = f.get("extraction_method", "text")
                    page = f.get("page_number")
                    page_ref = f" (p.{page})" if page else ""

                    conf_color = "#10B981" if conf > 0.8 else "#F59E0B" if conf > 0.5 else "#EF4444"
                    display_val = corrected if corrected else val
                    correction_badge = ' <span style="color:#818CF8; font-size:0.65rem;">[Corrected]</span>' if corrected else ""

                    st.markdown(f"""
<div style="padding:0.35rem 0; border-bottom:1px solid #1E293B;">
  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
    <div>
      <span style="color:#94A3B8; font-size:0.7rem; text-transform:uppercase;">{fname}{page_ref}</span>
      {correction_badge}<br>
      <span style="color:#E2E8F0; font-size:0.82rem;">{display_val}</span>
      {f'<br><span style="text-decoration:line-through; color:#475569; font-size:0.75rem;">{val}</span>' if corrected else ''}
    </div>
    <div style="text-align:right;">
      <span style="color:{conf_color}; font-size:0.7rem;">{conf:.0%}</span><br>
      <span style="color:#475569; font-size:0.65rem;">{method}</span>
    </div>
  </div>
</div>""", unsafe_allow_html=True)
            else:
                st.info("No extracted fields available.")

        with inner_tabs[1]:
            findings = get_validation_findings(doc_id)
            if findings:
                for f in findings:
                    sev = f.get("severity", "Info")
                    color = _severity_color(sev)
                    passed = f.get("passed", False)
                    icon = "✅" if passed else ("🔴" if sev in ("Critical", "High") else "⚠️" if sev == "Medium" else "ℹ️")
                    st.markdown(f"""
<div style="border-left:3px solid {color}; padding:0.5rem 0.75rem; margin:0.3rem 0; background:#0F172A; border-radius:0 4px 4px 0;">
  <div style="display:flex; justify-content:space-between;">
    <span style="color:{color}; font-size:0.7rem; font-weight:600;">{icon} {sev} — {f.get('rule_id','')}</span>
    <span style="color:#475569; font-size:0.65rem;">{f.get('field') or ''}</span>
  </div>
  <div style="color:#CBD5E1; font-size:0.8rem; margin:0.2rem 0;">{f.get('message','')}</div>
  {f'<div style="color:#64748B; font-size:0.72rem;">💡 {f["suggestion"]}</div>' if f.get("suggestion") else ''}
</div>""", unsafe_allow_html=True)
            else:
                st.info("No validation findings.")

        with inner_tabs[2]:
            events = get_agent_events(doc_id)
            if events:
                for ev in events:
                    s = ev.get("status", "")
                    icon = "✅" if s == "success" else "❌" if s == "failed" else "⏭️"
                    dur = ev.get("duration_ms", 0)
                    dur_str = f"{dur}ms" if dur < 1000 else f"{dur/1000:.1f}s"
                    st.markdown(f"""
<div style="display:flex; justify-content:space-between; padding:0.4rem 0; border-bottom:1px solid #1E293B;">
  <div>
    <span style="color:#38BDF8; font-size:0.78rem; font-weight:600;">{icon} {ev.get('agent_name','')}</span>
    <div style="color:#94A3B8; font-size:0.72rem;">{ev.get('summary','')[:80]}</div>
  </div>
  <div style="color:#475569; font-size:0.7rem; text-align:right;">{dur_str}</div>
</div>""", unsafe_allow_html=True)
            else:
                st.info("No agent trace available.")

        with inner_tabs[3]:
            fields_data = get_extracted_fields(doc_id)
            findings_data = get_validation_findings(doc_id)
            reviews_data = get_review_decisions(doc_id)

            col_j, col_c, col_x = st.columns(3)
            with col_j:
                json_bytes = export_json(doc, fields_data, findings_data, reviews_data, {})
                st.download_button("⬇ JSON", json_bytes, f"{doc_id}_export.json", "application/json", key=f"dl_json_{doc_id}")
            with col_c:
                csv_bytes = export_csv(doc, fields_data, findings_data, reviews_data, {})
                st.download_button("⬇ CSV", csv_bytes, f"{doc_id}_export.csv", "text/csv", key=f"dl_csv_{doc_id}")
            with col_x:
                xlsx_bytes = export_excel(doc, fields_data, findings_data, reviews_data, {})
                if xlsx_bytes:
                    st.download_button("⬇ Excel", xlsx_bytes, f"{doc_id}_export.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key=f"dl_xlsx_{doc_id}")
                else:
                    st.info("Excel unavailable")

            summary = generate_summary_report(doc, fields_data, findings_data)
            with st.expander("📄 Processing Summary"):
                st.text(summary)
