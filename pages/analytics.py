"""Analytics page"""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta


def render():
    st.markdown("## 📊 Analytics")
    st.markdown("Processing statistics and trends calculated from actual persisted data.")

    from core.database import get_all_documents, get_validation_findings, get_agent_events, get_all_review_decisions

    docs = get_all_documents(500)
    if not docs:
        st.info("No data available. Process some documents to see analytics.")
        return

    # ── Top metrics ────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    total = len(docs)
    avg_risk = sum(d.get("risk_score", 0) for d in docs) / max(total, 1)
    ready_rate = sum(1 for d in docs if d.get("status") == "Ready") / max(total, 1)
    review_docs = sum(1 for d in docs if d.get("status") in ("Needs Review", "High Risk"))

    with col1: st.metric("Total Documents", total)
    with col2: st.metric("Avg Risk Score", f"{avg_risk:.1%}")
    with col3: st.metric("Auto-Ready Rate", f"{ready_rate:.1%}")
    with col4: st.metric("Review Backlog", review_docs)

    st.markdown("")

    # ── Charts Row 1 ──────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Risk Score Distribution")
        risk_scores = [d.get("risk_score", 0) for d in docs]
        fig = go.Figure(go.Histogram(
            x=risk_scores, nbinsx=20,
            marker_color="#38BDF8", opacity=0.8,
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#94A3B8", height=230,
            xaxis=dict(title="Risk Score", gridcolor="#1E293B", color="#64748B"),
            yaxis=dict(title="Count", gridcolor="#1E293B", color="#64748B"),
            margin=dict(t=10, b=10, l=10, r=10),
        )
        # Threshold lines
        fig.add_vline(x=0.35, line_dash="dash", line_color="#F59E0B",
                      annotation_text="Med", annotation_font_color="#F59E0B")
        fig.add_vline(x=0.70, line_dash="dash", line_color="#EF4444",
                      annotation_text="High", annotation_font_color="#EF4444")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Issue Severity Breakdown")

        all_findings = []
        doc_ids = [d["doc_id"] for d in docs[:50]]  # sample for performance
        from core.database import _get_conn
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT severity, COUNT(*) as cnt FROM validation_findings GROUP BY severity"
            ).fetchall()
        sev_data = {r[0]: r[1] for r in rows}

        if sev_data:
            sev_colors = {"Critical": "#EF4444", "High": "#F97316", "Medium": "#F59E0B",
                          "Low": "#3B82F6", "Info": "#22D3EE"}
            fig2 = go.Figure(go.Bar(
                x=list(sev_data.keys()),
                y=list(sev_data.values()),
                marker_color=[sev_colors.get(k, "#94A3B8") for k in sev_data.keys()],
                text=list(sev_data.values()),
                textposition="outside",
                textfont_color="#CBD5E1",
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94A3B8", height=230,
                xaxis=dict(gridcolor="#1E293B", color="#64748B"),
                yaxis=dict(gridcolor="#1E293B", color="#64748B"),
                margin=dict(t=10, b=10, l=10, r=10), showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No findings yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Charts Row 2 ──────────────────────────────────────────────────────
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Document Type Breakdown")
        type_counts = {}
        for d in docs:
            t = d.get("doc_type") or "Unknown"
            type_counts[t] = type_counts.get(t, 0) + 1

        if type_counts:
            fig3 = go.Figure(go.Bar(
                x=list(type_counts.values()),
                y=list(type_counts.keys()),
                orientation="h",
                marker_color=["#38BDF8", "#818CF8", "#34D399", "#F472B6", "#FB923C"][:len(type_counts)],
                text=list(type_counts.values()),
                textposition="auto",
            ))
            fig3.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94A3B8", height=230,
                xaxis=dict(gridcolor="#1E293B", color="#64748B"),
                yaxis=dict(color="#CBD5E1"),
                margin=dict(t=10, b=10, l=10, r=10), showlegend=False,
            )
            st.plotly_chart(fig3, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_d:
        st.markdown('<div class="dm-card">', unsafe_allow_html=True)
        st.markdown("#### Agent Performance")

        from core.database import _get_conn
        with _get_conn() as conn:
            agent_rows = conn.execute("""
                SELECT agent_name,
                       COUNT(*) as total,
                       SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes,
                       AVG(duration_ms) as avg_ms
                FROM agent_events GROUP BY agent_name
            """).fetchall()

        if agent_rows:
            agents_df = pd.DataFrame([dict(r) for r in agent_rows])
            agents_df["success_rate"] = agents_df["successes"] / agents_df["total"]
            agents_df["agent_short"] = agents_df["agent_name"].str.replace("Agent", "")
            agents_df["avg_ms"] = agents_df["avg_ms"].fillna(0).astype(int)

            fig4 = go.Figure()
            fig4.add_trace(go.Bar(
                name="Success Rate",
                x=agents_df["agent_short"],
                y=agents_df["success_rate"],
                marker_color="#10B981",
                yaxis="y",
            ))
            fig4.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94A3B8", height=230,
                xaxis=dict(gridcolor="#1E293B", color="#64748B", tickangle=-30),
                yaxis=dict(gridcolor="#1E293B", color="#64748B", range=[0, 1], title="Success Rate"),
                margin=dict(t=10, b=40, l=10, r=10), showlegend=False,
            )
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("No agent data yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Document table ─────────────────────────────────────────────────────
    st.markdown('<div class="dm-card">', unsafe_allow_html=True)
    st.markdown("#### All Documents — Raw Data")
    df_docs = pd.DataFrame([{
        "Doc ID": d.get("doc_id"),
        "Filename": d.get("filename", "")[:35],
        "Type": d.get("doc_type") or "—",
        "Status": d.get("status"),
        "Risk": d.get("risk_score", 0),
        "Mode": d.get("processing_mode", "local"),
        "Demo": "✓" if d.get("is_demo") else "",
        "Created": d.get("created_at", "")[:16],
    } for d in docs])
    st.dataframe(df_docs, use_container_width=True, hide_index=True,
                 column_config={
                     "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=1, format="%.0%"),
                 })
    st.markdown('</div>', unsafe_allow_html=True)
