# app.py
import re
import urllib.parse
from datetime import datetime
import pandas as pd
import streamlit as st

from config import VISIT_CHARGES, MOBILITY_CHARGES, get_tonnage_specs
from database import fetch_parts_and_models, search_history_records, fetch_performance_data
from etl import bootstrap_master_data, normalize_phone, ingest_performance_pipeline, ingest_feedback_and_pricing

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
    .scope-box { background-color: #F1F5F9; border: 1px solid #CBD5E1; padding: 8px 12px; border-radius: 6px; font-size: 0.82rem; color: #334155; margin-bottom: 12px; }
    .support-box { background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 12px; margin-top: 2rem; font-size: 0.82rem; color: #991B1B; text-align: center; }
    .credit-footer { font-size: 0.75rem; color: #64748B; text-align: center; margin-top: 1rem; border-top: 1px solid #E2E8F0; padding-top: 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">❄️ DWP Service Field Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Field Diagnostic, Cost Estimator, Unit History & Technician Performance Hub</div>', unsafe_allow_html=True)

@st.cache_data
def get_app_store():
    bootstrap_master_data()
    return fetch_parts_and_models()

parts_df, all_models = get_app_store()

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### 📊 Module 3: Performance Sync")
    st.caption("Dono files upload karein aur button dabayein. Yeh Estimator ya History ko touch nahi karega.")
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
                st.rerun()

tab_estimator, tab_history, tab_perf = st.tabs(["🧮 Cost Estimator", "🔍 Unit & Customer History", "📊 Technician Performance"])

# ==========================================
# TAB 1: COST ESTIMATOR
# ==========================================
with tab_estimator:
    selected_model = st.selectbox("🔍 Step 1: Select Appliance Model Number", options=["-- Search Model --"] + all_models)

    if selected_model != "-- Search Model --":
        ton_label, gas_charge_amount, def_evap, def_pcb = get_tonnage_specs(selected_model)
        fam_match = re.match(r"^([A-Z0-9]+-[0-9]{2}[A-Z]+)", selected_model)
        family_code = fam_match.group(1) if fam_match else selected_model[:7]

        direct_parts = parts_df[parts_df['model'] == selected_model] if not parts_df.empty else pd.DataFrame()
        family_parts = parts_df[parts_df['model'].str.startswith(family_code)] if not parts_df.empty else pd.DataFrame()
        available = pd.concat([direct_parts, family_parts]).drop_duplicates(subset=['part_no']).copy() if not parts_df.empty else pd.DataFrame()

        if not available.empty:
            for i, r in available.iterrows():
                if r['price'] == 0:
                    name_lower = str(r['part_name']).lower()
                    if 'evap' in name_lower:
                        available.at[i, 'price'] = def_evap
                    elif '1/4' in name_lower:
                        available.at[i, 'price'] = 1600
                    elif any(v in name_lower for v in ['1/2', '5/8', '3/8', 'valve']):
                        available.at[i, 'price'] = 2100
                    elif 'motor' in name_lower:
                        available.at[i, 'price'] = 2000
                    elif 'sensor' in name_lower:
                        available.at[i, 'price'] = 1500
                    elif any(b in name_lower for b in ['board', 'pcb']):
                        available.at[i, 'price'] = def_pcb

        st.success(f"**Model:** `{selected_model}` | **Capacity:** `{ton_label}`")
        st.markdown("##### 🛠️ Step 2: Select Faulty Parts (Tap karke open karein)")

        categories = [
            ("❄️ Evaporator Assemblies", available[available['part_name'].str.contains('evap', case=False, na=False)], True),
            ("🔩 Cut-off & Service Valves", available[available['part_name'].str.contains('valve', case=False, na=False)], True),
            ("⚡ Circuit Boards (PCBs)", available[available['part_name'].str.contains('board|pcb', case=False, na=False)], False),
            ("🔄 Compressors", available[available['part_name'].str.contains('compressor', case=False, na=False)], True),
            ("🔌 Motors & Temperature Sensors", available[available['part_name'].str.contains('motor|sensor', case=False, na=False)], False),
            ("📦 Other Historical Parts", available[~available['part_name'].str.contains('evap|valve|board|pcb|compressor|motor|sensor', case=False, na=False)], False)
        ] if not available.empty else []

        selected_parts = []
        parts_total = 0
        cooling_cycle_selected = False

        for cat_title, cat_data, is_cooling in categories:
            part_count = len(cat_data)
            with st.expander(f"{cat_title} ({part_count} Available)", expanded=False):
                if not cat_data.empty:
                    for _, part in cat_data.iterrows():
                        p_name = part['part_name']
                        p_no = part['part_no']
                        p_price = int(part['price'])
                        checked = st.checkbox(f"{p_name} — Rs. {p_price:,}", key=f"part_{p_no}")
                        if checked:
                            selected_parts.append({'name': p_name, 'part_no': p_no, 'price': p_price})
                            parts_total += p_price
                            if is_cooling:
                                cooling_cycle_selected = True
                else:
                    st.caption("Service history mein koi part logged nahi mila.")

        st.markdown("##### ⛽ Step 3: Overheads & Charging")
        col_v, col_m = st.columns(2)
        with col_v:
            inc_visit = st.checkbox(f"Visit Charges (Rs. {VISIT_CHARGES:,})", value=True)
            visit_cost = VISIT_CHARGES if inc_visit else 0
        with col_m:
            inc_mobility = st.checkbox(f"Mobility / Labor Charges (Rs. {MOBILITY_CHARGES:,})", value=True)
            mobility_cost = MOBILITY_CHARGES if inc_mobility else 0

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

        part_bullets = "\n".join([f"• {sp['name']}: Rs. {sp['price']:,}" for sp in selected_parts]) if selected_parts else "• Nil (General Service / Checking)"
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