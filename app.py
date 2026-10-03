# app.py
import os
import sys
from pathlib import Path
import importlib

# Ensure application root directory is first in sys.path (critical for Streamlit Cloud)
APP_ROOT = str(Path(__file__).resolve().parent)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import re
import urllib.parse
from datetime import datetime
import pandas as pd
import streamlit as st


import json
import database
importlib.reload(database)
from database import (
    search_history_records, fetch_performance_data,
    init_estimator_schema, get_all_models_for_estimator,
    get_parts_by_model, update_part_price,
    get_missing_price_parts_df, get_cross_model_compatibilities
)

import etl
importlib.reload(etl)
from etl import (
    normalize_phone, ingest_performance_pipeline, ingest_feedback_and_pricing,
    parse_store_stock_pdf, sync_model_part_catalog_from_feedback
)

import config
from config import VISIT_CHARGES, MOBILITY_CHARGES, BASE_FIXED_TOTAL, calculate_gas_charge

st.set_page_config(
    page_title="DWP Field Assistant", 
    page_icon="❄️", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# Initialize database schema and auto-seed if required
init_estimator_schema()

# Custom Styling
st.markdown("""
<style>
    .main-title { font-size: 1.4rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.1rem; }
    .sub-title { font-size: 0.82rem; color: #64748B; margin-bottom: 0.8rem; }
    .bill-card { background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 12px; border-radius: 6px; margin: 10px 0; }
    .grand-total { font-size: 1.6rem; font-weight: 800; color: #0F172A; }
    .history-card { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .badge-warranty { background-color: #DCFCE7; color: #15803D; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-cash { background-color: #FEE2E2; color: #B91C1C; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-partial { background-color: #FEF3C7; color: #B45309; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-amount { background-color: #EFF6FF; color: #1D4ED8; padding: 3px 8px; border-radius: 12px; font-size: 0.78rem; font-weight: 700; border: 1px solid #BFDBFE; margin-right: 4px; }
    .scope-box { background-color: #F1F5F9; border: 1px solid #CBD5E1; padding: 8px 12px; border-radius: 6px; font-size: 0.82rem; color: #334155; margin-bottom: 12px; }
    .support-box { background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 12px; margin-top: 2rem; font-size: 0.82rem; color: #991B1B; text-align: center; }
    .credit-footer { font-size: 0.75rem; color: #64748B; text-align: center; margin-top: 1rem; border-top: 1px solid #E2E8F0; padding-top: 8px; }
    
    /* Stock Status Badges */
    .stock-badge-in { background-color: #DCFCE7; color: #15803D; font-weight: 700; padding: 2px 8px; border-radius: 12px; font-size: 0.73rem; border: 1px solid #86EFAC; display: inline-block; }
    .stock-badge-low { background-color: #FEF3C7; color: #B45309; font-weight: 700; padding: 2px 8px; border-radius: 12px; font-size: 0.73rem; border: 1px solid #FDE68A; display: inline-block; }
    .stock-badge-out { background-color: #FEE2E2; color: #B91C1C; font-weight: 700; padding: 2px 8px; border-radius: 12px; font-size: 0.73rem; border: 1px solid #FECACA; display: inline-block; }
    .item-card { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px; margin-bottom: 8px; }

    /* Multi-Tier Resolution Badges */
    .badge-tier-1 { background-color: #FEF3C7; color: #92400E; padding: 2px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 700; border: 1px solid #FCD34D; display: inline-block; margin-left: 4px; }
    .badge-tier-2 { background-color: #EFF6FF; color: #1D4ED8; padding: 2px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 600; border: 1px solid #BFDBFE; display: inline-block; margin-left: 4px; }
    .badge-tier-3 { background-color: #F0FDF4; color: #166534; padding: 2px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 600; border: 1px solid #BBF7D0; display: inline-block; margin-left: 4px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">❄️ DWP Service Field Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Field Diagnostic, Cost & Live Stock Estimator, History & KPI Hub</div>', unsafe_allow_html=True)



# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("---")
    st.markdown("### 📊 Module 3: Performance Sync")
    st.caption("Dono files upload karein aur button dabayein.")
    p_fb = st.file_uploader("Quality Feedback Report", type=["csv", "xlsx", "xls"], key="p_fb")
    p_can = st.file_uploader("Cancel / Nil / Transfer Report", type=["xlsx", "xls"], key="p_can")

    if st.button("📊 Update Technician Performance", use_container_width=True):
        if p_fb and p_can:
            with st.spinner("Processing Performance KPI..."):
                ingest_performance_pipeline(p_fb, p_can)
                st.success("Performance successfully updated!")
                st.rerun()
        else:
            st.error("Dono files lazmi upload karein!")

    st.markdown("---")
    st.markdown("### 🧮 Module 1 & 2: Archive Append")
    st.caption("Optional: Nayi closed complaints ko History mein add karne ke liye.")
    u_fb = st.file_uploader("Feedback File", type=["csv", "xlsx", "xls"], key="u_fb")
    u_coll = st.file_uploader("Collection Pricing File", type=["xlsx", "xls"], key="u_coll")

    if st.button("➕ Append to Master History", use_container_width=True):
        if u_fb:
            with st.spinner("Appending records..."):
                ingest_feedback_and_pricing(u_fb, u_coll)
                st.cache_data.clear()
                st.success("History updated safely without overwriting!")
    st.markdown("---")
    st.markdown("### 📋 Estimator & Pricing Tools")
    try:
        missing_df = get_missing_price_parts_df()
        if not missing_df.empty:
            csv_data = missing_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Download Missing Prices CSV ({len(missing_df)} SKUs)",
                data=csv_data,
                file_name="dwp_pending_erp_pricing_parts.csv",
                mime="text/csv",
                use_container_width=True
            )
    except Exception:
        pass

    with st.expander("📥 Daily Data Ingestion & Live Updates"):
        st.caption("Daily ERP stock movement PDF ya daily closed complaints add karein. 1-saal ka baseline data mehfooz rahy ga aur naye records judty rahengy.")
        
        st.markdown("###### ➕ Append Daily Closed Complaints")
        st.caption("Nayi closed complaints upload karein. Existing models/parts mein installation counts add hojayenge aur naye models catalog mein shamil hojayenge.")
        daily_fb = st.file_uploader("Daily Closed Complaints", type=["csv", "xlsx", "xls"], key="daily_fb")
        daily_coll = st.file_uploader("Daily Collection File (Optional)", type=["xlsx", "xls"], key="daily_coll")
        if st.button("➕ Merge Daily Complaints into Engine", use_container_width=True):
            if daily_fb:
                with st.spinner("Merging into Master History & Catalog..."):
                    ingest_feedback_and_pricing(daily_fb, daily_coll)
                    m_cnt, p_cnt, ev_cnt = sync_model_part_catalog_from_feedback(daily_fb, is_incremental=True)
                    st.cache_data.clear()
                    st.success(f"Successfully merged! {m_cnt} models, {p_cnt} parts updated.")
                    st.rerun()
            else:
                st.error("Closed complaints file upload karein!")

        st.markdown("---")
        st.markdown("###### 🔄 Update Daily ERP Stock & Prices")
        st.caption("Rozana ka naya Store Wise Stock Movement PDF upload karein taky Karachi-2 Store ki live availability aur retail prices update hojayen.")
        daily_pdf = st.file_uploader("Latest Stock Movement PDF", type=["pdf"], key="daily_pdf")
        if st.button("🔄 Sync Live Stock & Prices", use_container_width=True):
            if daily_pdf:
                with st.spinner("Updating Live Stock & Pricing..."):
                    cnt = parse_store_stock_pdf(daily_pdf)
                    st.success(f"Stock & prices updated for {cnt} items!")
                    st.rerun()
            else:
                st.error("Stock Movement PDF upload karein!")

tab_estimator, tab_history, tab_perf = st.tabs([
    "🧮 Spare Parts & Cost Estimator",
    "🔍 Unit & Customer History", 
    "📊 Technician Performance"
])

# ==========================================
# TAB 1: SPARE PARTS & COST ESTIMATOR
# ==========================================
with tab_estimator:
    st.markdown("##### 🧮 Spare Parts & Real-Time Job Cost Estimator")
    st.caption("Select appliance model to view verified compatible spare parts, Karachi-2 HA Store stock, and auto-calculated gas/labour rates.")

    # Initialize persistent selection state
    if "estimator_selected_parts" not in st.session_state:
        st.session_state["estimator_selected_parts"] = {}

    all_models = get_all_models_for_estimator()
    if not all_models:
        st.info("Catalog is initializing...")
        sync_model_part_catalog_from_feedback()
        parse_store_stock_pdf()
        all_models = get_all_models_for_estimator()

    col_m1, col_m2 = st.columns([3, 1])
    with col_m1:
        selected_model = st.selectbox(
            "🏷️ Select Equipment Model:",
            options=all_models,
            index=0 if all_models else None,
            help="Search across 500+ Gree and EcoStar models (e.g. GS-18PITH11W, GR-E8890G, WD-300F)"
        )
    
    # Reset parts selection and filters if model changes
    if selected_model:
        if st.session_state.get("estimator_active_model") != selected_model:
            st.session_state["estimator_selected_parts"] = {}
            st.session_state["estimator_active_model"] = selected_model
            if "p_board" in st.session_state:
                st.session_state["p_board"] = "-- All Categories --"
            if "p_search" in st.session_state:
                st.session_state["p_search"] = ""

        gas_amount, gas_label = calculate_gas_charge(selected_model)
        with col_m2:
            st.metric("Auto Gas Rate", f"Rs. {gas_amount:,}")
        st.markdown(f"""
        <div style="background-color: #F0FDF4; border: 1px solid #BBF7D0; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; color: #166534; margin-bottom: 12px;">
            ❄️ <b>Detected Category:</b> {gas_label} &nbsp;|&nbsp; <b>Base Gas Refill:</b> Rs. {gas_amount:,}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("##### 💵 Base Overheads & Billing Status")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            chk_visit = st.checkbox(f"🚗 Visit Charges (Rs. {VISIT_CHARGES:,})", value=True, key="chk_visit")
        with col_b2:
            chk_mobility = st.checkbox(f"🔧 Mobility / Labour (Rs. {MOBILITY_CHARGES:,})", value=True, key="chk_mobility")
        with col_b3:
            chk_gas = st.checkbox(f"⚡ Gas Refill Required (+Rs. {gas_amount:,})", value=False, key="chk_gas")

        billing_type = st.radio(
            "📋 Customer Warranty Status:",
            options=["Cash / Out of Warranty", "Under Warranty (Free Replacement)", "Partial Warranty (Parts Cash, Labour Free)"],
            horizontal=True,
            key="billing_type"
        )

        st.markdown("---")
        st.markdown("##### 🔩 Compatible Spare Parts Catalog")

        # Display Selected Parts Chip Container
        if st.session_state["estimator_selected_parts"]:
            st.markdown(f"""
            <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; color: #1D4ED8; font-size: 0.95rem;">
                        🛒 Currently Selected Parts ({len(st.session_state['estimator_selected_parts'])} items):
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            for pno, pinfo in list(st.session_state["estimator_selected_parts"].items()):
                c_p1, c_p2 = st.columns([0.82, 0.18])
                with c_p1:
                    st.markdown(f"• **{pinfo['description']}** (`{pno}`) &nbsp;|&nbsp; <span style='color: #0369A1; font-weight: 700;'>Rs. {pinfo['price']:,}</span> &nbsp;<span style='color: #64748B; font-size: 0.78rem;'>[{pinfo['board_type']}]</span>", unsafe_allow_html=True)
                with c_p2:
                    if st.button("❌ Remove", key=f"btn_rem_{pno}", use_container_width=True):
                        st.session_state["estimator_selected_parts"].pop(pno, None)
                        st.rerun()

            if st.button("🗑️ Clear All Selected Parts", key="btn_clear_all_parts"):
                st.session_state["estimator_selected_parts"] = {}
                st.rerun()

            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px dashed #CBD5E1;'>", unsafe_allow_html=True)

        parts_df = get_parts_by_model(selected_model)

        if parts_df.empty:
            st.warning(f"No historical spare parts recorded for `{selected_model}`.")
        else:
            avail_cnt = int((parts_df['branch_stock'] > 0).sum())
            zero_cnt = len(parts_df) - avail_cnt

            col_f1, col_f2 = st.columns([1.6, 1.4])
            with col_f1:
                search_part = st.text_input("🔍 Search Parts by Name / SKU:", placeholder="e.g. evaporator, valve, 1002...", key="p_search").strip().lower()
            with col_f2:
                board_types = ["-- All Categories --"] + sorted([b for b in parts_df['board_type'].dropna().unique() if b.strip()])
                sel_board = st.selectbox("Sub-Assembly Category:", options=board_types, key="p_board")

            col_avail, _ = st.columns([2, 1])
            with col_avail:
                stock_filter = st.radio(
                    "📦 Inventory Filter:",
                    options=[f"All Verified Compatible Parts ({len(parts_df)})", f"🟢 In-Stock Only (Karachi-2 Store) ({avail_cnt})"],
                    horizontal=True,
                    key="stock_filter",
                    help="Default shows all verified parts for accurate quotation even if out of stock in branch."
                )

            filtered_parts = parts_df.copy()

            if "In-Stock Only" in stock_filter:
                filtered_parts = filtered_parts[
                    (filtered_parts['branch_stock'] > 0) | 
                    (filtered_parts['part_no'].isin(st.session_state["estimator_selected_parts"].keys()))
                ]

            if search_part:
                tokens = [t.strip() for t in search_part.replace('-', ' ').split() if t.strip()]
                if tokens:
                    def match_part(row):
                        text = f"{row['part_no']} {row['part_description']} {row['board_type']}".lower()
                        norm = text.replace('-', ' ')
                        return all(tok in text or tok in norm for tok in tokens)
                    filtered_parts = filtered_parts[filtered_parts.apply(match_part, axis=1)]

            if sel_board != "-- All Categories --":
                filtered_parts = filtered_parts[filtered_parts['board_type'] == sel_board]

            st.caption(f"Showing **{len(filtered_parts)}** components ({avail_cnt} in stock at Karachi-2 Store, {zero_cnt} available via procurement/indent).")

            for idx, r in filtered_parts.iterrows():
                p_no = str(r['part_no'])
                p_desc = str(r['part_description'])
                p_board = str(r['board_type'])
                freq = int(r['historical_frequency'])
                p_price = int(r['retail_price']) if r['retail_price'] else 0
                b_stock = int(r['branch_stock']) if r['branch_stock'] else 0
                t_stock = int(r['tech_stock']) if r['tech_stock'] else 0
                tot_stock = int(r['total_stock']) if r['total_stock'] else 0
                is_pending = bool(r['is_pricing_pending'])
                cross_cnt = int(r['cross_model_count']) if r['cross_model_count'] else 1
                
                tech_alloc = {}
                try:
                    if r['tech_allocations_json']:
                        tech_alloc = json.loads(r['tech_allocations_json'])
                except Exception:
                    pass

                # Badges
                freq_badge = f'<span style="background-color: #FEF3C7; color: #92400E; padding: 2px 7px; border-radius: 10px; font-size: 0.72rem; font-weight: 700;">🔥 High Frequency ({freq} jobs)</span>' if freq >= 20 else f'<span style="background-color: #F1F5F9; color: #475569; padding: 2px 7px; border-radius: 10px; font-size: 0.72rem;">Replaced {freq} times</span>'
                
                if b_stock > 0:
                    stock_badge = f'<span class="stock-badge-in">🟢 Karachi-2 Store: {b_stock} In Stock</span>'
                else:
                    stock_badge = '<span class="stock-badge-out">🔴 Karachi-2 Store: 0 Available</span>'

                tech_pill = ""
                if tech_alloc:
                    t_details = ", ".join([f"{k} ({v})" for k, v in tech_alloc.items()])
                    tech_pill = f'&nbsp;<span style="background-color: #EFF6FF; color: #1D4ED8; padding: 2px 6px; border-radius: 10px; font-size: 0.72rem; font-weight: 600;">🤝 In Hand: {t_details}</span>'

                cross_pill = f'&nbsp;<span style="background-color: #F3E8FF; color: #6B21A8; padding: 2px 6px; border-radius: 10px; font-size: 0.72rem;">🌐 Fits {cross_cnt} models</span>' if cross_cnt > 1 else ""

                # Layout row
                with st.container():
                    c_chk, c_info, c_price = st.columns([0.08, 0.64, 0.28])
                    
                    is_already_selected = p_no in st.session_state["estimator_selected_parts"]
                    chk_val = c_chk.checkbox("", value=is_already_selected, key=f"chk_p_{selected_model}_{p_no}")

                    # Handle checkbox toggle
                    if chk_val != is_already_selected:
                        if chk_val:
                            st.session_state["estimator_selected_parts"][p_no] = {
                                'part_no': p_no,
                                'description': p_desc,
                                'price': p_price,
                                'board_type': p_board,
                                'is_pending': is_pending and (p_price == 0)
                            }
                        else:
                            st.session_state["estimator_selected_parts"].pop(p_no, None)
                        st.rerun()

                    with c_info:
                        st.markdown(f"""
                        <div style="line-height: 1.4; margin-bottom: 4px;">
                            <span style="font-weight: 700; color: #1E293B; font-size: 0.95rem;">{p_desc}</span><br>
                            <code style="color: #0369A1; font-weight: 600;">SKU: {p_no}</code> &nbsp;|&nbsp; 
                            <span style="color: #64748B; font-size: 0.8rem;">{p_board}</span><br>
                            <div style="margin-top: 3px;">
                                {freq_badge} &nbsp; {stock_badge} {tech_pill} {cross_pill}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if cross_cnt > 1:
                            with st.expander(f"🔍 View {cross_cnt} Compatible Models for {p_no}"):
                                compat_models = get_cross_model_compatibilities(p_no)
                                m_summary = ", ".join([f"**{m}** ({f})" for m, f in compat_models[:8]])
                                if len(compat_models) > 8:
                                    m_summary += f", +{len(compat_models)-8} more"
                                st.caption(f"Historically installed on: {m_summary}")

                    with c_price:
                        if is_pending or p_price == 0:
                            st.markdown('<span style="background-color: #FEF2F2; color: #991B1B; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; border: 1px solid #FECACA;">⚠️ Pending ERP Pricing</span>', unsafe_allow_html=True)
                            with st.expander("⚙️ Manual Price"):
                                new_val = st.number_input("Price (PKR):", min_value=0, step=500, key=f"inp_{p_no}")
                                if st.button("💾 Save", key=f"btn_{p_no}"):
                                    if new_val > 0:
                                        update_part_price(p_no, new_val)
                                        # If selected, update in session_state as well
                                        if p_no in st.session_state["estimator_selected_parts"]:
                                            st.session_state["estimator_selected_parts"][p_no]['price'] = int(new_val)
                                            st.session_state["estimator_selected_parts"][p_no]['is_pending'] = False
                                        st.success("Price updated in Database!")
                                        st.rerun()
                        else:
                            st.markdown(f'<div style="font-size: 1.05rem; font-weight: 700; color: #1E3A8A; text-align: right; padding-top: 4px;">Rs. {p_price:,}</div>', unsafe_allow_html=True)

                    st.markdown("<hr style='margin: 6px 0; border: none; border-top: 1px solid #F1F5F9;'>", unsafe_allow_html=True)

            # Calculation & Billing Card
            selected_parts_data = list(st.session_state["estimator_selected_parts"].values())
            parts_total = sum(p['price'] for p in selected_parts_data)
            visit_total = VISIT_CHARGES if chk_visit else 0
            mobility_total = MOBILITY_CHARGES if chk_mobility else 0
            gas_total = gas_amount if chk_gas else 0
            gross_total = parts_total + visit_total + mobility_total + gas_total

            if "under warranty" in billing_type.lower():
                customer_payable = 0
                policy_note = "Free of charge under manufacturer warranty."
            elif "partial warranty" in billing_type.lower():
                customer_payable = parts_total + gas_total
                policy_note = "Parts/Gas payable by customer; service & mobility covered under warranty."
            else:
                customer_payable = gross_total
                policy_note = "Standard commercial job — full parts and service charges apply."

            st.markdown("---")
            st.markdown("##### 📊 Real-Time Quotation Summary")

            col_sum1, col_sum2 = st.columns([1.5, 1])

            with col_sum2:
                st.markdown("###### 📲 Customer Details for Quote")
                c_name_input = st.text_input("Customer Name:", placeholder="e.g. Muhammad Abrar", key="q_cname").strip()
                c_phone_input = st.text_input("Customer Phone:", placeholder="e.g. 03402696414", key="q_phone").strip()
                c_serial_input = st.text_input("Unit Serial No (Optional):", placeholder="e.g. A1022381DD0013240425", key="q_serial").strip()

            # Itemized table rows (constructed without leading indentation to prevent markdown code block formatting)
            parts_rows_html = ""
            if selected_parts_data:
                for p in selected_parts_data:
                    p_price_str = f"Rs. {p['price']:,}" if p['price'] > 0 else "<span style='color:#B91C1C;'>Pending Price</span>"
                    parts_rows_html += (
                        f"<tr>"
                        f"<td style='padding: 3px 0 3px 14px; font-size: 0.84rem; color: #1E293B;'>"
                        f"• <b>{p['description']}</b> <code style='font-size:0.74rem;'>({p['part_no']})</code>"
                        f"</td>"
                        f"<td style='text-align: right; font-weight: 600; font-size: 0.86rem; color: #0F172A; white-space: nowrap;'>"
                        f"{p_price_str}"
                        f"</td>"
                        f"</tr>"
                    )
            else:
                parts_rows_html = (
                    "<tr>"
                    "<td style='padding: 3px 0 3px 14px; font-size: 0.82rem; color: #94A3B8; font-style: italic;'>"
                    "No spare parts selected (Standard service & inspection only)"
                    "</td>"
                    "<td style='text-align: right; color: #94A3B8;'>Rs. 0</td>"
                    "</tr>"
                )

            bill_card_html = (
                f"<div class='bill-card'>"
                f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>"
                f"<span style='font-size: 1.05rem; font-weight: 700; color: #0369A1;'>DWP Service Official Estimate</span>"
                f"<span class='badge-amount'>{billing_type.split()[0]}</span>"
                f"</div>"
                f"<table style='width: 100%; font-size: 0.88rem; line-height: 1.8; color: #334155; border-collapse: collapse;'>"
                f"<tr style='background-color: #F8FAFC; border-top: 1px solid #E2E8F0;'>"
                f"<td colspan='2' style='font-weight: 700; color: #0369A1; padding: 4px 0;'>"
                f"📦 Selected Spare Parts ({len(selected_parts_data)} item{'' if len(selected_parts_data) == 1 else 's'}):"
                f"</td>"
                f"</tr>"
                f"{parts_rows_html}"
                f"<tr style='border-top: 1px dashed #CBD5E1;'>"
                f"<td style='padding: 4px 0;'><b>Parts Subtotal:</b></td>"
                f"<td style='text-align: right; font-weight: 700; color: #0369A1;'>Rs. {parts_total:,}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding: 2px 0;'>Visit Charges:</td>"
                f"<td style='text-align: right;'>Rs. {visit_total:,}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding: 2px 0;'>Mobility / Labour Charges:</td>"
                f"<td style='text-align: right;'>Rs. {mobility_total:,}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding: 2px 0;'>Refrigerant Gas ({gas_label}):</td>"
                f"<td style='text-align: right;'>Rs. {gas_total:,}</td>"
                f"</tr>"
                f"<tr style='border-top: 2px solid #CBD5E1; font-weight: 800; font-size: 1.15rem; color: #0F172A;'>"
                f"<td style='padding-top: 8px;'>Total Customer Payable:</td>"
                f"<td style='text-align: right; padding-top: 8px; color: #0284C7;'>Rs. {customer_payable:,}</td>"
                f"</tr>"
                f"</table>"
                f"<div style='font-size: 0.76rem; color: #64748B; margin-top: 8px;'>"
                f"ℹ️ <b>Policy:</b> {policy_note}"
                f"</div>"
                f"</div>"
            )

            with col_sum1:
                st.markdown(bill_card_html, unsafe_allow_html=True)

            # WhatsApp Quotation Generator (Always live & reactive)
            parts_lines = ""
            if selected_parts_data:
                for i, p in enumerate(selected_parts_data, 1):
                    p_amt = f"Rs. {p['price']:,}" if p['price'] > 0 else "Pending ERP Confirmation"
                    parts_lines += f"{i}. {p['description']} ({p['part_no']}) - {p_amt}\n"
            else:
                parts_lines = "• No spare parts required (Standard service inspection)\n"

            display_cust_name = c_name_input if c_name_input else "Valued Customer"
            display_serial = c_serial_input if c_serial_input else "N/A"

            quote_text = f"""❄️ *DIGITAL WORLD PAKISTAN (PVT) LTD* ❄️
*Customer Service Official Quotation*
----------------------------------------
*Model:* {selected_model}
*Serial No:* {display_serial}
*Customer:* {display_cust_name}
*Warranty Status:* {billing_type}

*REQUIRED SPARE PARTS:*
{parts_lines}
*LABOUR & OVERHEADS:*
• Visit Charges: Rs. {visit_total:,}
• Labour & Mobility: Rs. {mobility_total:,}
{f'• Refrigerant Gas Refill ({gas_label}): Rs. {gas_total:,}' if chk_gas else ''}
----------------------------------------
💰 *NET ESTIMATE: Rs. {customer_payable:,}*
----------------------------------------
*Terms & Conditions:*
1. All genuine replacement parts carry official DWP warranty.
2. Prices are strictly per official Karachi-2 Store ERP price schedule.
3. Quotation valid for 7 days from issue date.

*Field Assistant Support:* 0322-8344755
"""

            st.markdown("##### 📋 Copy Customer WhatsApp Quotation")
            st.caption("Click the copy button on the top-right of the code box below to copy the complete formatted quotation.")
            st.code(quote_text, language="markdown")

            clean_ph = normalize_phone(c_phone_input) if c_phone_input else ""
            if clean_ph:
                wa_intl = "92" + clean_ph.lstrip("0")
                wa_link = f"https://api.whatsapp.com/send?phone={wa_intl}&text={urllib.parse.quote(quote_text)}"
                st.link_button(f"📲 Open WhatsApp Chat with {display_cust_name} ({clean_ph})", wa_link, use_container_width=True)

# ==========================================
# TAB 2: UNIT & CUSTOMER HISTORY
# ==========================================
with tab_history:
    st.markdown("##### 🔎 Smart Complaint & Unit Search")
    st.caption("Serial No, Customer Phone, ya Complaint No likh kar historical service record check karein.")

    query = st.text_input("Search Key Enter Karein:", placeholder="e.g. Serial No, 0322... ya 2826...").strip()

    if query:
        q_raw = query.upper().replace('=', '').replace('"', '').strip()
        q_phone = normalize_phone(query)
        match_df = search_history_records(q_raw, q_phone)

        if match_df.empty:
            st.warning(f"`{query}` ke against koi closed complaint nahi mili.")
        else:
            st.info(f"`{query}` ke **{len(match_df)}** closed service record(s) milay hain:")
            for _, r in match_df.iterrows():
                c_no = r['complaint_no']
                model = r['model']
                serial = r['serial']
                cust_name = r['customer_name']
                phone = r['phone']
                tech = r['technician_name']
                c_type = str(r['complaint_type']).strip()
                p_date = r['purchase_date']
                c_date = r['complaint_date']
                closed_date = r['closed_date']
                remarks = r['remarks'] if r['remarks'] else "No closing remarks logged."
                closed_amt = int(r.get('closed_amount', 0))

                amt_display = f"Rs. {closed_amt:,}" if closed_amt > 0 else ("Free Under Warranty" if "warranty" in c_type.lower() else "Rs. 0 (Nil Collection)")
                badge_class = "badge-cash" if "cash" in c_type.lower() else ("badge-partial" if "partial" in c_type.lower() else "badge-warranty")

                st.markdown(f"""
                <div class="history-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 700; color: #1E293B; font-size: 1rem;">Complaint #{c_no}</span>
                        <div>
                            <span class="badge-amount">{amt_display}</span>
                            <span class="{badge_class}">{c_type}</span>
                        </div>
                    </div>
                    <div style="font-size: 0.85rem; color: #334155; line-height: 1.5;">
                        <b>Model:</b> {model} &nbsp;|&nbsp; <b>Serial:</b> <code>{serial}</code><br>
                        <b>Customer:</b> {cust_name} (📞 {phone})<br>
                        <b>Technician:</b> {tech}<br>
                        <b>Complaint Date:</b> {c_date} &nbsp;|&nbsp; <b>Closed Date:</b> {closed_date}<br>
                        <b>Purchase Date:</b> {p_date if p_date else 'N/A'}<br>
                        <hr style="margin: 6px 0; border: none; border-top: 1px dashed #CBD5E1;">
                        <b>Closing Remarks:</b> <span style="color: #0369A1; font-weight: 500;">{remarks}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# ==========================================
# TAB 3: TECHNICIAN PERFORMANCE
# ==========================================
with tab_perf:
    perf_data = fetch_performance_data()
    if perf_data.empty:
        st.info("ℹ️ **Technician Performance Report Abhi Load Nahi Hai.**\n\nSidebar mein **Module 3: Performance Sync** ke andar dono files upload karke **Update Technician Performance** dabayein.")
    else:
        perf_data['parsed_date'] = pd.to_datetime(perf_data['closed_date'], errors='coerce')
        valid_dates = perf_data['parsed_date'].dropna()

        st.markdown("##### 📅 Select Date Range for KPI Evaluation")
        col_d1, col_d2 = st.columns(2)
        min_avail = valid_dates.min().date() if not valid_dates.empty else datetime.now().date()
        max_avail = valid_dates.max().date() if not valid_dates.empty else datetime.now().date()
        default_start = max(min_avail, max_avail.replace(day=1)) if max_avail else min_avail

        with col_d1:
            start_date = st.date_input("From Date:", value=default_start, min_value=min_avail, max_value=max_avail)
        with col_d2:
            end_date = st.date_input("To Date:", value=max_avail, min_value=min_avail, max_value=max_avail)

        mask = (perf_data['parsed_date'].dt.date >= start_date) & (perf_data['parsed_date'].dt.date <= end_date)
        scoped_data = perf_data[mask].copy()

        if scoped_data.empty:
            st.warning(f"{start_date.strftime('%d-%b-%Y')} se {end_date.strftime('%d-%b-%Y')} ke darmiyan koi complaints nahi mili.")
        else:
            tot_assigned = len(scoped_data)
            tot_completed = int((scoped_data['status'] == 'COMPLETED').sum())
            efficiency = (tot_completed / max(tot_assigned, 1)) * 100

            st.markdown(f"""
            <div class="scope-box">
                📅 <b>Selected Scope:</b> {start_date.strftime('%d-%b-%Y')} se {end_date.strftime('%d-%b-%Y')} tak &nbsp;|&nbsp; <b>Note:</b> Transferred calls excluded from KPI
            </div>
            """, unsafe_allow_html=True)

            k1, k2, k3 = st.columns(3)
            k1.metric("Assigned Complaints", f"{tot_assigned:,}")
            k2.metric("Completed Complaints", f"{tot_completed:,}")
            k3.metric("Zone Efficiency", f"{efficiency:.1f}%")

            st.divider()

            all_techs = ["-- All Technicians (Branch View) --"] + sorted([t for t in scoped_data['technician_name'].dropna().unique() if t.strip()])
            selected_tech = st.selectbox("👤 Select Technician (Personal Score):", options=all_techs)

            filtered_df = scoped_data[scoped_data['technician_name'] == selected_tech] if selected_tech != "-- All Technicians (Branch View) --" else scoped_data

            pvt = pd.pivot_table(
                filtered_df,
                index='technician_name',
                columns='status',
                values='complaint_no',
                aggfunc='count',
                fill_value=0
            )

            for s in ['COMPLETED', 'CANCELED', 'REJECTED', 'NIL']:
                if s not in pvt.columns:
                    pvt[s] = 0

            pvt = pvt[['COMPLETED', 'CANCELED', 'REJECTED', 'NIL']]
            pvt.rename(columns={'COMPLETED': 'Completed', 'CANCELED': 'Canceled', 'REJECTED': 'Rejected', 'NIL': 'Nil'}, inplace=True)
            pvt['Total Assigned'] = pvt.sum(axis=1)
            pvt['Completion Rate (%)'] = ((pvt['Completed'] / pvt['Total Assigned']) * 100).round(1).astype(str) + '%'
            pvt.sort_values(by='Total Assigned', ascending=False, inplace=True)

            st.dataframe(pvt, use_container_width=True)

# ==========================================
# SUPPORT BOX & CONTACT FOOTER
# ==========================================
st.markdown("""
<div class="support-box">
    ⚠️ <b>Koi Masla ya Error Aa Raha Hai?</b><br>
    Agar application mein koi ghalti, model na milna, ya galat estimate show ho raha ho, toh screen ka <b>Screenshot</b> le kar rabta karein:<br>
    📞 <b>WhatsApp / Call:</b> <code>03228344755</code> &nbsp;|&nbsp; ✉️ <b>Email:</b> <code>muhammad.abrar@ecostar.com.pk</code>
</div>
<div class="credit-footer">
    DWP Service Field Assistant Engine | Operations Support: <b>Muhammad Abrar</b>
</div>
""", unsafe_allow_html=True)