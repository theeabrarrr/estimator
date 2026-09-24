# app.py
import re
import urllib.parse
from datetime import datetime
import pandas as pd
import streamlit as st

from config import VISIT_CHARGES, MOBILITY_CHARGES, CATEGORY_OVERHEADS, get_tonnage_specs, detect_appliance_category
from database import (
    fetch_parts_and_models, search_history_records, fetch_performance_data,
    fetch_parts_with_live_stock, search_stock_global, get_stock_metadata
)
from etl import (
    bootstrap_master_data, normalize_phone, ingest_performance_pipeline,
    ingest_feedback_and_pricing, ingest_stock_file
)

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
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">❄️ DWP Service Field Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Field Diagnostic, Cost & Live Stock Estimator, History & KPI Hub</div>', unsafe_allow_html=True)

# Initialize Session State for Cart
if "cart_items" not in st.session_state:
    st.session_state.cart_items = {}

@st.cache_data
def get_app_store():
    bootstrap_master_data()
    return fetch_parts_and_models()

parts_df, all_models = get_app_store()
stock_meta = get_stock_metadata()

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### 📦 Module 4: Live Stock Sync")
    if stock_meta['total_items'] > 0:
        st.markdown(f"""
        <div style="background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 6px; padding: 8px; font-size: 0.8rem; color: #166534; margin-bottom: 10px;">
            <b>Live Warehouse Stock Active:</b><br>
            • Total Items: <b>{stock_meta['total_items']:,}</b><br>
            • In Stock: <b>{stock_meta['in_stock_items']:,}</b><br>
            • Last Synced: <code>{stock_meta['last_synced']}</code>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("Stock data abhi load nahi hai. Nayi CSV/Excel file upload karein.")

    p_stock = st.file_uploader("Stock Detail File (.csv / .xls)", type=["csv", "xlsx", "xls"], key="p_stock")
    if st.button("🔄 Sync Live Stock Now", use_container_width=True):
        if p_stock:
            with st.spinner("Syncing warehouse stock..."):
                tot, in_stk = ingest_stock_file(p_stock)
                st.cache_data.clear()
                st.success(f"Stock Updated! {tot} items loaded ({in_stk} in stock).")
                st.rerun()
        else:
            st.error("Stock Detail file lazmi choose karein!")

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
                st.rerun()

tab_estimator, tab_history, tab_perf = st.tabs(["🧮 Cost & Stock Estimator", "🔍 Unit & Customer History", "📊 Technician Performance"])

# ==========================================
# TAB 1: COST & STOCK ESTIMATOR
# ==========================================
with tab_estimator:
    # Top Stock Status bar
    if stock_meta['total_items'] > 0:
        st.caption(f"🟢 **Warehouse Stock Connected:** {stock_meta['in_stock_items']:,} parts available in Karachi store (Updated: {stock_meta['last_synced']})")

    # Search Mode Selection
    search_mode = st.radio(
        "🔎 Part Dhoondnay Ka Tareeqa:",
        ["Model Number Se Search Karein", "Direct Part Name / Part No Se Search Karein"],
        horizontal=True
    )

    detected_category = "Split AC"
    ton_label = "1.5 Ton"
    gas_charge_amount = 7000

    if search_mode == "Model Number Se Search Karein":
        selected_model = st.selectbox("1. Appliance Model Select Karein:", options=["-- Search Model --"] + all_models)

        if selected_model != "-- Search Model --":
            ton_label, gas_charge_amount, def_evap, def_pcb, detected_category = get_tonnage_specs(selected_model)
            overheads = CATEGORY_OVERHEADS.get(detected_category, CATEGORY_OVERHEADS['General'])

            st.info(f"**Appliance:** `{selected_model}` &nbsp;|&nbsp; **Category:** `{detected_category}` &nbsp;|&nbsp; **Spec:** `{ton_label}`")

            # Fetch live parts with stock
            available = fetch_parts_with_live_stock(selected_model)

            if available.empty:
                st.warning("Is model ke compatible parts store list mein nahi milay. Aap neeche 'Direct Part Search' se part dhoond kar add kar saktay hain.")
            else:
                # Apply fallback heuristics if price is still 0
                for i, r in available.iterrows():
                    if r['price'] == 0:
                        nl = str(r['part_name']).lower()
                        if 'evap' in nl:
                            available.at[i, 'price'] = def_evap
                        elif '1/4' in nl:
                            available.at[i, 'price'] = 1600
                        elif any(v in nl for v in ['1/2', '5/8', '3/8', 'valve']):
                            available.at[i, 'price'] = 2100
                        elif 'motor' in nl:
                            available.at[i, 'price'] = 2000
                        elif 'sensor' in nl:
                            available.at[i, 'price'] = 1500
                        elif any(b in nl for b in ['board', 'pcb']):
                            available.at[i, 'price'] = def_pcb

                st.markdown("##### 🛠️ Step 2: Faulty Parts & Live Stock (Select to Add)")

                # Categorized breakdown
                part_cats = [
                    ("❄️ Evaporator Assemblies", available[available['part_name'].str.contains('evap', case=False, na=False)]),
                    ("🔩 Valves & Tubing", available[available['part_name'].str.contains('valve', case=False, na=False)]),
                    ("⚡ Circuit Boards (PCBs)", available[available['part_name'].str.contains('board|pcb', case=False, na=False)]),
                    ("🔄 Compressors", available[available['part_name'].str.contains('compressor', case=False, na=False)]),
                    ("🔌 Motors & Sensors", available[available['part_name'].str.contains('motor|sensor', case=False, na=False)]),
                    ("📦 Other Parts", available[~available['part_name'].str.contains('evap|valve|board|pcb|compressor|motor|sensor', case=False, na=False)])
                ]

                for cat_title, cat_data in part_cats:
                    if cat_data.empty:
                        continue
                    in_stk_in_cat = (cat_data['bal_qty'] > 0).sum()
                    with st.expander(f"{cat_title} ({len(cat_data)} Total | {in_stk_in_cat} In Stock)", expanded=(cat_title.startswith("❄️") or cat_title.startswith("⚡"))):
                        for _, part in cat_data.iterrows():
                            p_no = part['part_no']
                            p_name = part['part_name']
                            p_price = int(part['price'])
                            p_qty = int(part['bal_qty'])

                            if p_qty > 2:
                                badge_html = f'<span class="stock-badge-in">🟢 In Stock ({p_qty} pcs)</span>'
                            elif p_qty > 0:
                                badge_html = f'<span class="stock-badge-low">🟡 Low Stock ({p_qty} left)</span>'
                            else:
                                badge_html = '<span class="stock-badge-out">🔴 Out of Stock / NIL</span>'

                            col_p1, col_p2, col_p3 = st.columns([6, 2, 2])
                            with col_p1:
                                st.markdown(f"<b>{p_name}</b><br><small style='color:#64748B;'>Code: <code>{p_no}</code> &nbsp;|&nbsp; {badge_html}</small>", unsafe_allow_html=True)
                            with col_p2:
                                st.markdown(f"<span style='font-weight:700; color:#1E3A8A;'>Rs. {p_price:,}</span>", unsafe_allow_html=True)
                            with col_p3:
                                in_cart = p_no in st.session_state.cart_items
                                if in_cart:
                                    if st.button("❌ Remove", key=f"btn_rem_{p_no}", use_container_width=True):
                                        del st.session_state.cart_items[p_no]
                                        st.rerun()
                                else:
                                    if st.button("➕ Add", key=f"btn_add_{p_no}", use_container_width=True):
                                        st.session_state.cart_items[p_no] = {
                                            'name': p_name,
                                            'part_no': p_no,
                                            'price': p_price,
                                            'qty': 1,
                                            'bal_qty': p_qty
                                        }
                                        st.rerun()
                            st.divider()

    else:
        # Direct Part Search
        st.markdown("##### ⚡ Instant Store Inventory Search")
        st.caption("Part Number, Description, ya Model likhein (e.g., `1521210712`, `Main Board`, `Evaporator`, `Sensor`):")
        q_part = st.text_input("Search Keyword:", placeholder="Enter Part Code or Description...").strip()

        if q_part:
            results = search_stock_global(q_part)
            if results.empty:
                st.warning(f"`{q_part}` ke mutabiq koi part stock list mein nahi mila.")
            else:
                st.info(f"**{len(results)}** item(s) milay hain:")
                for _, part in results.iterrows():
                    p_no = part['part_no']
                    p_name = part['part_name']
                    p_price = int(part['price'])
                    p_qty = int(part['bal_qty'])
                    p_cat = part['category']

                    if p_qty > 2:
                        badge_html = f'<span class="stock-badge-in">🟢 In Stock ({p_qty} pcs)</span>'
                    elif p_qty > 0:
                        badge_html = f'<span class="stock-badge-low">🟡 Low Stock ({p_qty} left)</span>'
                    else:
                        badge_html = '<span class="stock-badge-out">🔴 Out of Stock / NIL</span>'

                    col_r1, col_r2, col_r3 = st.columns([6, 2, 2])
                    with col_r1:
                        st.markdown(f"<b>{p_name}</b><br><small style='color:#64748B;'>Code: <code>{p_no}</code> | Cat: {p_cat} | {badge_html}</small>", unsafe_allow_html=True)
                    with col_r2:
                        st.markdown(f"<span style='font-weight:700; color:#1E3A8A;'>Rs. {p_price:,}</span>", unsafe_allow_html=True)
                    with col_r3:
                        in_cart = p_no in st.session_state.cart_items
                        if in_cart:
                            if st.button("❌ Remove", key=f"s_rem_{p_no}", use_container_width=True):
                                del st.session_state.cart_items[p_no]
                                st.rerun()
                        else:
                            if st.button("➕ Add", key=f"s_add_{p_no}", use_container_width=True):
                                st.session_state.cart_items[p_no] = {
                                    'name': p_name,
                                    'part_no': p_no,
                                    'price': p_price,
                                    'qty': 1,
                                    'bal_qty': p_qty
                                }
                                st.rerun()
                    st.divider()

    # ==========================================
    # ESTIMATE BASKET & OVERHEADS SECTION
    # ==========================================
    st.markdown("---")
    st.markdown("### 🛒 Estimate Basket (Selected Items)")

    has_cooling_part = False
    has_out_of_stock = False

    if not st.session_state.cart_items:
        st.info("Basket khali hai. Upar se parts add karein ya general service / visit estimate banayein.")
    else:
        # Display selected items with quantity controls
        for p_no, item in list(st.session_state.cart_items.items()):
            nl = item['name'].lower()
            if any(k in nl for k in ['evap', 'valve', 'compressor']):
                has_cooling_part = True
            if item['bal_qty'] <= 0:
                has_out_of_stock = True

            col_c1, col_c2, col_c3, col_c4 = st.columns([5, 2, 2, 1])
            with col_c1:
                st.markdown(f"**{item['name']}**<br><small style='color:#64748B;'>Code: <code>{p_no}</code> &nbsp;|&nbsp; Stock: {item['bal_qty']} pcs</small>", unsafe_allow_html=True)
            with col_c2:
                q = st.number_input("Qty", min_value=1, max_value=20, value=item['qty'], key=f"qty_{p_no}", label_visibility="collapsed")
                st.session_state.cart_items[p_no]['qty'] = q
            with col_c3:
                line_total = item['price'] * q
                st.markdown(f"<span style='font-weight:700;'>Rs. {line_total:,}</span>", unsafe_allow_html=True)
            with col_c4:
                if st.button("🗑️", key=f"del_{p_no}"):
                    del st.session_state.cart_items[p_no]
                    st.rerun()

        if st.button("🧹 Clear All Items"):
            st.session_state.cart_items = {}
            st.rerun()

    # Out of stock warning banner
    if has_out_of_stock:
        st.warning("⚠️ **Stock Warning:** Aapki basket mein selected part(s) branch store mein **OUT OF STOCK / NIL** hain. Customer ko part arrival ka time inform karein.")

    # Overheads & Service Section
    st.markdown("##### ⛽ Service & Labor Overheads")
    overheads = CATEGORY_OVERHEADS.get(detected_category, CATEGORY_OVERHEADS['General'])

    col_v, col_m = st.columns(2)
    with col_v:
        inc_visit = st.checkbox(f"Technician Visit Charges (Rs. {overheads['visit']:,})", value=True)
        visit_cost = overheads['visit'] if inc_visit else 0
    with col_m:
        inc_mobility = st.checkbox(f"Mobility / Labor Charges (Rs. {overheads['mobility']:,})", value=True)
        mobility_cost = overheads['mobility'] if inc_mobility else 0

    gas_cost = 0
    if overheads.get('has_gas', False):
        default_gas_price = gas_charge_amount if detected_category in ['Split AC', 'Floor Standing AC'] else overheads.get('gas_default', 3500)
        inc_gas = st.checkbox(f"Gas Charging / Sealed System ({ton_label} - Rs. {default_gas_price:,})", value=has_cooling_part)
        gas_cost = default_gas_price if inc_gas else 0

    # Custom Miscellaneous Charges (e.g. extra piping / bracket)
    with st.expander("➕ Additional Misc Charges (Optional)"):
        misc_desc = st.text_input("Misc Item Description:", placeholder="e.g. Extra 10ft Copper Piping / AC Bracket")
        misc_amt = st.number_input("Misc Amount (Rs.):", min_value=0, step=500, value=0)

    # Totals Calculation
    parts_subtotal = sum(item['price'] * item['qty'] for item in st.session_state.cart_items.values())
    grand_total = parts_subtotal + visit_cost + mobility_cost + gas_cost + misc_amt

    # Bill Summary Display
    st.markdown("---")
    st.markdown(f"""
    <div class="bill-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-size: 0.9rem; color: #475569;">Grand Total Estimate:</div>
                <div class="grand-total">Rs. {grand_total:,}</div>
            </div>
            <div style="text-align: right; font-size: 0.8rem; color: #64748B;">
                Parts: Rs. {parts_subtotal:,}<br>
                Overheads: Rs. {(visit_cost + mobility_cost + gas_cost + misc_amt):,}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # WhatsApp Message Builder
    part_bullets_list = []
    if st.session_state.cart_items:
        for it in st.session_state.cart_items.values():
            stk_str = f"In Stock: {it['bal_qty']} pcs" if it['bal_qty'] > 0 else "NIL (Out of Stock)"
            part_bullets_list.append(f"• {it['name']} (Qty: {it['qty']}) — Rs. {it['price'] * it['qty']:,} [{stk_str}]")
        part_bullets = "\n".join(part_bullets_list)
    else:
        part_bullets = "• Nil (General Checking / Service Only)"

    misc_bullet = f"• Misc / Extra: {misc_desc} — Rs. {misc_amt:,}\n" if misc_amt > 0 else ""
    gas_bullet = f"• Gas Charging ({ton_label}): Rs. {gas_cost:,}\n" if gas_cost > 0 else ""

    whatsapp_text = (
        f"*DWP OFFICIAL SERVICE & PARTS ESTIMATE*\n"
        f"-----------------------------------\n"
        f"Appliance: {ton_label} ({detected_category})\n\n"
        f"*Parts & Stock Availability:*\n{part_bullets}\n\n"
        f"*Service & Standard Overheads:*\n"
        f"• Technician Visit: Rs. {visit_cost:,}\n"
        f"• Mobility / Labor: Rs. {mobility_cost:,}\n"
        f"{gas_bullet}{misc_bullet}"
        f"-----------------------------------\n"
        f"*TOTAL ESTIMATE: Rs. {grand_total:,}*\n"
        f"-----------------------------------\n"
        f"_DWP Authorized Customer Care_"
    )

    encoded_msg = urllib.parse.quote(whatsapp_text)
    wa_url = f"https://api.whatsapp.com/send?text={encoded_msg}"

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        st.link_button("📲 Share Estimate to WhatsApp", wa_url, use_container_width=True)
    with col_btn2:
        with st.popover("👁️ View Full Text Quotation"):
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