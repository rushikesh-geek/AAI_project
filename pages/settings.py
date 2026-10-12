"""Settings & System Health page"""
from __future__ import annotations

import streamlit as st
import shutil
from pathlib import Path


def render():
    st.markdown("## 🔧 Settings & System Health")

    tab_health, tab_config, tab_data = st.tabs(["🩺 System Health", "⚙️ Configuration", "🗄️ Data Management"])

    with tab_health:
        _render_health()

    with tab_config:
        _render_config()

    with tab_data:
        _render_data()


def _check_icon(ok: bool) -> str:
    return "✅" if ok else "❌"


def _render_health():
    from core.config import (
        OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL,
        SUPPORTED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, DB_PATH, UPLOAD_DIR,
        llm_available, APP_VERSION
    )
    from agents.ocr_layout_agent import ocr_available, ocr_error_message

    st.markdown("### Dependency Status")

    checks = []

    # Python
    import sys
    py_ver = sys.version.split()[0]
    checks.append(("Python", True, f"v{py_ver}", ""))

    # Streamlit
    import streamlit
    checks.append(("Streamlit", True, f"v{streamlit.__version__}", ""))

    # PyMuPDF
    try:
        import fitz
        checks.append(("PyMuPDF", True, f"v{fitz.version[0]}", "PDF reading"))
    except ImportError:
        checks.append(("PyMuPDF", False, "Not installed", "pip install pymupdf"))

    # Pillow
    try:
        from PIL import Image
        import PIL
        checks.append(("Pillow", True, f"v{PIL.__version__}", "Image processing"))
    except ImportError:
        checks.append(("Pillow", False, "Not installed", "pip install pillow"))

    # OpenCV
    try:
        import cv2
        checks.append(("OpenCV", True, f"v{cv2.__version__}", "Image preprocessing"))
    except ImportError:
        checks.append(("OpenCV", False, "Not installed", "Optional — pip install opencv-python"))

    # pytesseract
    ocr_ok = ocr_available()
    ocr_msg = "" if ocr_ok else ocr_error_message()
    checks.append(("Tesseract OCR", ocr_ok, "Available" if ocr_ok else "Not found", ocr_msg))

    # Pydantic
    try:
        import pydantic
        checks.append(("Pydantic", True, f"v{pydantic.VERSION}", "Schema validation"))
    except ImportError:
        checks.append(("Pydantic", False, "Not installed", ""))

    # pandas
    try:
        import pandas as pd
        checks.append(("Pandas", True, f"v{pd.__version__}", "Data processing"))
    except ImportError:
        checks.append(("Pandas", False, "Not installed", ""))

    # plotly
    try:
        import plotly
        checks.append(("Plotly", True, f"v{plotly.__version__}", "Charts"))
    except ImportError:
        checks.append(("Plotly", False, "Not installed", ""))

    # rapidfuzz
    try:
        import rapidfuzz
        checks.append(("RapidFuzz", True, f"v{rapidfuzz.__version__}", "Fuzzy matching"))
    except ImportError:
        checks.append(("RapidFuzz", False, "Not installed", "pip install rapidfuzz"))

    # openpyxl
    try:
        import openpyxl
        checks.append(("openpyxl", True, f"v{openpyxl.__version__}", "Excel export"))
    except ImportError:
        checks.append(("openpyxl", False, "Not installed", "pip install openpyxl"))

    # SQLite DB
    db_exists = DB_PATH.exists()
    checks.append(("SQLite Database", db_exists, str(DB_PATH) if db_exists else "Not initialized", ""))

    for name, ok, version, note in checks:
        icon = _check_icon(ok)
        note_html = f'<span style="color:#64748B; font-size:0.7rem;"> — {note}</span>' if note else ""
        st.markdown(f"""
<div style="display:flex; justify-content:space-between; padding:0.4rem 0; border-bottom:1px solid #1E293B;">
  <div>
    <span style="color:{'#CBD5E1' if ok else '#EF4444'}; font-size:0.85rem;">{icon} {name}</span>
    {note_html}
  </div>
  <span style="color:#64748B; font-size:0.78rem;">{version}</span>
</div>""", unsafe_allow_html=True)

    # LLM status
    st.markdown("---")
    st.markdown("### LLM / API Status")
    llm_ok = llm_available()
    st.markdown(f"""
<div class="dm-card-sm">
  <div><b style="color:#CBD5E1;">OpenRouter Status:</b> {_check_icon(llm_ok)} {'Connected' if llm_ok else 'Not configured'}</div>
  <div style="color:#64748B; font-size:0.78rem; margin-top:0.3rem;">
    Model: {OPENROUTER_MODEL if llm_ok else '(not set)'}<br>
    Endpoint: {OPENROUTER_BASE_URL if llm_ok else '—'}<br>
    Key: {'✓ Configured (hidden)' if llm_ok else '✗ Not set — add OPENROUTER_API_KEY to .env'}
  </div>
</div>""", unsafe_allow_html=True)

    if llm_ok:
        if st.button("🔌 Test API Connectivity", key="test_api_btn"):
            from services.openrouter_client import verify_connectivity
            with st.spinner("Testing…"):
                ok, msg = verify_connectivity()
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")


def _render_config():
    from core.config import (
        MAX_UPLOAD_SIZE_MB, SUPPORTED_EXTENSIONS, UPLOAD_DIR, DB_PATH,
        ENABLE_LLM_CLASSIFICATION, ENABLE_LLM_EXTRACTION,
        LLM_TIMEOUT_SECONDS, LOW_RISK_THRESHOLD, HIGH_RISK_THRESHOLD,
        DEMO_MODE, APP_VERSION
    )

    st.markdown(f"""
<div class="dm-card">
  <h4 style="color:#38BDF8;">Application Configuration</h4>
  <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
    <tr><td style="color:#94A3B8; padding:0.3rem;">App Version</td><td style="color:#CBD5E1;">{APP_VERSION}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">Max Upload Size</td><td style="color:#CBD5E1;">{MAX_UPLOAD_SIZE_MB} MB</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">Supported Formats</td><td style="color:#CBD5E1;">{', '.join(SUPPORTED_EXTENSIONS)}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">Upload Directory</td><td style="color:#CBD5E1;">{UPLOAD_DIR}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">Database Path</td><td style="color:#CBD5E1;">{DB_PATH}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">LLM Classification</td><td style="color:#CBD5E1;">{'Enabled' if ENABLE_LLM_CLASSIFICATION else 'Disabled'}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">LLM Extraction</td><td style="color:#CBD5E1;">{'Enabled' if ENABLE_LLM_EXTRACTION else 'Disabled'}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">LLM Timeout</td><td style="color:#CBD5E1;">{LLM_TIMEOUT_SECONDS}s</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">Low Risk Threshold</td><td style="color:#CBD5E1;">{LOW_RISK_THRESHOLD:.0%}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">High Risk Threshold</td><td style="color:#CBD5E1;">{HIGH_RISK_THRESHOLD:.0%}</td></tr>
    <tr><td style="color:#94A3B8; padding:0.3rem;">Demo Mode</td><td style="color:#CBD5E1;">{'On' if DEMO_MODE else 'Off'}</td></tr>
  </table>
</div>""", unsafe_allow_html=True)

    st.info("To change configuration, edit the `.env` file and restart the application.")


def _render_data():
    from core.database import get_dashboard_metrics, clear_demo_data, DB_PATH, UPLOAD_DIR

    metrics = get_dashboard_metrics()
    st.markdown(f"""
<div class="dm-card">
  <h4>Database Statistics</h4>
  <div style="font-size:0.82rem; color:#94A3B8;">
    Total documents: <b style="color:#CBD5E1;">{metrics['total']}</b><br>
    Ready: <b style="color:#10B981;">{metrics['ready']}</b> | 
    Review: <b style="color:#F59E0B;">{metrics['needs_review']}</b> | 
    High Risk: <b style="color:#EF4444;">{metrics['high_risk']}</b>
  </div>
</div>""", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑 Clear All Demo Data", key="clear_demo_settings"):
            clear_demo_data()
            st.success("Demo data cleared.")
            st.rerun()

    with col_b:
        # Database size
        if DB_PATH.exists():
            size_mb = DB_PATH.stat().st_size / (1024 * 1024)
            st.metric("Database Size", f"{size_mb:.2f} MB")

    st.warning("⚠️ Data Management Note: Clearing demo data removes all synthetic records. "
               "Production data (is_demo=0) is not affected by the demo clear operation.")
