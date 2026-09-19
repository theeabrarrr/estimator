import os
import re
import sqlite3
import urllib.parse
import pandas as pd
import streamlit as st

DB_NAME = "dwp_service_v5.db"
DEFAULT_FB_FILE = "quality_feedback_report_14SEP2026_170840.csv"
DEFAULT_COLL_FILE = "Detail_Collection_14SEP26_052528PM.xlsx"

st.set_page_config(
    page_title="DWP Field Assistant", 
    page_icon="❄️", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# Custom Styling
st.markdown("""
<style>
    .main-title { font-size: 1.4rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.1rem; }
    .sub-title { font-size: 0.82rem; color: #64748B; margin-bottom: 0.8rem; }
    .bill-card { background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 12px; border-radius: 6px; margin: 10px 0; }
    .grand-total { font-size: 1.5rem; font-weight: 800; color: #0F172A; }
    .history-card { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .badge-warranty { background-color: #DCFCE7; color: #15803D; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-cash { background-color: #FEE2E2; color: #B91C1C; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-partial { background-color: #FEF3C7; color: #B45309; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-amount { background-color: #EFF6FF; color: #1D4ED8; padding: 3px 8px; border-radius: 12px; font-size: 0.78rem; font-weight: 700; border: 1px solid #BFDBFE; margin-right: 4px; }
    .credit-footer { font-size: 0.75rem; color: #94A3B8; text-align: center; margin-top: 2rem; border-top: 1px solid #E2E8F0; padding-top: 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">❄️ DWP Service Field Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Field Diagnostic, Cost Estimator & Customer Unit History Engine</div>', unsafe_allow_html=True)

def clean_val(val):
    if pd.isna(val):
        return ""
    return str(val).strip().replace('=', '').replace('"', '').strip()

# =========================================================
# CORE BUILDER & PERSISTENCE
# =========================================================
def build_and_save_data(fb_source, coll_source):
    fb = pd.read_csv(fb_source, low_memory=False) if isinstance(fb_source, str) or fb_source.name.endswith('.csv') else pd.read_excel(fb_source)
    coll = pd.read_excel(coll_source)

    fb['C_NO_CLEAN'] = fb['COMPLAINT_NO'].apply(clean_val)
    fb['SERIAL_CLEAN'] = fb['SERIAL'].apply(clean_val).str.upper()
    fb['PHONE_CLEAN'] = fb['PHONE_NO'].apply(clean_val)
    fb['MODEL_CLEAN'] = fb['MODEL_NAME'].astype(str).str.strip().str.upper()
    
    # Identify remarks column
    rem_col = next((c for c in ['FEEDBACK_REMARKS', 'REMARKS', 'CLOSING_REMARKS', 'TECHNICIAN_REMARKS', 'TECH_REMARKS'] if c in fb.columns), None)
    fb['REMARKS_CLEAN'] = fb[rem_col].apply(clean_val) if rem_col else ""

    # Clean collection complaint number
    c_no_coll_col = next((c for c in ['Complaint No', 'COMPLAINT_NO', 'COMPLAINT NO', 'Complaint_No'] if c in coll.columns), 'Complaint No')
    coll['C_NO_CLEAN'] = coll[c_no_coll_col].apply(clean_val)

    # EXACT COLUMN: Net Collection
    if 'Net Collection' in coll.columns:
        coll['NET_COLLECTION_CLEAN'] = pd.to_numeric(coll['Net Collection'], errors='coerce').fillna(0).astype(int)
    else:
        net_col = next((c for c in coll.columns if 'net collection' in str(c).lower()), None)
        coll['NET_COLLECTION_CLEAN'] = pd.to_numeric(coll[net_col], errors='coerce').fillna(0).astype(int) if net_col else 0

    # Pricing logic for Estimator (Untouched)
    coll['EFFECTIVE_PART_PRICE'] = coll['Part Cash'].where(coll['Part Cash'] > 0, coll['Part Warranty'])
    coll_sub = coll[coll['EFFECTIVE_PART_PRICE'] > 0][['C_NO_CLEAN', 'EFFECTIVE_PART_PRICE']]
    merged = pd.merge(fb, coll_sub, on='C_NO_CLEAN', how='inner')

    single_jobs = merged[~merged['HARDWARE_PART_NOS'].str.contains(',', na=False)].copy()
    single_jobs['PART_NO'] = single_jobs['HARDWARE_PART_NOS'].str.strip()
    
    exact_price_map = single_jobs.groupby('PART_NO')['EFFECTIVE_PART_PRICE'].agg(
        lambda x: x.mode()[0] if not x.mode().empty else x.median()
    ).to_dict()

    records = []
    for _, row in fb.iterrows():
        pnos = str(row['HARDWARE_PART_NOS'])
        prods = str(row['HARDWARE_PRODUCTS'])
        if pd.isna(row['HARDWARE_PART_NOS']) or pnos.lower() == 'nan' or not pnos.strip():
            continue
        pno_list = [p.strip() for p in pnos.split(',') if p.strip()]
        prod_list = [p.strip() for p in prods.split(',') if p.strip()]
        for i, pno in enumerate(pno_list):
            pname = prod_list[i] if i < len(prod_list) else (prod_list[0] if prod_list else "Component")
            price = exact_price_map.get(pno, 0)
            records.append({
                'MODEL': row['MODEL_CLEAN'],
                'PART_NO': pno,
                'PART_NAME': pname,
                'PRICE': price
            })
            
    parts_df = pd.DataFrame(records).drop_duplicates(subset=['MODEL', 'PART_NO'])
    
    # Map Exact Net Collection to Feedback Records by Complaint No
    coll_amt_map = coll.groupby('C_NO_CLEAN')['NET_COLLECTION_CLEAN'].max().to_dict()
    fb['CLOSED_AMOUNT'] = fb['C_NO_CLEAN'].map(coll_amt_map).fillna(0).astype(int)

    # Save to SQLite
    conn = sqlite3.connect(DB_NAME)
    parts_df.to_sql('parts_master', conn, if_exists='replace', index=False)
    
    fb_save = fb[['C_NO_CLEAN', 'SERIAL_CLEAN', 'PHONE_CLEAN', 'MODEL_CLEAN', 
                  'CUSTOMER_NAME', 'TECHNICIAN_NAME', 'COMPLAINT_TYPE', 
                  'PURCHASE_DATE', 'COMPLAINT_DATE', 'CLOSED_DATE', 
                  'REMARKS_CLEAN', 'CLOSED_AMOUNT']].copy()
    fb_save.to_sql('history_master', conn, if_exists='replace', index=False)
    
    c = conn.cursor()
    c.execute("CREATE INDEX IF NOT EXISTS idx_hist ON history_master(SERIAL_CLEAN, PHONE_CLEAN, C_NO_CLEAN)")
    conn.commit()
    conn.close()

# Auto Database Bootstrap
@st.cache_resource
def init_system():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='parts_master'")
    exists = c.fetchone()
    conn.close()
    
    if not exists:
        if os.path.exists(DEFAULT_FB_FILE) and os.path.exists(DEFAULT_COLL_FILE):
            build_and_save_data(DEFAULT_FB_FILE, DEFAULT_COLL_FILE)

init_system()

@st.cache_data
def get_cached_store():
    conn = sqlite3.connect(DB_NAME)
    parts_df = pd.read_sql_query("SELECT * FROM parts_master", conn)
    models = pd.read_sql_query("SELECT DISTINCT MODEL FROM parts_master ORDER BY MODEL ASC", conn)['MODEL'].tolist()
    conn.close()
    return parts_df, models

parts_df, all_models = get_cached_store()

# =========================================================
# SIDEBAR: DATA UPDATE
# =========================================================
with st.sidebar:
    st.subheader("⚙️ Data Sync Center")
    st.caption("Upload fresh ERP reports to update parts and history.")
    
    up_fb = st.file_uploader("1. Quality Feedback (CSV/Excel)", type=["csv", "xlsx", "xls"], key="fb_up")
    up_coll = st.file_uploader("2. Collection Pricing (Excel)", type=["xlsx", "xls"], key="coll_up")
    
    if up_fb and up_coll:
        if st.button("Sync System Data"):
            with st.spinner("Processing & Synchronizing..."):
                build_and_save_data(up_fb, up_coll)
                st.cache_data.clear()
                st.cache_resource.clear()
                st.success("Synchronized successfully!")
                st.rerun()

# =========================================================
# CAPACITY & GAS SPECIFICATIONS (FIXED RULE ORDER)
# =========================================================
def get_tonnage_specs(model_str):
    m = str(model_str).upper()
    if any(x in m for x in ['48', '60', '36', '36TFIH', 'TFIH']):
        return '4.0 Ton', 13000, 70000, 55000
    elif any(x in m for x in ['24', '26']):
        return '2.0 Ton', 8500, 39000, 45000
    elif any(x in m for x in ['18', '16']):
        return '1.5 Ton', 7000, 26000, 40000
    elif any(x in m for x in ['12', '11']) or re.search(r'[^0-9]10[^0-9]', m):
        return '1.0 Ton', 5500, 20000, 35000
    return '1.5 Ton', 7000, 26000, 40000

# Navigation Tabs
tab_estimator, tab_history = st.tabs(["🧮 Cost Estimator", "🔍 Unit & Customer History"])

# ==========================================
# TAB 1: COST ESTIMATOR (UNTOUCHED)
# ==========================================
with tab_estimator:
    selected_model = st.selectbox("🔍 Step 1: Select Appliance Model Number", options=["-- Search Model --"] + all_models)

    if selected_model != "-- Search Model --":
        ton_label, gas_charge_amount, def_evap, def_pcb = get_tonnage_specs(selected_model)
        
        fam_match = re.match(r"^([A-Z0-9]+-[0-9]{2}[A-Z]+)", selected_model)
        family_code = fam_match.group(1) if fam_match else selected_model[:7]

        direct_parts = parts_df[parts_df['MODEL'] == selected_model]
        family_parts = parts_df[parts_df['MODEL'].str.startswith(family_code)]
        available = pd.concat([direct_parts, family_parts]).drop_duplicates(subset=['PART_NO']).copy()

        for i, r in available.iterrows():
            if r['PRICE'] == 0:
                name_lower = str(r['PART_NAME']).lower()
                if 'evap' in name_lower:
                    available.at[i, 'PRICE'] = def_evap
                elif '1/4' in name_lower:
                    available.at[i, 'PRICE'] = 1600
                elif any(v in name_lower for v in ['1/2', '5/8', '3/8', 'valve']):
                    available.at[i, 'PRICE'] = 2100
                elif 'motor' in name_lower:
                    available.at[i, 'PRICE'] = 2000
                elif 'sensor' in name_lower:
                    available.at[i, 'PRICE'] = 1500
                elif any(b in name_lower for b in ['board', 'pcb']):
                    available.at[i, 'PRICE'] = def_pcb

        st.success(f"**Model:** `{selected_model}` | **Capacity:** `{ton_label}`")
        st.markdown("##### 🛠️ Step 2: Select Faulty Parts (Tap category to open)")

        categories = [
            ("❄️ Evaporator Assemblies", available[available['PART_NAME'].str.contains('evap', case=False, na=False)], True),
            ("🔩 Cut-off & Service Valves", available[available['PART_NAME'].str.contains('valve', case=False, na=False)], True),
            ("⚡ Circuit Boards (PCBs)", available[available['PART_NAME'].str.contains('board|pcb', case=False, na=False)], False),
            ("🔄 Compressors", available[available['PART_NAME'].str.contains('compressor', case=False, na=False)], True),
            ("🔌 Motors & Temperature Sensors", available[available['PART_NAME'].str.contains('motor|sensor', case=False, na=False)], False),
            ("📦 Other Historical Parts", available[~available['PART_NAME'].str.contains('evap|valve|board|pcb|compressor|motor|sensor', case=False, na=False)], False)
        ]

        selected_parts = []
        parts_total = 0
        cooling_cycle_selected = False

        for cat_title, cat_data, is_cooling in categories:
            part_count = len(cat_data)
            with st.expander(f"{cat_title} ({part_count} Available)", expanded=False):
                if not cat_data.empty:
                    for _, part in cat_data.iterrows():
                        p_name = part['PART_NAME']
                        p_no = part['PART_NO']
                        p_price = int(part['PRICE'])
                        
                        checked = st.checkbox(f"{p_name} — Rs. {p_price:,}", key=f"part_{p_no}")
                        if checked:
                            selected_parts.append({'name': p_name, 'part_no': p_no, 'price': p_price})
                            parts_total += p_price
                            if is_cooling:
                                cooling_cycle_selected = True
                else:
                    st.caption("No parts logged in service history.")

        st.markdown("##### ⛽ Step 3: Overheads & Charging")
        
        col_v, col_m = st.columns(2)
        with col_v:
            inc_visit = st.checkbox("Visit Charges (Rs. 600)", value=True)
            visit_cost = 600 if inc_visit else 0
        with col_m:
            inc_mobility = st.checkbox("Mobility / Labor (Rs. 2,000)", value=True)
            mobility_cost = 2000 if inc_mobility else 0

        inc_gas = st.checkbox(f"Gas Charging ({ton_label} - Rs. {gas_charge_amount:,})", value=cooling_cycle_selected)
        gas_cost = gas_charge_amount if inc_gas else 0

        grand_total = parts_total + visit_cost + mobility_cost + gas_cost

        st.markdown("---")
        st.markdown(f"""
        <div class="bill-card">
            <div style="font-size: 0.9rem; color: #475569;">Grand Total Estimate:</div>
            <div class="grand-total">Rs. {grand_total:,}</div>
            <div style="font-size: 0.8rem; color: #64748B;">Includes Selected Parts + Gas + Overheads</div>
        </div>
        """, unsafe_allow_html=True)

        part_bullets = "\n".join([f"• {sp['name']}: Rs. {sp['price']:,}" for sp in selected_parts]) if selected_parts else "• Nil (General Service)"
        whatsapp_text = (
            f"*DWP OFFICIAL SERVICE ESTIMATE*\n"
            f"----------------------------------\n"
            f"Appliance: {selected_model} ({ton_label})\n\n"
            f"*Parts Replaced:*\n{part_bullets}\n\n"
            f"*Standard Overheads:*\n"
            f"• Technician Visit: Rs. {visit_cost:,}\n"
            f"• Mobility / Labor: Rs. {mobility_cost:,}\n"
            f"• Gas Charging ({ton_label}): Rs. {gas_cost:,}\n"
            f"----------------------------------\n"
            f"*TOTAL PAYABLE: Rs. {grand_total:,}*\n"
            f"----------------------------------\n"
            f"_DWP Authorized Customer Care_"
        )
        
        encoded_msg = urllib.parse.quote(whatsapp_text)
        wa_url = f"https://api.whatsapp.com/send?text={encoded_msg}"
        
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            st.link_button("📲 Share to WhatsApp", wa_url, use_container_width=True)
        with col_btn2:
            with st.popover("👁️ View Full Text"):
                st.code(whatsapp_text, language="text")

# ==========================================
# TAB 2: UNIT & CUSTOMER HISTORY LOOKUP
# ==========================================
with tab_history:
    st.markdown("##### 🔎 Smart Complaint & Unit Search")
    st.caption("Enter Serial No, Customer Phone, or Complaint No to fetch complete historical service logs.")

    query = st.text_input("Enter Search Key:", placeholder="e.g. A1021288DD... or 03322260552 or 282622633").strip()

    if query:
        q_clean = query.upper().replace('=', '').replace('"', '').strip()
        conn = sqlite3.connect(DB_NAME)
        
        sql = """
            SELECT * FROM history_master 
            WHERE SERIAL_CLEAN LIKE ? OR PHONE_CLEAN LIKE ? OR C_NO_CLEAN LIKE ?
            ORDER BY CLOSED_DATE DESC LIMIT 30
        """
        match_df = pd.read_sql_query(sql, conn, params=(f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%"))
        conn.close()

        if match_df.empty:
            st.warning(f"No previous closed complaints found matching `{query}`.")
        else:
            st.info(f"Found **{len(match_df)}** closed service record(s) for `{query}`:")

            for _, r in match_df.iterrows():
                c_no = r['C_NO_CLEAN']
                model = r['MODEL_CLEAN']
                serial = r['SERIAL_CLEAN']
                cust_name = r['CUSTOMER_NAME']
                phone = r['PHONE_CLEAN']
                tech = r['TECHNICIAN_NAME']
                c_type = str(r['COMPLAINT_TYPE']).strip()
                p_date = clean_val(r['PURCHASE_DATE'])
                c_date = clean_val(r['COMPLAINT_DATE'])
                closed_date = clean_val(r['CLOSED_DATE'])
                remarks = clean_val(r['REMARKS_CLEAN'])
                if not remarks or remarks.lower() == 'nan':
                    remarks = "No specific closing remarks logged."
                
                closed_amt = int(r.get('CLOSED_AMOUNT', 0))
                
                # Context-aware Amount Formatting
                if closed_amt > 0:
                    amt_display = f"Rs. {closed_amt:,}"
                elif "warranty" in c_type.lower():
                    amt_display = "Free Under Warranty"
                else:
                    amt_display = "Rs. 0 (Nil Collection)"

                badge_class = "badge-warranty"
                if "cash" in c_type.lower():
                    badge_class = "badge-cash"
                elif "partial" in c_type.lower():
                    badge_class = "badge-partial"

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

# Footer Credit
st.markdown("""
<div class="credit-footer">
    DWP Service Logistics & Operations Platform<br>
    System Architecture & Logic: <b>M. Abrar</b> | Operations Support
</div>
""", unsafe_allow_html=True)
