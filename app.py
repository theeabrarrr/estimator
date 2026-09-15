import streamlit as st
import pandas as pd
import re
import urllib.parse

# 1. Page Configuration for Mobile
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
    .credit-footer { font-size: 0.75rem; color: #94A3B8; text-align: center; margin-top: 2rem; border-top: 1px solid #E2E8F0; padding-top: 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">❄️ DWP Service Field Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Field Diagnostic, Cost Estimator & Customer Unit History Engine</div>', unsafe_allow_html=True)

# Helper function to clean Oracle text formatting
def clean_val(val):
    if pd.isna(val):
        return ""
    return str(val).strip().replace('=', '').replace('"', '').strip()

# 2. Data Loader
@st.cache_data
def load_all_datasets():
    fb = pd.read_csv("quality_feedback_report_14SEP2026_170840.csv", low_memory=False)
    coll = pd.read_excel("Detail_Collection_14SEP26_052528PM.xlsx")

    # Clean IDs for merging & search
    fb['C_NO_CLEAN'] = fb['COMPLAINT_NO'].apply(clean_val)
    fb['SERIAL_CLEAN'] = fb['SERIAL'].apply(clean_val).str.upper()
    fb['PHONE_CLEAN'] = fb['PHONE_NO'].apply(clean_val)
    fb['MODEL_CLEAN'] = fb['MODEL_NAME'].astype(str).str.strip().str.upper()
    
    coll['C_NO_CLEAN'] = coll['Complaint No'].apply(clean_val)

    # Pricing map from Col R & Col W
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
            
    parts_db = pd.DataFrame(records).drop_duplicates(subset=['MODEL', 'PART_NO'])
    model_list = sorted(fb['MODEL_CLEAN'].dropna().unique().tolist())
    return parts_db, model_list, fb

parts_df, all_models, raw_fb = load_all_datasets()

# 3. Capacity & Benchmark Rules
def get_tonnage_specs(model_str):
    m = str(model_str).upper()
    if any(x in m for x in ['12', '11', '10']):
        return '1.0 Ton', 5500, 20000, 35000
    elif any(x in m for x in ['18', '16']):
        return '1.5 Ton', 7000, 26000, 40000
    elif any(x in m for x in ['24', '26']):
        return '2.0 Ton', 8500, 39000, 45000
    elif any(x in m for x in ['48', '60']):
        return '4.0 Ton', 13000, 70000, 55000
    return '1.5 Ton', 7000, 26000, 40000

# Navigation Tabs
tab_estimator, tab_history = st.tabs(["🧮 Cost Estimator", "🔍 Unit & Customer History"])

# ==========================================
# TAB 1: ORIGINAL COST ESTIMATOR (UNTOUCHED)
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

        inc_gas = st.checkbox(f"Gas Charging ({ton_label} - Rs. {gas_charge_amount:,})", value=True if cooling_cycle_selected else False)
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
        
        # Filter matching records from raw feedback
        match_df = raw_fb[
            (raw_fb['SERIAL_CLEAN'].str.contains(q_clean, na=False, case=False)) |
            (raw_fb['PHONE_CLEAN'].str.contains(q_clean, na=False)) |
            (raw_fb['C_NO_CLEAN'].str.contains(q_clean, na=False))
        ].copy()

        if match_df.empty:
            st.warning(f"No previous closed complaints found matching `{query}`.")
        else:
            st.info(f"Found **{len(match_df)}** closed service record(s) for `{query}`:")

            # Display cards sorted by closed date descending
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
                parts_used = clean_val(r['HARDWARE_PRODUCTS'])
                if not parts_used or parts_used.lower() == 'nan':
                    parts_used = "No hardware parts logged (Service / Checking call)"

                # Badge selection
                badge_class = "badge-warranty"
                if "cash" in c_type.lower():
                    badge_class = "badge-cash"
                elif "partial" in c_type.lower():
                    badge_class = "badge-partial"

                # HTML Card
                st.markdown(f"""
                <div class="history-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 700; color: #1E293B; font-size: 1rem;">Complaint #{c_no}</span>
                        <span class="{badge_class}">{c_type}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #334155; line-height: 1.5;">
                        <b>Model:</b> {model} &nbsp;|&nbsp; <b>Serial:</b> <code>{serial}</code><br>
                        <b>Customer:</b> {cust_name} (📞 {phone})<br>
                        <b>Technician:</b> {tech}<br>
                        <b>Complaint Date:</b> {c_date} &nbsp;|&nbsp; <b>Closed Date:</b> {closed_date}<br>
                        <b>Purchase Date:</b> {p_date if p_date else 'N/A'}<br>
                        <hr style="margin: 6px 0; border: none; border-top: 1px dashed #CBD5E1;">
                        <b>Parts Replaced:</b> <span style="color: #0369A1;">{parts_used}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

# Subtle Professional Footer Credit
st.markdown("""
<div class="credit-footer">
    DWP Service Logistics & Operations Platform<br>
    System Architecture & Logic: <b>M. Abrar</b> | Operations Support
</div>
""", unsafe_allow_html=True)