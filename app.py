"""
DocuMind AI — Main Streamlit Application Entry Point
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Page configuration — MUST be first Streamlit call
st.set_page_config(
    page_title="DocuMind AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.database import init_db
from core.logging_config import setup_logging

setup_logging()
init_db()

# ── Custom CSS ─────────────────────────────────────────────────────────────

def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { font-family: 'Inter', sans-serif; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
    border-right: 1px solid #334155;
}
[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
[data-testid="stSidebar"] .stRadio label:hover { color: #38BDF8 !important; }

/* Main area */
.stApp { background: #0F172A; color: #E2E8F0; }

/* Cards */
.dm-card {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}
.dm-card-sm {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 0.75rem 1rem;
}

/* Metric tiles */
.dm-metric {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
}
.dm-metric .value { font-size: 2.2rem; font-weight: 700; color: #38BDF8; }
.dm-metric .label { font-size: 0.75rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em; }
.dm-metric .delta { font-size: 0.8rem; color: #10B981; }

/* Status badges */
.badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.badge-ready { background: #064E3B; color: #34D399; }
.badge-review { background: #713F12; color: #FCD34D; }
.badge-risk { background: #7F1D1D; color: #FCA5A5; }
.badge-failed { background: #1E293B; color: #64748B; }
.badge-processing { background: #1E3A5F; color: #60A5FA; }

/* Risk score bar */
.risk-bar { height: 8px; border-radius: 4px; margin-top: 0.3rem; }
.risk-low { background: linear-gradient(90deg, #10B981, #34D399); }
.risk-med { background: linear-gradient(90deg, #F59E0B, #FCD34D); }
.risk-high { background: linear-gradient(90deg, #EF4444, #FCA5A5); }

/* Section headers */
.section-title {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #64748B;
    margin: 1.5rem 0 0.5rem 0;
}

/* Table styling */
.dataframe { border: 1px solid #334155 !important; }
.dataframe th { background: #1E293B !important; color: #94A3B8 !important; font-size: 0.72rem !important; }
.dataframe td { color: #CBD5E1 !important; font-size: 0.8rem !important; }

/* Finding severity */
.finding-critical { border-left: 3px solid #EF4444; padding-left: 0.75rem; margin: 0.4rem 0; }
.finding-high { border-left: 3px solid #F97316; padding-left: 0.75rem; margin: 0.4rem 0; }
.finding-medium { border-left: 3px solid #F59E0B; padding-left: 0.75rem; margin: 0.4rem 0; }
.finding-low { border-left: 3px solid #3B82F6; padding-left: 0.75rem; margin: 0.4rem 0; }
.finding-info { border-left: 3px solid #22D3EE; padding-left: 0.75rem; margin: 0.4rem 0; }

/* Streamlit overrides */
.stButton button {
    background: linear-gradient(135deg, #3B82F6 0%, #6366F1 100%);
    color: white !important;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s;
}
.stButton button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(99,102,241,0.4); }

.stDownloadButton button {
    background: #0F766E;
    color: white !important;
    border: none;
    border-radius: 8px;
}

div[data-testid="stExpander"] {
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
    background: #1E293B !important;
}

.stTabs [data-baseweb="tab"] { color: #94A3B8 !important; }
.stTabs [aria-selected="true"] { color: #38BDF8 !important; }

.stAlert { border-radius: 8px !important; }

/* Sidebar brand */
.sidebar-brand {
    padding: 1rem;
    border-bottom: 1px solid #334155;
    margin-bottom: 1rem;
}
.sidebar-brand h2 { font-size: 1.3rem; font-weight: 700; color: #38BDF8 !important; margin: 0; }
.sidebar-brand p { font-size: 0.72rem; color: #64748B !important; margin: 0.2rem 0 0 0; }
</style>
""", unsafe_allow_html=True)


inject_css()

# ── Navigation ──────────────────────────────────────────────────────────────

PAGES = {
    "🏠  Overview": "overview",
    "📄  Document Workspace": "workspace",
    "📦  Batch Processing": "batch",
    "👁️  Human Review Center": "review",
    "⚙️  Business Rules": "rules",
    "📋  Contract Intelligence": "contracts",
    "📜  Audit Trail": "audit",
    "📊  Analytics": "analytics",
    "🔧  Settings & Health": "settings",
}

with st.sidebar:
    st.markdown("""
<div class="sidebar-brand">
  <h2>🧠 DocuMind AI</h2>
  <p>Document Intelligence Platform</p>
</div>
""", unsafe_allow_html=True)

    selection = st.radio(
        "Navigate",
        list(PAGES.keys()),
        label_visibility="collapsed",
    )
    st.markdown("---")

    # Quick stats in sidebar
    try:
        from core.database import get_dashboard_metrics
        m = get_dashboard_metrics()
        st.markdown(f"""
<div style="padding:0.5rem;">
  <div style="color:#64748B; font-size:0.65rem; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.5rem;">Quick Stats</div>
  <div style="display:flex; justify-content:space-between; margin:0.25rem 0;">
    <span style="color:#94A3B8; font-size:0.78rem;">Total Docs</span>
    <span style="color:#38BDF8; font-weight:600; font-size:0.78rem;">{m['total']}</span>
  </div>
  <div style="display:flex; justify-content:space-between; margin:0.25rem 0;">
    <span style="color:#94A3B8; font-size:0.78rem;">Review Queue</span>
    <span style="color:#FCD34D; font-weight:600; font-size:0.78rem;">{m['review_backlog']}</span>
  </div>
  <div style="display:flex; justify-content:space-between; margin:0.25rem 0;">
    <span style="color:#94A3B8; font-size:0.78rem;">High Risk</span>
    <span style="color:#FCA5A5; font-weight:600; font-size:0.78rem;">{m['high_risk']}</span>
  </div>
</div>
""", unsafe_allow_html=True)
    except Exception:
        pass

# ── Route to page ───────────────────────────────────────────────────────────

page_key = PAGES[selection]

if page_key == "overview":
    from pages import overview; overview.render()
elif page_key == "workspace":
    from pages import workspace; workspace.render()
elif page_key == "batch":
    from pages import batch; batch.render()
elif page_key == "review":
    from pages import review; review.render()
elif page_key == "rules":
    from pages import rules; rules.render()
elif page_key == "contracts":
    from pages import contracts; contracts.render()
elif page_key == "audit":
    from pages import audit; audit.render()
elif page_key == "analytics":
    from pages import analytics; analytics.render()
elif page_key == "settings":
    from pages import settings; settings.render()
