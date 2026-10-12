"""Audit Trail page"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render():
    st.markdown("## 📜 Audit Trail")
    st.markdown("Complete, tamper-evident record of all processing and review events.")

    from core.database import get_audit_events, get_all_documents

    col_filter, col_doc = st.columns([1, 2])
    with col_filter:
        event_types = ["All", "PIPELINE", "AGENT", "REVIEW", "RULE", "SYSTEM"]
        filter_type = st.selectbox("Event Type", event_types, key="audit_filter_type")
    with col_doc:
        docs = get_all_documents(200)
        doc_options = {"All Documents": None}
        doc_options.update({f"{d['doc_id']} — {d['filename'][:35]}": d["doc_id"] for d in docs})
        selected_doc = st.selectbox("Filter by Document", list(doc_options.keys()), key="audit_filter_doc")
        doc_id = doc_options[selected_doc]

    events = get_audit_events(doc_id=doc_id, limit=500)
    if filter_type != "All":
        events = [e for e in events if e.get("event_type") == filter_type]

    if not events:
        st.markdown("""
<div style="text-align:center; padding:3rem; color:#64748B;">
  <div style="font-size:3rem;">📜</div>
  <div>No audit events found matching the selected filters.</div>
</div>""", unsafe_allow_html=True)
        return

    # Summary
    event_counts = {}
    for e in events:
        t = e.get("event_type", "Other")
        event_counts[t] = event_counts.get(t, 0) + 1

    cols = st.columns(len(event_counts) + 1)
    cols[0].metric("Total Events", len(events))
    for col, (t, cnt) in zip(cols[1:], event_counts.items()):
        color = {"PIPELINE": "#38BDF8", "AGENT": "#34D399", "REVIEW": "#818CF8"}.get(t, "#94A3B8")
        col.markdown(f'<div class="dm-metric"><div class="value" style="color:{color};">{cnt}</div><div class="label">{t}</div></div>', unsafe_allow_html=True)

    st.markdown("")

    # Timeline
    type_colors = {
        "PIPELINE": "#38BDF8", "AGENT": "#34D399", "REVIEW": "#818CF8",
        "RULE": "#F59E0B", "SYSTEM": "#64748B"
    }

    for ev in events[:100]:
        ev_type = ev.get("event_type", "OTHER")
        color = type_colors.get(ev_type, "#94A3B8")
        action = ev.get("action", "")
        doc = ev.get("doc_id", "—")
        ts = ev.get("created_at", "")[:19].replace("T", " ")
        actor = ev.get("actor", "system")
        details = ev.get("details") or ""
        prev_val = ev.get("previous_value")
        new_val = ev.get("new_value")

        diff_html = ""
        if prev_val and new_val:
            diff_html = f"""
<div style="font-size:0.72rem; margin-top:0.3rem;">
  <span style="color:#EF4444; text-decoration:line-through;">{prev_val[:50]}</span>
  <span style="color:#94A3B8;"> → </span>
  <span style="color:#10B981;">{new_val[:50]}</span>
</div>"""

        st.markdown(f"""
<div style="display:flex; gap:1rem; padding:0.6rem 0; border-bottom:1px solid #1E293B;">
  <div style="min-width:140px; color:#475569; font-size:0.7rem; padding-top:0.1rem;">{ts}</div>
  <div style="flex:1;">
    <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.1rem;">
      <span style="background:{color}22; color:{color}; padding:1px 6px; border-radius:4px; font-size:0.65rem; font-weight:600;">{ev_type}</span>
      <span style="color:#CBD5E1; font-size:0.8rem;">{action}</span>
    </div>
    {f'<div style="color:#94A3B8; font-size:0.72rem;">{details[:100]}</div>' if details else ''}
    {diff_html}
  </div>
  <div style="min-width:100px; text-align:right;">
    <div style="color:#64748B; font-size:0.68rem;">Doc: {doc}</div>
    <div style="color:#475569; font-size:0.65rem;">{actor}</div>
  </div>
</div>""", unsafe_allow_html=True)

    if len(events) > 100:
        st.info(f"Showing 100 of {len(events)} events. Use filters to narrow down.")

    # Export
    rows = [{
        "Timestamp": e.get("created_at", "")[:19],
        "Type": e.get("event_type", ""),
        "Action": e.get("action", ""),
        "Doc ID": e.get("doc_id", ""),
        "Agent": e.get("agent", ""),
        "Actor": e.get("actor", ""),
        "Details": (e.get("details") or "")[:100],
    } for e in events]
    df = pd.DataFrame(rows)
    csv = df.to_csv(index=False).encode()
    st.download_button("⬇ Export Audit Log (CSV)", csv, "audit_trail.csv", "text/csv", key="audit_dl")
