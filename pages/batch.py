"""Batch Processing page"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import time


def render():
    st.markdown("## 📦 Batch Processing")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("### Batch Document Upload")
        uploaded = st.file_uploader(
            "Upload multiple documents for batch processing",
            type=["pdf", "png", "jpg", "jpeg", "tiff"],
            accept_multiple_files=True,
            key="batch_uploader",
        )
        is_demo = st.checkbox("Mark as demo data", key="batch_demo")
        run_btn = st.button("▶ Run Batch Processing", key="batch_run_btn", disabled=not uploaded)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("### Batch Settings")
        st.markdown("**Continue on failure:** Yes")
        st.markdown("**Isolation:** Each document processed independently")
        st.markdown("**Export:** Batch CSV available after processing")
        st.markdown('</div>', unsafe_allow_html=True)

    if uploaded and run_btn:
        _run_batch(uploaded, is_demo)

    # Batch history
    st.markdown("---")
    st.markdown("### Recent Batch Results")
    _show_batch_history()


def _run_batch(uploaded_files, is_demo: bool):
    from agents.orchestrator_agent import run_pipeline
    from agents.structured_output_agent import export_batch_csv

    results = []
    start_time = time.time()

    progress = st.progress(0.0, text="Batch processing starting…")
    result_placeholder = st.empty()

    for idx, uf in enumerate(uploaded_files):
        file_bytes = uf.read()
        file_start = time.time()

        try:
            def _cb(msg, frac, _idx=idx):
                overall = (_idx + frac) / len(uploaded_files)
                progress.progress(overall, text=f"[{idx+1}/{len(uploaded_files)}] {uf.name}: {msg}")

            result = run_pipeline(uf.name, file_bytes, is_demo=is_demo, progress_callback=_cb)
            elapsed = time.time() - file_start
            results.append({
                "filename": uf.name,
                "status": result.get("status", "Failed") if result.get("success") else "Failed",
                "doc_type": result.get("doc_type", "Unknown"),
                "risk_score": result.get("risk_score", 0),
                "risk_label": result.get("risk_label", "—"),
                "doc_id": result.get("doc_id", "—"),
                "elapsed_s": round(elapsed, 2),
                "error": result.get("error") if not result.get("success") else None,
                "success": result.get("success", False),
            })
        except Exception as exc:
            results.append({
                "filename": uf.name, "status": "Failed", "success": False,
                "doc_type": "—", "risk_score": 0, "risk_label": "—",
                "doc_id": "—", "elapsed_s": 0, "error": str(exc),
            })

    progress.progress(1.0, text="Batch complete!")
    total_elapsed = time.time() - start_time

    # Show summary
    success_count = sum(1 for r in results if r["success"])
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a: st.metric("Total", len(results))
    with col_b: st.metric("Successful", success_count)
    with col_c: st.metric("Failed", len(results) - success_count)
    with col_d: st.metric("Total Time", f"{total_elapsed:.1f}s")

    # Results table
    df_data = []
    for r in results:
        status_icon = "✅" if r["success"] else "❌"
        df_data.append({
            "File": r["filename"][:40],
            "Status": f"{status_icon} {r['status']}",
            "Type": r["doc_type"],
            "Risk": r["risk_score"],
            "Time (s)": r["elapsed_s"],
            "Doc ID": r["doc_id"],
        })

    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=1, format="%.0%"),
                 })

    # Download batch CSV
    from core.database import get_all_documents
    all_docs = get_all_documents(50)
    recent_ids = {r["doc_id"] for r in results}
    recent_docs = [d for d in all_docs if d.get("doc_id") in recent_ids]
    if recent_docs:
        csv_bytes = export_batch_csv(recent_docs)
        st.download_button("⬇ Download Batch CSV", csv_bytes, "batch_export.csv", "text/csv", key="batch_dl_csv")

    # Show errors
    errors = [r for r in results if not r["success"]]
    if errors:
        with st.expander(f"⚠️ {len(errors)} document(s) failed"):
            for r in errors:
                st.error(f"**{r['filename']}**: {r.get('error', 'Unknown error')}")


def _show_batch_history():
    from core.database import get_all_documents
    docs = get_all_documents(50)
    if not docs:
        st.info("No documents processed yet.")
        return

    # Show document-type breakdown
    type_counts = {}
    status_counts = {}
    for d in docs:
        t = d.get("doc_type") or "Unknown"
        s = d.get("status", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        status_counts[s] = status_counts.get(s, 0) + 1

    col_t, col_s = st.columns(2)
    with col_t:
        st.markdown("**By Type:**")
        for t, cnt in type_counts.items():
            st.markdown(f"- {t}: **{cnt}**")
    with col_s:
        st.markdown("**By Status:**")
        for s, cnt in status_counts.items():
            color = {"Ready": "#10B981", "Needs Review": "#F59E0B", "High Risk": "#EF4444"}.get(s, "#94A3B8")
            st.markdown(f'- <span style="color:{color}">{s}</span>: **{cnt}**', unsafe_allow_html=True)

    from agents.structured_output_agent import export_batch_csv
    csv_bytes = export_batch_csv(docs)
    st.download_button("⬇ Download All Documents CSV", csv_bytes, "all_documents.csv", "text/csv", key="all_docs_csv")
