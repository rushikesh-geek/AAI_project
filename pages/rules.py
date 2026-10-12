"""Business Rules page"""
from __future__ import annotations

import json
import uuid
import streamlit as st
import pandas as pd


def render():
    st.markdown("## ⚙️ Business Rules")
    st.markdown("Configure validation and processing rules applied to all documents.")

    tab_rules, tab_vendors, tab_new = st.tabs(["📋 Active Rules", "🏢 Reference Entities", "➕ Create Rule"])

    with tab_rules:
        _show_rules()

    with tab_vendors:
        _show_vendors()

    with tab_new:
        _create_rule_form()


def _show_rules():
    from core.database import get_business_rules, toggle_business_rule, delete_business_rule

    rules = get_business_rules(active_only=False)

    if not rules:
        st.info("No rules configured. Use the 'Create Rule' tab to add rules.")
        return

    for rule in rules:
        severity_color = {"Critical": "#EF4444", "High": "#F97316", "Medium": "#F59E0B",
                          "Low": "#3B82F6"}.get(rule.get("severity", ""), "#94A3B8")
        active = rule.get("active", 1)
        status_text = "🟢 Active" if active else "⚫ Disabled"

        with st.expander(f"{'🟢' if active else '⚫'} [{rule.get('rule_type','')}] {rule.get('name','')}", expanded=False):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"""
<div style="font-size:0.8rem; color:#94A3B8;">
  <b style="color:#CBD5E1;">{rule.get('name','')}</b><br>
  <span style="color:#64748B;">{rule.get('description','')}</span><br>
  <span style="color:{severity_color};">Severity: {rule.get('severity','')}</span><br>
  <span style="color:#475569; font-size:0.72rem;">Params: {json.dumps(rule.get('parameters',{}))}</span>
</div>""", unsafe_allow_html=True)

            with col2:
                toggle_label = "Disable" if active else "Enable"
                if st.button(toggle_label, key=f"toggle_{rule['rule_id']}"):
                    toggle_business_rule(rule["rule_id"], not active)
                    st.rerun()

            with col3:
                if st.button("🗑 Delete", key=f"delete_{rule['rule_id']}"):
                    delete_business_rule(rule["rule_id"])
                    st.rerun()


def _show_vendors():
    from core.database import get_reference_entities, add_reference_entity, delete_reference_entity

    col_list, col_add = st.columns([2, 1])

    with col_list:
        st.markdown("#### Registered Vendors")
        vendors = get_reference_entities("vendor")
        if vendors:
            for v in vendors:
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.markdown(f'<div style="padding:0.3rem 0; color:#CBD5E1; font-size:0.83rem;">🏢 {v["name"]}</div>', unsafe_allow_html=True)
                with col_b:
                    if st.button("✕", key=f"del_vendor_{v['id']}"):
                        delete_reference_entity(v["id"])
                        st.rerun()
        else:
            st.info("No vendors registered.")

    with col_add:
        st.markdown("#### Add Vendor")
        new_vendor = st.text_input("Vendor name", key="new_vendor_name")
        if st.button("➕ Add Vendor", key="add_vendor_btn") and new_vendor.strip():
            add_reference_entity("vendor", new_vendor.strip())
            st.success(f"Added: {new_vendor}")
            st.rerun()

    st.markdown("---")
    col_c, col_d = st.columns([2, 1])
    with col_c:
        st.markdown("#### Registered Customers")
        customers = get_reference_entities("customer")
        if customers:
            for c in customers:
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.markdown(f'<div style="padding:0.3rem 0; color:#CBD5E1; font-size:0.83rem;">👤 {c["name"]}</div>', unsafe_allow_html=True)
                with col_b:
                    if st.button("✕", key=f"del_cust_{c['id']}"):
                        delete_reference_entity(c["id"])
                        st.rerun()
        else:
            st.info("No customers registered.")

    with col_d:
        st.markdown("#### Add Customer")
        new_cust = st.text_input("Customer name", key="new_cust_name")
        if st.button("➕ Add Customer", key="add_cust_btn") and new_cust.strip():
            add_reference_entity("customer", new_cust.strip())
            st.success(f"Added: {new_cust}")
            st.rerun()


def _create_rule_form():
    st.markdown("#### Create New Business Rule")

    from core.database import upsert_business_rule

    with st.form("new_rule_form"):
        rule_name = st.text_input("Rule Name *", placeholder="e.g. Flag High Value Invoices")
        rule_type = st.selectbox("Rule Type", ["threshold", "required_field", "vendor_check", "due_date"])
        description = st.text_area("Description", placeholder="What this rule checks…", height=60)
        severity = st.selectbox("Severity", ["Critical", "High", "Medium", "Low"])

        st.markdown("**Parameters** (JSON format):")
        param_help = {
            "threshold": '{"field": "stated_total", "operator": "gt", "value": 50000}',
            "required_field": '{"field": "po_number"}',
            "vendor_check": '{"match_threshold": 80}',
            "due_date": '{"days": 7}',
        }
        params_text = st.text_area(
            "Parameters JSON",
            value=param_help.get(rule_type, "{}"),
            height=80,
        )

        submitted = st.form_submit_button("➕ Create Rule")
        if submitted:
            if not rule_name.strip():
                st.error("Rule name is required.")
            else:
                try:
                    params = json.loads(params_text)
                    rule_id = f"CUSTOM_{uuid.uuid4().hex[:8].upper()}"
                    upsert_business_rule({
                        "rule_id": rule_id,
                        "rule_type": rule_type,
                        "name": rule_name.strip(),
                        "description": description.strip(),
                        "parameters": params,
                        "severity": severity,
                        "active": 1,
                    })
                    st.success(f"✅ Rule '{rule_name}' created (ID: {rule_id})")
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON parameters: {e}")
