# app.py
from __future__ import annotations
import os
import sys
from pathlib import Path
import importlib
import re
import urllib.parse
from datetime import datetime, date
import calendar
import json
import pandas as pd
import streamlit as st

# Ensure application root directory is first in sys.path (critical for Streamlit Cloud)
APP_ROOT = str(Path(__file__).resolve().parent)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import importlib

import database
if not hasattr(database, "try_reconnect_turso"):
    importlib.reload(database)
from database import (
    search_history_records, fetch_performance_data,
    init_estimator_schema, get_all_models_for_estimator,
    get_parts_by_model, update_part_price,
    get_missing_price_parts_df, get_cross_model_compatibilities,
    get_all_cross_model_compatibilities_map,
    is_turso_active, get_database_status, try_reconnect_turso
)

import etl
if not hasattr(etl, "sync_all_complaints_pipeline"):
    importlib.reload(etl)
from etl import (
    normalize_phone, ingest_performance_pipeline, ingest_feedback_and_pricing,
    parse_store_stock_pdf, sync_model_part_catalog_from_feedback,
    sync_all_complaints_pipeline
)

import config
if not hasattr(config, "AC_SERVICE_CHARGES"):
    importlib.reload(config)
from config import (
    VISIT_CHARGES, MOBILITY_CHARGES, BASE_FIXED_TOTAL, calculate_gas_charge,
    VALVE_BYPASS_CHARGES, AC_SERVICE_CHARGES
)

# Page Configuration - Wide layout for high productivity split dashboard
st.set_page_config(
    page_title="DWP Field Assistant", 
    page_icon="❄️", 
    layout="wide", 
    initial_sidebar_state="auto"
)

# Initialize database schema and auto-seed if required
init_estimator_schema()

# Top-level session state initialization
if "estimator_selected_parts" not in st.session_state:
    st.session_state["estimator_selected_parts"] = {}
if "estimator_active_model" not in st.session_state:
    st.session_state["estimator_active_model"] = None

# Top-level cached queries to eliminate redundant round-trips over Turso Cloud
@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_all_models():
    return get_all_models_for_estimator()

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_parts_by_model(model_name: str):
    return get_parts_by_model(model_name)

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_cross_model_compatibilities(part_no: str):
    return get_cross_model_compatibilities(part_no)

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_all_cross_compatibilities_map():
    return get_all_cross_model_compatibilities_map()

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_missing_price_parts_df():
    return get_missing_price_parts_df()

@st.cache_data(ttl=3600, show_spinner="Loading Technician KPI Data...")
def get_cached_performance_data():
    df = fetch_performance_data()
    if df is None or df.empty:
        return pd.DataFrame(), None, None, [], []
    df = df.copy()
    df['parsed_date'] = pd.to_datetime(df['closed_date'], errors='coerce')
    valid_dates = df['parsed_date'].dropna()
    min_avail = valid_dates.min().date() if not valid_dates.empty else date(2025, 1, 1)
    max_avail = valid_dates.max().date() if not valid_dates.empty else datetime.now().date()
    df['month_period'] = df['closed_date'].astype(str).str.slice(0, 7)
    available_months = sorted([m for m in df['month_period'].dropna().unique() if len(m) == 7 and m.startswith('20')], reverse=True)
    if 'branch_name' in df.columns:
        raw_branches = [b for b in df['branch_name'].dropna().unique() if str(b).strip()]
        available_branches = ["Karachi 2 HA"] + sorted([b for b in raw_branches if b != "Karachi 2 HA"])
    else:
        available_branches = ["Karachi 2 HA"]
    return df, min_avail, max_avail, available_months, available_branches

# ==========================================
# CUSTOM STYLING: SLEEK CORPORATE CLAYMORPHISM
# ==========================================
st.markdown("""
<style>
    .stApp {
        --dwp-border: rgba(128, 128, 128, 0.22);
    }

    .main-title { 
        font-size: 1.65rem; 
        font-weight: 800; 
        color: var(--text-color) !important; 
        margin-bottom: 0.15rem; 
        letter-spacing: -0.025em;
    }
    
    .sub-title { 
        font-size: 0.88rem; 
        color: var(--text-color) !important; 
        opacity: 0.82; 
        margin-bottom: 0.95rem; 
    }
    
    /* Claymorphism 3D Inflated Cards & Step Boxes */
    .dwp-step-box {
        background-color: var(--secondary-background-color, rgba(128,128,128,0.06)) !important;
        border: 1px solid var(--dwp-border) !important;
        border-left: 5px solid var(--text-color) !important;
        border-radius: 18px !important;
        padding: 12px 18px !important;
        margin-top: 10px !important;
        margin-bottom: 14px !important;
        color: var(--text-color) !important;
        box-shadow: 6px 6px 16px rgba(0, 0, 0, 0.06), 
                    inset 2px 2px 4px rgba(255, 255, 255, 0.22), 
                    inset -2px -2px 4px rgba(0, 0, 0, 0.05) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    }

    .dwp-step-box:hover {
        transform: translateY(-2px);
        box-shadow: 8px 8px 20px rgba(0, 0, 0, 0.09), 
                    inset 2px 2px 4px rgba(255, 255, 255, 0.3), 
                    inset -2px -2px 4px rgba(0, 0, 0, 0.06) !important;
    }
    
    .dwp-step-title {
        font-weight: 700;
        font-size: 1.0rem;
        color: var(--text-color) !important;
    }

    /* Claymorphism Cart & Bill Card */
    .dwp-cart-box, .bill-card {
        background-color: var(--secondary-background-color, rgba(128,128,128,0.06)) !important;
        border: 1px solid var(--dwp-border) !important;
        border-radius: 20px !important;
        padding: 16px !important;
        margin-bottom: 14px !important;
        color: var(--text-color) !important;
        box-shadow: 7px 7px 18px rgba(0, 0, 0, 0.07), 
                    inset 2px 2px 4px rgba(255, 255, 255, 0.22), 
                    inset -2px -2px 4px rgba(0, 0, 0, 0.05) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    }

    .dwp-cart-box:hover, .bill-card:hover {
        transform: translateY(-2px);
        box-shadow: 9px 9px 22px rgba(0, 0, 0, 0.1), 
                    inset 2px 2px 4px rgba(255, 255, 255, 0.32), 
                    inset -2px -2px 4px rgba(0, 0, 0, 0.06) !important;
    }

    /* Part Row Clay Card inside Bounded Catalog Container */
    .part-clay-card {
        background-color: var(--secondary-background-color, rgba(128,128,128,0.06)) !important;
        border: 1px solid var(--dwp-border) !important;
        border-radius: 16px !important;
        padding: 12px 14px !important;
        margin-bottom: 10px !important;
        box-shadow: 4px 4px 12px rgba(0, 0, 0, 0.05), 
                    inset 1.5px 1.5px 3px rgba(255, 255, 255, 0.2), 
                    inset -1.5px -1.5px 3px rgba(0, 0, 0, 0.04) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }

    .part-clay-card:hover {
        transform: translateY(-1.5px);
        box-shadow: 6px 6px 15px rgba(0, 0, 0, 0.08), 
                    inset 1.5px 1.5px 3px rgba(255, 255, 255, 0.3) !important;
    }

    /* 3D Clay Pills & Badges */
    .dwp-badge {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.74rem;
        border: 1px solid var(--dwp-border) !important;
        box-shadow: 3px 3px 7px rgba(0,0,0,0.06), 
                    inset 1px 1px 2px rgba(255,255,255,0.25), 
                    inset -1px -1px 2px rgba(0,0,0,0.04) !important;
        display: inline-block;
    }

    .dwp-badge-highlight {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.74rem;
        border: 1.5px solid var(--text-color) !important;
        box-shadow: 3px 3px 8px rgba(0,0,0,0.08), 
                    inset 1px 1px 2px rgba(255,255,255,0.3), 
                    inset -1px -1px 2px rgba(0,0,0,0.05) !important;
        display: inline-block;
    }

    .badge-amount {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 700;
        border: 1.5px solid var(--text-color) !important;
        box-shadow: 3px 3px 7px rgba(0,0,0,0.06), 
                    inset 1px 1px 2px rgba(255,255,255,0.25) !important;
        margin-right: 4px;
        display: inline-block;
    }

    .badge-cash, .badge-partial, .badge-warranty {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 600;
        border: 1px solid var(--dwp-border) !important;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.05), inset 1px 1px 2px rgba(255,255,255,0.2) !important;
        display: inline-block;
    }

    .status-badge-completed {
        background-color: rgba(34, 197, 94, 0.12) !important;
        color: #16a34a !important;
        border: 1px solid rgba(34, 197, 94, 0.4) !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 700;
        display: inline-block;
        margin-right: 4px;
        box-shadow: 3px 3px 8px rgba(22, 163, 74, 0.12), inset 1px 1px 2px rgba(255,255,255,0.3) !important;
    }

    .status-badge-rejected {
        background-color: rgba(239, 68, 68, 0.12) !important;
        color: #dc2626 !important;
        border: 1px solid rgba(239, 68, 68, 0.4) !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 700;
        display: inline-block;
        margin-right: 4px;
        box-shadow: 3px 3px 8px rgba(220, 38, 38, 0.12), inset 1px 1px 2px rgba(255,255,255,0.3) !important;
    }

    .status-badge-canceled {
        background-color: rgba(245, 158, 11, 0.12) !important;
        color: #d97706 !important;
        border: 1px solid rgba(245, 158, 11, 0.4) !important;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 700;
        display: inline-block;
        margin-right: 4px;
        box-shadow: 3px 3px 8px rgba(217, 119, 6, 0.12), inset 1px 1px 2px rgba(255,255,255,0.3) !important;
    }

    /* Stock Status Badges */
    .stock-badge-in { 
        background-color: rgba(34, 197, 94, 0.1) !important; 
        color: #16a34a !important; 
        font-weight: 700; 
        padding: 3px 10px; 
        border-radius: 9999px; 
        font-size: 0.73rem; 
        border: 1px solid rgba(34, 197, 94, 0.3) !important; 
        box-shadow: 2px 2px 6px rgba(0,0,0,0.04), inset 1px 1px 2px rgba(255,255,255,0.25) !important;
        display: inline-block; 
    }
    
    .stock-badge-out { 
        background-color: var(--secondary-background-color) !important; 
        color: var(--text-color) !important; 
        font-weight: 700; 
        padding: 3px 10px; 
        border-radius: 9999px; 
        font-size: 0.73rem; 
        border: 1px solid var(--dwp-border) !important; 
        opacity: 0.75; 
        box-shadow: 2px 2px 6px rgba(0,0,0,0.04), inset 1px 1px 2px rgba(255,255,255,0.2) !important;
        display: inline-block; 
    }

    /* Checkbox & Radio Labels Full Wrap */
    div[data-testid="stCheckbox"] label p {
        white-space: normal !important;
        font-size: 0.85rem !important;
        line-height: 1.3 !important;
    }

    /* Ultra-Compact 2-Line Clay Part Card & Meta */
    .compact-part-name {
        font-weight: 700;
        font-size: 0.87rem;
        color: var(--text-color) !important;
        line-height: 1.22;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }

    .compact-meta-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 5px;
        font-size: 0.71rem;
        color: var(--text-color) !important;
        margin-top: 3px;
        line-height: 1.15;
    }

    .compact-meta-pill {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        font-weight: 600;
        padding: 1px 7px;
        border-radius: 9999px;
        font-size: 0.69rem;
        border: 1px solid var(--dwp-border) !important;
        box-shadow: 1px 1px 3px rgba(0,0,0,0.04);
        display: inline-flex;
        align-items: center;
        white-space: nowrap;
    }

    /* 3D Clay Physical Buttons */
    div.stButton > button {
        border-radius: 14px !important;
        border: 1px solid var(--dwp-border) !important;
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        font-weight: 700 !important;
        box-shadow: 5px 5px 12px rgba(0, 0, 0, 0.08), 
                    inset 1.5px 1.5px 3px rgba(255, 255, 255, 0.3), 
                    inset -1.5px -1.5px 3px rgba(0, 0, 0, 0.05) !important;
        transition: all 0.15s ease-in-out !important;
    }

    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 7px 7px 16px rgba(0, 0, 0, 0.12), 
                    inset 1.5px 1.5px 3px rgba(255, 255, 255, 0.4), 
                    inset -1.5px -1.5px 3px rgba(0, 0, 0, 0.06) !important;
    }

    div.stButton > button:active {
        transform: translateY(1px) !important;
        box-shadow: inset 2px 2px 5px rgba(0, 0, 0, 0.15), 
                    inset -1px -1px 2px rgba(255, 255, 255, 0.2) !important;
    }

    /* WhatsApp Link Button Clay Styling */
    a[data-testid="stLinkButton"] {
        border-radius: 14px !important;
        background: #16a34a !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        box-shadow: 5px 5px 14px rgba(22, 163, 74, 0.35), 
                    inset 1.5px 1.5px 3px rgba(255, 255, 255, 0.45), 
                    inset -1.5px -1.5px 3px rgba(0, 0, 0, 0.2) !important;
        transition: all 0.15s ease-in-out !important;
    }
    
    a[data-testid="stLinkButton"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 7px 7px 18px rgba(22, 163, 74, 0.48) !important;
    }

    /* Metric Tiles in Tab 3 */
    div[data-testid="stMetric"] {
        background-color: var(--secondary-background-color) !important;
        border-radius: 18px !important;
        border: 1px solid var(--dwp-border) !important;
        padding: 14px 18px !important;
        box-shadow: 5px 5px 14px rgba(0, 0, 0, 0.06), 
                    inset 1.5px 1.5px 3px rgba(255, 255, 255, 0.25), 
                    inset -1.5px -1.5px 3px rgba(0, 0, 0, 0.04) !important;
        transition: transform 0.2s ease !important;
    }

    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
    }

    .dwp-bill-table {
        width: 100%;
        font-size: 0.88rem;
        line-height: 1.8;
        color: var(--text-color) !important;
        border-collapse: collapse;
    }

    .dwp-bill-table tr, .dwp-bill-table td, .dwp-bill-table th {
        color: var(--text-color) !important;
    }

    .dwp-item-desc {
        font-weight: 700;
        color: var(--text-color) !important;
        font-size: 0.94rem;
    }

    .dwp-item-sku {
        color: var(--text-color) !important;
        background-color: transparent !important;
        font-weight: 700;
        opacity: 0.85;
    }

    .dwp-price-tag {
        font-size: 1.05rem;
        font-weight: 800;
        color: var(--text-color) !important;
        text-align: right;
    }

    .history-card { 
        background-color: var(--secondary-background-color, rgba(128,128,128,0.06)) !important; 
        border: 1px solid var(--dwp-border) !important; 
        border-radius: 18px !important; 
        padding: 16px !important; 
        margin-bottom: 14px !important; 
        color: var(--text-color) !important; 
        box-shadow: 5px 5px 14px rgba(0, 0, 0, 0.06), 
                    inset 2px 2px 4px rgba(255, 255, 255, 0.22), 
                    inset -2px -2px 4px rgba(0, 0, 0, 0.04) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    }

    .history-card:hover {
        transform: translateY(-2px);
        box-shadow: 8px 8px 20px rgba(0, 0, 0, 0.09) !important;
    }

    .unit-timeline-card {
        background-color: var(--secondary-background-color, rgba(128,128,128,0.06)) !important;
        border: 1.5px solid var(--dwp-border) !important;
        border-radius: 20px !important;
        padding: 18px 20px !important;
        margin-bottom: 18px !important;
        color: var(--text-color) !important;
        box-shadow: 6px 6px 16px rgba(0, 0, 0, 0.06), 
                    inset 2px 2px 4px rgba(255, 255, 255, 0.25), 
                    inset -2px -2px 4px rgba(0, 0, 0, 0.04) !important;
    }

    .timeline-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: var(--background-color, #ffffff);
        border: 1px solid var(--dwp-border);
        border-radius: 12px;
        padding: 4px 10px;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--text-color);
        box-shadow: inset 1px 1px 2px rgba(255, 255, 255, 0.4), 1px 1px 4px rgba(0,0,0,0.04);
        margin-right: 6px;
        margin-top: 4px;
    }
    
    .scope-box { 
        background-color: var(--secondary-background-color, rgba(128,128,128,0.06)) !important; 
        border: 1px solid var(--dwp-border) !important; 
        padding: 10px 14px !important; 
        border-radius: 14px !important; 
        font-size: 0.82rem; 
        color: var(--text-color) !important; 
        margin-bottom: 14px; 
        box-shadow: 3px 3px 8px rgba(0,0,0,0.05), inset 1px 1px 2px rgba(255,255,255,0.2) !important;
    }
    
    .credit-footer { 
        font-size: 0.76rem; 
        color: var(--text-color) !important; 
        opacity: 0.75; 
        text-align: center; 
        margin-top: 1.8rem; 
        border-top: 1px solid var(--dwp-border) !important; 
        padding-top: 12px; 
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">❄️ DWP Service Field Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Field Diagnostic, Cost & Live Stock Estimator, History & KPI Hub</div>', unsafe_allow_html=True)

# ==========================================
# SIDEBAR: DATA SYNC, CLOUD PERSISTENCE & SUPPORT
# ==========================================
with st.sidebar:
    st.markdown("### 📥 Daily Service & Performance Sync")
    db_status = get_database_status()
    if db_status == "TURSO_ONLINE":
        st.markdown("<div style='margin-bottom:8px;'><span class='status-badge-completed'>🟢 Cloud Storage: Permanent (Turso Cloud)</span></div>", unsafe_allow_html=True)
    elif db_status == "TURSO_FALLBACK_LOCAL":
        st.markdown("<div style='margin-bottom:8px;'><span class='status-badge-canceled' title='Turso Cloud network latency detected. High-speed local snapshot active.'>🟡 High-Speed Local Snapshot Active (Cloud Syncing)</span></div>", unsafe_allow_html=True)
        if st.button("🔄 Retry Turso Cloud Connection", key="btn_retry_turso", width="stretch"):
            with st.spinner("Connecting to Turso Cloud..."):
                ok, msg = try_reconnect_turso()
                if ok:
                    st.success("Reconnected to Turso Cloud!")
                    st.rerun()
                else:
                    st.warning(f"Turso Cloud unreachable: {msg}. Continuing on local snapshot.")
    else:
        st.markdown("<div style='margin-bottom:8px;'><span class='dwp-badge'>💻 Local Storage (dwp_service.db)</span></div>", unsafe_allow_html=True)
    st.caption("Upload complaints to update Master History, Technician KPI, and Parts Catalog simultaneously.")
    sync_fb = st.file_uploader("1. Quality Feedback Report (Completed)", type=["csv", "xlsx", "xls"], key="sync_fb")
    sync_can = st.file_uploader("2. Cancel / Nil / Transfer Report (Optional)", type=["xlsx", "xls"], key="sync_can")
    sync_coll = st.file_uploader("3. Collection Pricing File (Optional)", type=["xlsx", "xls"], key="sync_coll")

    if st.button("🔄 Sync All Complaints & Performance", width="stretch"):
        if sync_fb:
            with st.spinner("Syncing Master History, KPI & Catalog..."):
                try:
                    import gc
                    gc.collect()
                    perf_cnt, m_cnt, p_cnt = sync_all_complaints_pipeline(sync_fb, sync_can, sync_coll)
                    st.cache_data.clear()
                    gc.collect()
                    st.success(f"Synced successfully! {perf_cnt:,} KPI records, {m_cnt} models, {p_cnt} parts updated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync error: {e}")
        else:
            st.error("Quality Feedback Report lazmi upload karein!")

    if not is_turso_active() and os.path.exists(database.DB_FILE):
        try:
            with open(database.DB_FILE, "rb") as fp_db:
                st.download_button(
                    label="💾 Download Database Backup (.db)",
                    data=fp_db.read(),
                    file_name="dwp_service.db",
                    mime="application/x-sqlite3",
                    width="stretch",
                    help="Container reboot se pehle updated database file download karein."
                )
        except Exception:
            pass

    st.markdown("---")
    st.markdown("### 📦 Store Stock & Retail Pricing Sync")
    st.caption("Store Wise Stock Movement PDF upload karein taky Karachi-2 Store live inventory aur retail prices update hon.")
    sync_pdf = st.file_uploader("Latest Stock Movement PDF", type=["pdf"], key="sync_pdf")
    if st.button("🔄 Sync Live Stock & Prices", width="stretch"):
        if sync_pdf:
            with st.spinner("Updating Live Stock & Prices..."):
                try:
                    import gc
                    gc.collect()
                    cnt = parse_store_stock_pdf(sync_pdf)
                    st.cache_data.clear()
                    gc.collect()
                    st.success(f"Stock & prices updated for {cnt:,} items!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Stock PDF parse error: {e}")
        else:
            st.error("Stock Movement PDF upload karein!")

    st.markdown("---")
    st.markdown("### 📋 Estimator & Pricing Tools")
    try:
        missing_df = get_cached_missing_price_parts_df()
        if not missing_df.empty:
            csv_data = missing_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Download Missing Prices CSV ({len(missing_df)} SKUs)",
                data=csv_data,
                file_name="dwp_pending_erp_pricing_parts.csv",
                mime="text/csv",
                width="stretch"
            )
    except Exception:
        pass

    # Clean Operations & Support box with Clay styling inside Sidebar
    st.markdown("---")
    st.markdown("""
    <div style="background-color: var(--secondary-background-color, rgba(128,128,128,0.06)); border: 1px solid var(--dwp-border, rgba(128,128,128,0.22)); border-radius: 16px; padding: 14px; font-size: 0.8rem; color: var(--text-color); box-shadow: 4px 4px 12px rgba(0,0,0,0.06), inset 1.5px 1.5px 3px rgba(255,255,255,0.2);">
        <b>⚠️ Operations & Support Help:</b><br>
        Agar application mein koi ghalti, model na milna, ya galat estimate show ho raha ho, toh screen ka screenshot le kar rabta karein:<br>
        📞 <b>Call / WhatsApp:</b> <code>03228344755</code><br>
        ✉️ <b>Email:</b> <code>muhammad.abrar@ecostar.com.pk</code>
    </div>
    <div style="font-size: 0.72rem; color: var(--text-color); opacity: 0.7; text-align: center; margin-top: 10px;">
        DWP Field Operations Support: <b>Muhammad Abrar</b>
    </div>
    """, unsafe_allow_html=True)

# Main Navigation Tabs
tab_estimator, tab_history, tab_perf = st.tabs([
    "🧮 Spare Parts & Cost Estimator",
    "🔍 Unit & Customer History", 
    "📊 Technician Performance"
])

# ==========================================
# TAB 1: SPARE PARTS & COST ESTIMATOR (2-COLUMN SPLIT LAYOUT)
# ==========================================
with tab_estimator:
    all_models = get_cached_all_models()
    if not all_models:
        st.info("Catalog is initializing...")
        sync_model_part_catalog_from_feedback()
        parse_store_stock_pdf()
        get_cached_all_models.clear()
        all_models = get_cached_all_models()

    # 2-Column Split: Left side for Model & Parts Explorer, Right side for Live Sticky Estimate & WhatsApp Checkout
    col_parts, col_quote = st.columns([1.5, 1.0], gap="large")

    with col_parts:
        # STEP 1: MODEL SELECTION
        st.markdown("<div class='dwp-step-box'><span class='dwp-step-title'>🏷️ STEP 1: Select Model</span></div>", unsafe_allow_html=True)

        selected_model = st.selectbox(
            "Select Appliance Model:",
            options=all_models,
            index=0 if all_models else None,
            help="Search across 500+ Gree and EcoStar models (e.g. GS-18PITH11W, GR-E8890G, WD-300F)",
            key="sel_model_main",
            label_visibility="collapsed"
        )

        if selected_model:
            if st.session_state.get("estimator_active_model") != selected_model:
                st.session_state["estimator_selected_parts"] = {}
                st.session_state["estimator_active_model"] = selected_model
                if "p_board" in st.session_state:
                    st.session_state["p_board"] = "All Categories"
                if "p_search" in st.session_state:
                    st.session_state["p_search"] = ""

            gas_amount, gas_label = calculate_gas_charge(selected_model)
            parts_df = get_cached_parts_by_model(selected_model)

            # STEP 2: COMPATIBLE SPARE PARTS & CATEGORY EXPLORER
            st.markdown("<div class='dwp-step-box'><span class='dwp-step-title'>🔩 STEP 2: Compatible Spare Parts</span></div>", unsafe_allow_html=True)

            if parts_df.empty:
                st.warning(f"No historical spare parts recorded for `{selected_model}`.")
            else:
                avail_cnt = int((parts_df['branch_stock'] > 0).sum())
                zero_cnt = len(parts_df) - avail_cnt

                # Sub-Assembly Category Selection & Search Controls
                categories = sorted([b for b in parts_df['board_type'].dropna().unique() if b.strip()])
                cat_options = ["All Categories"] + categories
                category_counts = parts_df['board_type'].value_counts().to_dict()
                
                def format_cat_label(cat_name):
                    if cat_name == "All Categories":
                        return f"All Categories ({len(parts_df)})"
                    return f"{cat_name} ({category_counts.get(cat_name, 0)})"
                
                col_c1, col_c2 = st.columns([1.3, 1.7])
                with col_c1:
                    sel_board = st.selectbox(
                        "📦 Sub-Assembly:",
                        options=cat_options,
                        format_func=format_cat_label,
                        key="p_board",
                        help="Filter parts by functional sub-assembly"
                    )
                    
                with col_c2:
                    search_part = st.text_input(
                        "🔍 Search Parts by Name / SKU:", 
                        placeholder="e.g. evaporator, valve, 1002...", 
                        key="p_search"
                    ).strip().lower()

                stock_filter = st.radio(
                    "📦 Branch Inventory Scope:",
                    options=[f"All Verified Compatible ({len(parts_df)})", f"🟢 In-Stock Only (Karachi-2 Store) ({avail_cnt})"],
                    horizontal=True,
                    key="stock_filter"
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

                if sel_board != "All Categories":
                    filtered_parts = filtered_parts[filtered_parts['board_type'] == sel_board]

                st.caption(f"Showing **{len(filtered_parts)}** components ({avail_cnt} in stock at Karachi-2 Store, {zero_cnt} available via indent).")

                # Bounded Scroll Container with Claymorphism Part Cards
                cross_compat_map = get_cached_all_cross_compatibilities_map()
                with st.container(height=560):
                    if filtered_parts.empty:
                        st.info("No matching spare parts found for the selected category/search filter.")
                    else:
                        for idx, r in filtered_parts.iterrows():
                            p_no = str(r['part_no'])
                            p_desc = str(r['part_description'])
                            p_board = str(r['board_type'])
                            freq = int(r['historical_frequency'])
                            p_price = int(r['retail_price']) if r['retail_price'] else 0
                            b_stock = int(r['branch_stock']) if r['branch_stock'] else 0
                            is_pending = bool(r['is_pricing_pending'])
                            cross_cnt = int(r['cross_model_count']) if r['cross_model_count'] else 1

                            # Construct hover tooltip for compatible models without taking vertical space
                            compat_models = cross_compat_map.get(p_no, [])
                            if compat_models:
                                tooltip_txt = "Compatible Models: " + ", ".join([f"{m} ({f})" for m, f in compat_models[:10]])
                                if len(compat_models) > 10:
                                    tooltip_txt += f", +{len(compat_models)-10} more"
                            else:
                                tooltip_txt = f"Fits model {selected_model}"

                            freq_badge = f'<span class="compact-meta-pill" style="border: 1px solid var(--text-color); font-weight: 700;">🔥 {freq} jobs</span>' if freq >= 20 else f'<span class="compact-meta-pill">{freq} jobs</span>'
                            stock_badge = f'<span class="compact-meta-pill" style="color: #16a34a; border-color: rgba(34,197,94,0.4); background: rgba(34,197,94,0.08); font-weight:700;">🟢 Karachi-2: {b_stock}</span>' if b_stock > 0 else '<span class="compact-meta-pill" style="opacity: 0.7;">⚪ Karachi-2: 0</span>'
                            cross_pill = f'<span class="compact-meta-pill" title="{tooltip_txt}" style="cursor: help;">🌐 Fits {cross_cnt} models</span>' if cross_cnt > 1 else ""

                            is_already_selected = p_no in st.session_state["estimator_selected_parts"]
                            
                            with st.container():
                                c_chk, c_info, c_price = st.columns([0.07, 0.71, 0.22])
                                chk_val = c_chk.checkbox("Select component", value=is_already_selected, key=f"chk_p_{selected_model}_{p_no}", label_visibility="collapsed")

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
                                    <div style="line-height: 1.25;">
                                        <span class="compact-part-name" title="{p_desc}">{p_desc}</span>
                                        <div class="compact-meta-row">
                                            <code style="font-size:0.73rem; font-weight:700; opacity:0.85;">SKU: {p_no}</code>
                                            <span class="compact-meta-pill">[{p_board}]</span>
                                            {stock_badge}
                                            {freq_badge}
                                            {cross_pill}
                                        </div>
                                    </div>
                                    """, unsafe_allow_html=True)

                                with c_price:
                                    if is_pending or p_price == 0:
                                        st.markdown('<div style="text-align:right;"><span class="compact-meta-pill" style="border: 1px solid var(--text-color); font-weight: 700; color: #dc2626;">⚠️ Pending</span></div>', unsafe_allow_html=True)
                                    else:
                                        st.markdown(f'<div style="font-size:0.96rem; font-weight:800; text-align:right; color:var(--text-color); padding-top:2px;">Rs. {p_price:,}</div>', unsafe_allow_html=True)

                                st.markdown("<hr style='margin: 4px 0 5px 0; border: none; border-top: 1px solid var(--dwp-border); opacity: 0.5;'>", unsafe_allow_html=True)

    with col_quote:
        if not selected_model:
            st.info("👈 Please select an appliance model from Step 1 to generate an estimate.")
        else:
            selected_parts_data = list(st.session_state["estimator_selected_parts"].values())
            parts_total = sum(p['price'] for p in selected_parts_data)

            # Selected Parts Cart Container with Claymorphism
            st.markdown(f"""
            <div class="dwp-cart-box">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="dwp-step-title">
                        🛒 Selected Parts ({len(selected_parts_data)})
                    </span>
                    <span class="dwp-price-tag" style="padding-top: 0; font-size: 0.98rem;">
                        Subtotal: Rs. {parts_total:,}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if selected_parts_data:
                for pno, pinfo in list(st.session_state["estimator_selected_parts"].items()):
                    cp1, cp2 = st.columns([0.82, 0.18])
                    with cp1:
                        st.markdown(f"• **{pinfo['description']}** (`{pno}`)<br><span style='font-size:0.86rem; font-weight:700;'>Rs. {pinfo['price']:,}</span> &nbsp;<span class='dwp-badge'>[{pinfo['board_type']}]</span>", unsafe_allow_html=True)
                    with cp2:
                        if st.button("❌", key=f"btn_rem_{pno}", help="Remove component"):
                            st.session_state["estimator_selected_parts"].pop(pno, None)
                            st.rerun()

                if st.button("🗑️ Clear All Selected Parts", key="btn_clear_all_parts", width="stretch"):
                    st.session_state["estimator_selected_parts"] = {}
                    st.rerun()
            else:
                st.caption("ℹ️ No spare parts selected yet. Check items on the left to include them.")

            # STEP 3: BASE OVERHEADS & SERVICE CHARGES
            st.markdown("<div class='dwp-step-box'><span class='dwp-step-title'>💵 STEP 3: Service & Labour Charges</span></div>", unsafe_allow_html=True)

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                chk_visit = st.checkbox(f"🚗 Visit Charges (Rs. {VISIT_CHARGES:,})", value=True, key="chk_visit")
                chk_bypass = st.checkbox(f"🔄 4-Way Valve Bypass (Rs. {VALVE_BYPASS_CHARGES:,})", value=False, key="chk_bypass")
            with col_b2:
                chk_mobility = st.checkbox(f"🔧 Labour & Mobility (Rs. {MOBILITY_CHARGES:,})", value=True, key="chk_mobility")
                chk_service = st.checkbox(f"🧼 AC Service Charges (Rs. {AC_SERVICE_CHARGES:,})", value=False, key="chk_service")

            chk_gas = st.checkbox(f"⚡ Gas Refill (+Rs. {gas_amount:,}) - {gas_label}", value=False, key="chk_gas")

            # Calculation & Grand Total Breakdown
            visit_total = VISIT_CHARGES if chk_visit else 0
            mobility_total = MOBILITY_CHARGES if chk_mobility else 0
            bypass_total = VALVE_BYPASS_CHARGES if chk_bypass else 0
            service_total = AC_SERVICE_CHARGES if chk_service else 0
            gas_total = gas_amount if chk_gas else 0
            customer_payable = parts_total + visit_total + mobility_total + bypass_total + service_total + gas_total

            # STEP 4: CUSTOMER DETAILS & ESTIMATE
            st.markdown("<div class='dwp-step-box'><span class='dwp-step-title'>📊 STEP 4: Official Estimate & Quotation</span></div>", unsafe_allow_html=True)

            col_cp1, col_cp2 = st.columns(2)
            with col_cp1:
                c_complaint_input = st.text_input("Complaint No (Optional):", placeholder="e.g. 2826010...", key="q_complaint").strip()
                c_name_input = st.text_input("Customer Name:", placeholder="e.g. Muhammad Abrar", key="q_cname").strip()
            with col_cp2:
                c_serial_input = st.text_input("Serial No (Optional):", placeholder="e.g. A1022381...", key="q_serial").strip()
                c_phone_input = st.text_input("Customer Phone:", placeholder="e.g. 03402696414", key="q_phone").strip()

            # Itemized table rows
            parts_rows_html = ""
            if selected_parts_data:
                for p in selected_parts_data:
                    p_price_str = f"Rs. {p['price']:,}" if p['price'] > 0 else "<span>Pending Price</span>"
                    parts_rows_html += (
                        f"<tr>"
                        f"<td style='padding: 3px 0 3px 10px; font-size: 0.83rem;'>"
                        f"• <b>{p['description']}</b> <code>({p['part_no']})</code>"
                        f"</td>"
                        f"<td style='text-align: right; font-weight: 600; font-size: 0.85rem; white-space: nowrap;'>"
                        f"{p_price_str}"
                        f"</td>"
                        f"</tr>"
                    )
            else:
                parts_rows_html = (
                    "<tr>"
                    "<td style='padding: 3px 0 3px 10px; font-size: 0.82rem; font-style: italic;'>"
                    "No spare parts selected (Standard service & inspection only)"
                    "</td>"
                    "<td style='text-align: right;'>Rs. 0</td>"
                    "</tr>"
                )

            bill_card_html = (
                f"<div class='bill-card'>"
                f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>"
                f"<span style='font-size: 1.0rem; font-weight: 700;'>Official Estimate Breakdown</span>"
                f"<span class='dwp-badge'>Official Quote</span>"
                f"</div>"
                f"<table class='dwp-bill-table'>"
                f"<tr style='border-top: 1px solid var(--dwp-border);'>"
                f"<td colspan='2' style='font-weight: 700; padding: 4px 0;'>"
                f"📦 Selected Spare Parts ({len(selected_parts_data)}):"
                f"</td>"
                f"</tr>"
                f"{parts_rows_html}"
                f"<tr style='border-top: 1px dashed var(--dwp-border);'>"
                f"<td style='padding: 4px 0;'><b>Parts Subtotal:</b></td>"
                f"<td style='text-align: right; font-weight: 700;'>Rs. {parts_total:,}</td>"
                f"</tr>"
                f"{f'<tr><td style=\"padding: 2px 0;\">Visit Charges:</td><td style=\"text-align: right;\">Rs. {visit_total:,}</td></tr>' if chk_visit else ''}"
                f"{f'<tr><td style=\"padding: 2px 0;\">Labour & Mobility:</td><td style=\"text-align: right;\">Rs. {mobility_total:,}</td></tr>' if chk_mobility else ''}"
                f"{f'<tr><td style=\"padding: 2px 0;\">4-Way Valve Bypass:</td><td style=\"text-align: right;\">Rs. {bypass_total:,}</td></tr>' if chk_bypass else ''}"
                f"{f'<tr><td style=\"padding: 2px 0;\">AC Service Charges:</td><td style=\"text-align: right;\">Rs. {service_total:,}</td></tr>' if chk_service else ''}"
                f"{f'<tr><td style=\"padding: 2px 0;\">Gas Charges ({gas_label}):</td><td style=\"text-align: right;\">Rs. {gas_total:,}</td></tr>' if chk_gas else ''}"
                f"<tr style='border-top: 2px solid var(--dwp-border); font-weight: 800; font-size: 1.15rem;'>"
                f"<td style='padding-top: 8px;'>Total Customer Payable:</td>"
                f"<td style='text-align: right; padding-top: 8px;'>Rs. {customer_payable:,}</td>"
                f"</tr>"
                f"</table>"
                f"<div style='font-size: 0.74rem; opacity: 0.8; margin-top: 8px;'>"
                f"ℹ️ <b>Policy:</b> Standard commercial job — all genuine replacement parts carry official DWP warranty."
                f"</div>"
                f"</div>"
            )

            st.markdown(bill_card_html, unsafe_allow_html=True)

            # WhatsApp Quotation Generator
            parts_lines = ""
            if selected_parts_data:
                for i, p in enumerate(selected_parts_data, 1):
                    p_amt = f"Rs. {p['price']:,}" if p['price'] > 0 else "Pending ERP Confirmation"
                    parts_lines += f"{i}. {p['description']} ({p['part_no']}) - {p_amt}\n"
            else:
                parts_lines = "• No spare parts required (Inspection / General Service)\n"

            display_cust_name = c_name_input if c_name_input else "Valued Customer"
            display_serial = c_serial_input if c_serial_input else "N/A"
            display_complaint = c_complaint_input if c_complaint_input else "N/A"

            service_charges_lines = []
            if chk_visit:
                service_charges_lines.append(f"• Visit Charges: Rs. {visit_total:,}")
            if chk_mobility:
                service_charges_lines.append(f"• Labour & Mobility: Rs. {mobility_total:,}")
            if chk_bypass:
                service_charges_lines.append(f"• 4-Way Valve Bypass: Rs. {bypass_total:,}")
            if chk_service:
                service_charges_lines.append(f"• AC Service Charges: Rs. {service_total:,}")
            if chk_gas:
                service_charges_lines.append(f"• Gas: Rs. {gas_total:,}")
            if not service_charges_lines:
                service_charges_lines.append("• Nil / No additional service charges")
            service_charges_text = "\n".join(service_charges_lines)

            quote_text = f"""*Complaint No:* {display_complaint}
*Model:* {selected_model}
*Serial No:* {display_serial}
*Customer:* {display_cust_name}

*REQUIRED PARTS:*
{parts_lines.strip()}

*LABOUR & SERVICE CHARGES:*
{service_charges_text}
----------------------------------------
💰 *Total: Rs. {customer_payable:,}*
----------------------------------------"""

            st.markdown("###### 📋 Customer WhatsApp Quotation")
            st.code(quote_text, language="markdown")

            clean_ph = normalize_phone(c_phone_input) if c_phone_input else ""
            if clean_ph:
                wa_intl = "92" + clean_ph.lstrip("0")
                wa_link = f"https://api.whatsapp.com/send?phone={wa_intl}&text={urllib.parse.quote(quote_text)}"
                st.link_button(f"📲 Open WhatsApp Chat with {display_cust_name} ({clean_ph})", wa_link, width="stretch")

# ==========================================
# TAB 2: UNIT & CUSTOMER HISTORY
# ==========================================
with tab_history:
    st.markdown("##### 🔎 Smart Complaint & Unit Search")
    st.caption("Serial No, Customer Phone, ya Complaint No likh kar purana record check karein.")

    query = st.text_input("Search Key Enter Karein:", placeholder="e.g. Serial No, 0322... ya 2826...", key="hist_search_key").strip()

    if query:
        q_raw = query.upper().replace('=', '').replace('"', '').strip()
        q_phone = normalize_phone(query)
        with st.spinner("Searching records..."):
            match_df = search_history_records(q_raw, q_phone)

        if match_df.empty:
            st.warning(f"`{query}` ke against koi record nahi mila.")
        else:
            # Calculate Unit Timeline & Lifecycle Metrics
            total_records = len(match_df)
            models = [m for m in match_df['model'].dropna().unique() if m and m != 'N/A']
            unit_model = models[0] if models else "N/A"
            serials = [s for s in match_df['serial'].dropna().unique() if s and s != 'N/A']
            unit_serial = serials[0] if serials else "N/A"
            primary_cust = match_df.iloc[0]['customer_name'] or "Valued Customer"
            primary_phone = match_df.iloc[0]['phone'] or "N/A"
            
            all_dates = []
            for dt_col in ['closed_date', 'complaint_date']:
                if dt_col in match_df.columns:
                    for d_val in match_df[dt_col].dropna():
                        d_str = str(d_val).strip()
                        if d_str and d_str != 'N/A':
                            all_dates.append(d_str)
            first_service = all_dates[-1] if all_dates else "N/A"
            latest_service = all_dates[0] if all_dates else "N/A"
            latest_tech = match_df.iloc[0]['technician_name'] or "N/A"
            total_spent = sum(int(amt) for amt in match_df.get('closed_amount', [0]) if pd.notna(amt))

            st.markdown(f"""
            <div class="unit-timeline-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 800; font-size: 1.05rem; color: var(--text-color); letter-spacing: -0.01em;">
                        📋 Unit Lifecycle & Service History Summary
                    </span>
                    <span class="status-badge-completed">✨ {total_records} Verified Service Event(s)</span>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px;">
                    <span class="timeline-chip">🏷️ <b>Model:</b> {unit_model}</span>
                    <span class="timeline-chip">🔢 <b>Serial:</b> <code>{unit_serial}</code></span>
                    <span class="timeline-chip">👤 <b>Customer:</b> {primary_cust} (📞 {primary_phone})</span>
                    <span class="timeline-chip">👨‍🔧 <b>Latest Tech:</b> {latest_tech}</span>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 4px; font-size: 0.82rem;">
                    <span class="timeline-chip">🗓️ <b>First Service:</b> {first_service}</span>
                    <span class="timeline-chip">🚀 <b>Latest Service:</b> {latest_service}</span>
                    <span class="timeline-chip">💰 <b>Total Recorded Invoiced:</b> Rs. {total_spent:,}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"###### 📑 Detailed Historical Service Tickets ({total_records})")
            for _, r in match_df.iterrows():
                raw_c_no = str(r['complaint_no'])
                c_no = raw_c_no.replace('="', '').replace('"', '').strip()
                raw_serial = str(r['serial'])
                serial = raw_serial.replace('="', '').replace('"', '').strip()
                model = r['model']
                cust_name = r['customer_name']
                phone = r['phone']
                tech = r['technician_name']
                c_type = str(r['complaint_type']).strip()
                p_date = r['purchase_date']
                c_date = r['complaint_date']
                closed_date = r['closed_date']
                remarks = r['remarks'] if r['remarks'] else "No remarks logged."
                closed_amt = int(r.get('closed_amount', 0))
                status = str(r.get('status', 'COMPLETED')).upper().strip()

                if status == 'COMPLETED':
                    status_badge = '<span class="status-badge-completed">🟢 Completed</span>'
                elif status in ['CANCELED', 'NIL']:
                    status_badge = f'<span class="status-badge-canceled">🟠 {status.title()}</span>'
                else:
                    status_badge = f'<span class="status-badge-rejected">🔴 {status.title()}</span>'

                amt_display = f"Rs. {closed_amt:,}" if closed_amt > 0 else ("Free Under Warranty" if "warranty" in c_type.lower() else "Rs. 0 (Nil Collection)")
                badge_class = "badge-cash" if "cash" in c_type.lower() else ("badge-partial" if "partial" in c_type.lower() else "badge-warranty")

                st.markdown(f"""
                <div class="history-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 700; color: var(--text-color); font-size: 1rem;">Complaint #{c_no}</span>
                        <div>
                            {status_badge}
                            <span class="badge-amount">{amt_display}</span>
                            <span class="{badge_class}">{c_type}</span>
                        </div>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-color); line-height: 1.5;">
                        <b>Model:</b> {model} &nbsp;|&nbsp; <b>Serial:</b> <code>{serial}</code><br>
                        <b>Customer:</b> {cust_name} (📞 {phone})<br>
                        <b>Technician:</b> {tech}<br>
                        <b>Complaint Date:</b> {c_date} &nbsp;|&nbsp; <b>Closed Date:</b> {closed_date}<br>
                        <b>Purchase Date:</b> {p_date if p_date else 'N/A'}<br>
                        <hr style="margin: 6px 0; border: none; border-top: 1px dashed var(--dwp-border);">
                        <b>Closing Remarks:</b> <span style="color: var(--text-color); font-weight: 500; opacity: 0.9;">{remarks}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# ==========================================
# TAB 3: TECHNICIAN PERFORMANCE
# ==========================================
with tab_perf:
    perf_data, min_avail, max_avail, available_months, available_branches = get_cached_performance_data()
    if perf_data.empty:
        st.info("ℹ️ **Technician Performance Report Abhi Load Nahi Hai.**\n\nSidebar mein **Quality Feedback Report** upload karke **Sync All Complaints & Performance** dabayein.")
    else:
        st.markdown("##### 📅 Select Branch & Period for KPI Evaluation")
        
        col_br, col_pr = st.columns([1, 1])
        with col_br:
            branch_options = available_branches.copy()
            if "-- All Branches --" not in branch_options:
                branch_options.append("-- All Branches --")
            sel_branch = st.selectbox(
                "🏢 Select Branch:",
                options=branch_options,
                index=0,
                key="sel_kpi_branch"
            )

        with col_pr:
            month_labels = {}
            for m_str in available_months:
                try:
                    dt_m = datetime.strptime(m_str, '%Y-%m')
                    month_labels[m_str] = dt_m.strftime('%B %Y')
                except Exception:
                    month_labels[m_str] = m_str

            period_options = [f"🗓️ {month_labels[m]}" for m in available_months]
            period_options += ["🌐 Full Year Baseline (All Time)", "⚙️ Custom Date Range..."]
            
            sel_period = st.selectbox(
                "📅 Evaluation Period:",
                options=period_options,
                index=0 if period_options else None,
                key="sel_kpi_period"
            )

        min_calendar = min(date(2025, 1, 1), min_avail) if min_avail else date(2025, 1, 1)
        max_calendar = max(max_avail, datetime.now().date()) if max_avail else datetime.now().date()

        if "Custom Date Range" in str(sel_period):
            col_d1, col_d2 = st.columns(2)
            default_start = max(min_calendar, max_avail.replace(day=1)) if max_avail else min_calendar
            with col_d1:
                start_date = st.date_input("From Date:", value=default_start, min_value=min_calendar, max_value=max_calendar, key="kpi_fdate")
            with col_d2:
                end_date = st.date_input("To Date:", value=max_calendar, min_value=min_calendar, max_value=max_calendar, key="kpi_tdate")
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            period_label = f"{start_date.strftime('%d-%b-%Y')} se {end_date.strftime('%d-%b-%Y')} tak"
        elif "Full Year Baseline" in str(sel_period):
            start_str = "2025-01-01"
            end_str = "2099-12-31"
            period_label = "Full Year Baseline (All Recorded History)"
        else:
            chosen_m = None
            for m_key, m_lab in month_labels.items():
                if m_lab in str(sel_period):
                    chosen_m = m_key
                    break
            if not chosen_m and available_months:
                chosen_m = available_months[0]
            if not chosen_m:
                chosen_m = datetime.now().strftime('%Y-%m')

            dt_start = datetime.strptime(chosen_m, '%Y-%m')
            _, last_day = calendar.monthrange(dt_start.year, dt_start.month)
            dt_end = dt_start.replace(day=last_day)
            start_str = dt_start.strftime('%Y-%m-%d')
            end_str = dt_end.strftime('%Y-%m-%d')
            period_label = f"{dt_start.strftime('%B %Y')} (01-{dt_start.strftime('%b')} to {last_day:02d}-{dt_start.strftime('%b-%Y')})"

        # Filter by date range and branch
        mask = (perf_data['closed_date'] >= start_str) & (perf_data['closed_date'] <= end_str)
        if sel_branch != "-- All Branches --" and 'branch_name' in perf_data.columns:
            mask = mask & (perf_data['branch_name'] == sel_branch)
        scoped_data = perf_data[mask].copy()

        if scoped_data.empty:
            st.warning(f"{sel_branch} | {period_label} ke darmiyan koi complaints nahi mili.")
        else:
            branch_label_html = f"🏢 <b>Branch:</b> {sel_branch}" if sel_branch != "-- All Branches --" else "🏢 <b>Branch:</b> All Branches (Enterprise View)"
            st.markdown(f"""
            <div class="scope-box">
                {branch_label_html} &nbsp;|&nbsp; 📅 <b>Selected Scope:</b> {period_label} &nbsp;|&nbsp; <b>Note:</b> Transferred calls excluded from KPI
            </div>
            """, unsafe_allow_html=True)

            # Build summary table across all named technicians (strictly filter out blank technician rows)
            table_scoped = scoped_data[scoped_data['technician_name'].astype(str).str.strip() != ''].copy()

            if not table_scoped.empty:
                all_pvt = pd.pivot_table(
                    table_scoped,
                    index='technician_name',
                    columns='status',
                    values='complaint_no',
                    aggfunc='count',
                    fill_value=0
                )

                for s in ['COMPLETED', 'REJECTED', 'CANCELED', 'NIL']:
                    if s not in all_pvt.columns:
                        all_pvt[s] = 0

                completed_series = all_pvt['COMPLETED']
                rejected_series = all_pvt['REJECTED']
                canceled_series = all_pvt['CANCELED'] + all_pvt['NIL']
                assigned_series = all_pvt.sum(axis=1)

                # Calculate Avg Days per technician on completed jobs with non-null days
                tech_days_map = {}
                for t_name, grp in table_scoped.groupby('technician_name'):
                    valid_days = grp[grp['status'] == 'COMPLETED']['days'].dropna()
                    if not valid_days.empty:
                        tech_days_map[t_name] = f"{valid_days.mean():.1f}"
                    else:
                        tech_days_map[t_name] = "-"

                summary_df = pd.DataFrame({
                    'Technician': all_pvt.index,
                    'Assigned': assigned_series.values,
                    'Completed': completed_series.values,
                    'Rejected': rejected_series.values,
                    'Canceled': canceled_series.values,
                    'Avg Days': [tech_days_map.get(t, "-") for t in all_pvt.index]
                })

                # Sort strictly based on completed volume descending, then assigned volume descending
                summary_df = summary_df.sort_values(by=['Completed', 'Assigned'], ascending=[False, False])
                summary_df = summary_df.reset_index(drop=True)

                # Add sequential ranking column starting from 1
                summary_df.insert(0, 'Sr. No', range(1, len(summary_df) + 1))
            else:
                summary_df = pd.DataFrame()

            # Technician selector candidates
            tech_candidates = sorted([t for t in scoped_data['technician_name'].dropna().unique() if str(t).strip()])
            all_techs = ["-- All Technicians (Branch View) --"] + tech_candidates

            if "sel_kpi_tech" not in st.session_state or st.session_state["sel_kpi_tech"] not in all_techs:
                st.session_state["sel_kpi_tech"] = "-- All Technicians (Branch View) --"

            active_tech = st.session_state["sel_kpi_tech"]

            # Dynamic KPI calculation: Switch dynamically between Branch and Selected Technician
            if active_tech == "-- All Technicians (Branch View) --":
                active_subset = scoped_data
                eff_title = "Branch Efficiency" if sel_branch != "-- All Branches --" else "Enterprise Efficiency"
            else:
                active_subset = scoped_data[scoped_data['technician_name'] == active_tech]
                eff_title = "Personal Efficiency"

            tot_assigned = len(active_subset)
            tot_completed = int((active_subset['status'] == 'COMPLETED').sum())
            tot_rejected = int((active_subset['status'] == 'REJECTED').sum())
            tot_canceled = int((active_subset['status'].isin(['CANCELED', 'NIL'])).sum())
            efficiency = (tot_completed / max(tot_assigned, 1)) * 100

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Total Assigned", f"{tot_assigned:,}")
            k2.metric("Completed", f"{tot_completed:,}")
            k3.metric("Rejected", f"{tot_rejected:,}")
            k4.metric("Canceled", f"{tot_canceled:,}")
            k5.metric(eff_title, f"{efficiency:.1f}%")

            # Top 3 Best Performers Showcase (Standard Streamlit Metric Cards)
            if not summary_df.empty:
                top3 = summary_df[summary_df['Completed'] > 0].head(3)
                if not top3.empty:
                    st.markdown("##### 🏆 Top 3 Best Performers")
                    medals = ["🥇 1st Place", "🥈 2nd Place", "🥉 3rd Place"]
                    top_cols = st.columns(len(top3))
                    for idx, (t_col, (_, r_data)) in enumerate(zip(top_cols, top3.iterrows())):
                        with t_col:
                            p_name = r_data['Technician']
                            p_comp = int(r_data['Completed'])
                            p_ass = int(r_data['Assigned'])
                            p_days = r_data['Avg Days']
                            p_eff = (p_comp / max(p_ass, 1)) * 100
                            speed_txt = f" • ⚡ {p_days} Days Avg" if p_days != "-" else ""
                            
                            st.metric(
                                label=f"{medals[idx]}: {p_name}",
                                value=f"{p_comp:,} Completed",
                                delta=f"{p_eff:.1f}% Efficiency{speed_txt}"
                            )
                            if st.button(f"🔍 Inspect {p_name}", key=f"btn_inspect_podium_{idx}", width="stretch"):
                                st.session_state["sel_kpi_tech"] = p_name
                                st.rerun()

            st.divider()

            # Technician Selector dropdown
            selected_tech_idx = all_techs.index(st.session_state["sel_kpi_tech"])
            chosen_tech = st.selectbox(
                "👤 Select Technician (Personal Score):",
                options=all_techs,
                index=selected_tech_idx,
                key="sel_kpi_tech_box"
            )
            if chosen_tech != st.session_state["sel_kpi_tech"]:
                st.session_state["sel_kpi_tech"] = chosen_tech
                st.rerun()

            # Render Ranking Table
            if not summary_df.empty:
                # Highlight selected technician row while keeping full ranking visible
                def highlight_selected(row):
                    if active_tech != "-- All Technicians (Branch View) --" and row['Technician'] == active_tech:
                        return ['background-color: rgba(30, 144, 255, 0.22); font-weight: bold; border-left: 4px solid #1E90FF;'] * len(row)
                    return [''] * len(row)

                styled_df = summary_df.style.apply(highlight_selected, axis=1)
                st.dataframe(styled_df, hide_index=True, width="stretch")
            else:
                st.info("No technician data found for the selected branch and period.")

# Clean, subtle credit footer at the bottom of the page
st.markdown("""
<div class="credit-footer">
    DWP Service Assistant Engine • Digital World Pakistan (Pvt) Ltd
</div>
""", unsafe_allow_html=True)