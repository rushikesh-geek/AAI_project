"""Overview Dashboard page"""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime


def render():
    st.markdown("## 🏠 Overview Dashboard")
    st.markdown('<div class="section-title">Platform Performance at a Glance</div>', unsafe_allow_html=True)

    from core.database import get_dashboard_metrics, get_all_documents, get_audit_events
    m = get_dashboard_metrics()
    docs = get_all_documents(limit=200)

    # ── KPI Row ────────────────────────────────────────────────────────────
    cols = st.columns(5)
    kpis = [
        ("Total Processed", m["total"], "📄", "#38BDF8"),
        ("Ready", m["ready"], "✅", "#10B981"),
        ("Needs Review", m["needs_review"], "⚠️", "#F59E0B"),
        ("High Risk", m["high_risk"], "🔴", "#EF4444"),
        ("Failed", m["failed"], "❌", "#64748B"),
    ]
    for col, (label, value, icon, color) in zip(cols, kpis):
        with col:
            st.markdown(f"""
<div class="dm-metric">
  <div class="value" style="color:{color}">{icon} {value}</div>
  <div class="label">{label}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── Row 2: Charts ──────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Document Type Distribution")
        if m["type_distribution"]:
            fig = go.Figure(data=[go.Pie(
                labels=list(m["type_distribution"].keys()),
                values=list(m["type_distribution"].values()),
                hole=0.55,
                marker_colors=["#38BDF8", "#818CF8", "#34D399", "#F472B6", "#FB923C"],
                textfont_size=11,
            )])
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#CBD5E1",
                legend=dict(font_color="#94A3B8", bgcolor="rgba(0,0,0,0)"),
                margin=dict(t=10, b=10, l=10, r=10),
                height=220,
                showlegend=True,
            )
            fig.add_annotation(
                text=f"<b>{m['total']}</b><br><span style='font-size:9px'>Docs</span>",
                x=0.5, y=0.5, font_size=14, showarrow=False, font_color="#CBD5E1"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No documents processed yet. Upload documents to begin.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Processing Status")
        statuses = ["Ready", "Needs Review", "High Risk", "Failed", "Processing"]
        colors = ["#10B981", "#F59E0B", "#EF4444", "#64748B", "#3B82F6"]
        counts = [
            m["ready"], m["needs_review"], m["high_risk"],
            m["failed"], max(0, m["total"] - m["ready"] - m["needs_review"] - m["high_risk"] - m["failed"])
        ]
        fig2 = go.Figure(go.Bar(
            x=statuses, y=counts,
            marker_color=colors,
            text=counts,
            textposition="outside",
            textfont_color="#CBD5E1",
        ))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#94A3B8", xaxis_color="#334155", yaxis_color="#334155",
            xaxis=dict(gridcolor="#1E293B"), yaxis=dict(gridcolor="#1E293B"),
            margin=dict(t=20, b=10, l=10, r=10), height=220, showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### System Health")
        metrics2 = [
            ("Avg Risk Score", f"{m['avg_risk']:.1%}", "#F59E0B"),
            ("Critical Findings", str(m["critical_findings"]), "#EF4444"),
            ("Agent Failure Rate", f"{m['agent_failure_rate']:.1f}%", "#FB923C"),
            ("Review Backlog", str(m["review_backlog"]), "#FCD34D"),
        ]
        for label, value, color in metrics2:
            st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center; 
     padding:0.5rem 0; border-bottom:1px solid #1E293B;">
  <span style="color:#94A3B8; font-size:0.8rem;">{label}</span>
  <span style="color:{color}; font-weight:600; font-size:0.9rem;">{value}</span>
</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Row 3: Recent Activity ─────────────────────────────────────────────
    st.markdown("")
    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Recent Documents")
        if docs:
            recent = docs[:8]
            rows = []
            for d in recent:
                status = d.get("status", "")
                badge_class = {
                    "Ready": "badge-ready", "Needs Review": "badge-review",
                    "High Risk": "badge-risk", "Failed": "badge-failed",
                }.get(status, "badge-processing")
                rows.append({
                    "Document": d.get("filename", "")[:35],
                    "Type": d.get("doc_type") or "—",
                    "Status": status,
                    "Risk": f"{d.get('risk_score', 0):.0%}",
                    "Processed": d.get("created_at", "")[:16],
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config={
                             "Risk": st.column_config.ProgressColumn(
                                 "Risk", min_value=0, max_value=1, format="%.0%",
                             )
                         })
        else:
            st.markdown("""
<div style="text-align:center; padding:2rem; color:#64748B;">
  <div style="font-size:2.5rem; margin-bottom:0.5rem;">📭</div>
  <div>No documents yet. Upload documents in the Workspace.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Recent Audit Events")
        events = get_audit_events(limit=6)
        if events:
            for ev in events:
                ts = ev.get("created_at", "")[:16]
                etype = ev.get("event_type", "")
                action = ev.get("action", "")[:40]
                color = {"REVIEW": "#818CF8", "PIPELINE": "#38BDF8", "AGENT": "#34D399"}.get(etype, "#94A3B8")
                st.markdown(f"""
<div style="padding:0.4rem 0; border-bottom:1px solid #1E293B;">
  <div style="color:{color}; font-size:0.7rem; font-weight:600;">{etype}</div>
  <div style="color:#CBD5E1; font-size:0.77rem;">{action}</div>
  <div style="color:#475569; font-size:0.65rem;">{ts}</div>
</div>""", unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#64748B; text-align:center; padding:1rem;">No events yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Demo CTA ───────────────────────────────────────────────────────────
    if m["total"] == 0:
        st.markdown("")
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("### 🚀 Quick Start — Run Demo Workflow")
        st.markdown("""
Process three synthetic sample documents (Invoice, KYC, Contract) through the full 10-agent pipeline.
All demo documents are clearly labelled synthetic data — not real business records.
        """)
        if st.button("▶ Run Demo Workflow Now", key="overview_demo_btn"):
            _run_demo()
        st.markdown('</div>', unsafe_allow_html=True)


def _run_demo():
    """Run the demo workflow from the overview page."""
    from core.config import DEMO_DIR
    from assets.demo.demo_generator import create_demo_documents
    from agents.orchestrator_agent import run_pipeline

    demo_files = create_demo_documents(DEMO_DIR)
    progress_bar = st.progress(0.0, text="Starting demo workflow…")

    results = []
    for i, (name, path) in enumerate(demo_files.items()):
        if path.exists():
            file_bytes = path.read_bytes()
            def _cb(msg, frac, _i=i, _name=name):
                total_frac = (_i + frac) / len(demo_files)
                progress_bar.progress(total_frac, text=f"[{_name}] {msg}")

            result = run_pipeline(path.name, file_bytes, is_demo=True, progress_callback=_cb)
            results.append((name, result))

    progress_bar.progress(1.0, text="Demo complete!")

    success = sum(1 for _, r in results if r.get("success"))
    st.success(f"✅ Demo complete — {success}/{len(results)} documents processed successfully!")

    for name, r in results:
        doc_id = r.get("doc_id", "")
        doc_type = r.get("doc_type", "")
        status = r.get("status", "")
        risk = r.get("risk_score", 0)
        st.markdown(f"**{name}** → {doc_type} | Status: `{status}` | Risk: `{risk:.1%}`")

    st.info("📄 View results in the Document Workspace and Human Review Center.")
    st.rerun()
