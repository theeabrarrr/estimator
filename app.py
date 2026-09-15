import os
import re
import sqlite3
import urllib.parse
import pandas as pd
import streamlit as st

DB_NAME = "dwp_service.db"
DEFAULT_FB_FILE = "quality_feedback_report_14SEP2026_170840.csv"
DEFAULT_COLL_FILE = "Detail_Collection_14SEP26_052528PM.xlsx"

st.set_page_config(
    page_title="DWP Field Assistant",
    page_icon="❄️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Custom Styling
st.markdown(
    """
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
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-title">❄️ DWP Service Field Assistant</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">Field Diagnostic, Cost Estimator & Customer Unit'
    " History Engine</div>",
    unsafe_allow_html=True,
)


def clean_val(val):
  if pd.isna(val):
    return ""
  return str(val).strip().replace("=", "").replace('"', "").strip()


# =========================================================
# EXACT ORIGINAL PRICING & PARTS EXTRACTION LOGIC
# =========================================================
def build_parts_catalog(fb_df, coll_df):
  fb = fb_df.copy()
  coll = coll_df.copy()

  fb["C_NO_CLEAN"] = fb["COMPLAINT_NO"].apply(clean_val)
  fb["SERIAL_CLEAN"] = fb["SERIAL"].apply(clean_val).str.upper()
  fb["PHONE_CLEAN"] = fb["PHONE_NO"].apply(clean_val)
  fb["MODEL_CLEAN"] = fb["MODEL_NAME"].astype(str).str.strip().str.upper()

  coll["C_NO_CLEAN"] = coll["Complaint No"].apply(clean_val)
  coll["EFFECTIVE_PART_PRICE"] = coll["Part Cash"].where(
      coll["Part Cash"] > 0, coll["Part Warranty"]
  )
  coll_sub = coll[coll["EFFECTIVE_PART_PRICE"] > 0][
      ["C_NO_CLEAN", "EFFECTIVE_PART_PRICE"]
  ]
  merged = pd.merge(fb, coll_sub, on="C_NO_CLEAN", how="inner")

  single_jobs = merged[
      ~merged["HARDWARE_PART_NOS"].str.contains(",", na=False)
  ].copy()
  single_jobs["PART_NO"] = single_jobs["HARDWARE_PART_NOS"].str.strip()

  exact_price_map = (
      single_jobs.groupby("PART_NO")["EFFECTIVE_PART_PRICE"]
      .agg(lambda x: x.mode()[0] if not x.mode().empty else x.median())
      .to_dict()
  )

  records = []
  for _, row in fb.iterrows():
    pnos = str(row["HARDWARE_PART_NOS"])
    prods = str(row["HARDWARE_PRODUCTS"])
    if (
        pd.isna(row["HARDWARE_PART_NOS"])
        or pnos.lower() == "nan"
        or not pnos.strip()
    ):
      continue
    pno_list = [p.strip() for p in pnos.split(",") if p.strip()]
    prod_list = [p.strip() for p in prods.split(",") if p.strip()]
    for i, pno in enumerate(pno_list):
      pname = (
          prod_list[i]
          if i < len(prod_list)
          else (prod_list[0] if prod_list else "Component")
      )
      price = int(exact_price_map.get(pno, 0))
      records.append({
          "MODEL": row["MODEL_CLEAN"],
          "PART_NO": pno,
          "PART_NAME": pname,
          "PRICE": price,
      })

  parts_df = pd.DataFrame(records).drop_duplicates(subset=["MODEL", "PART_NO"])
  return parts_df, fb


# =========================================================
# DATABASE BOOTSTRAP & SYNC
# =========================================================
def sync_to_sqlite(parts_df, fb_df):
  conn = sqlite3.connect(DB_NAME)

  # Complaints Master
  fb_to_save = fb_df[[
      "C_NO_CLEAN",
      "SERIAL_CLEAN",
      "PHONE_CLEAN",
      "MODEL_CLEAN",
      "CUSTOMER_NAME",
      "TECHNICIAN_NAME",
      "COMPLAINT_TYPE",
      "PURCHASE_DATE",
      "COMPLAINT_DATE",
      "CLOSED_DATE",
      "HARDWARE_PRODUCTS",
  ]].copy()

  fb_to_save.columns = [
      "c_no",
      "serial",
      "phone",
      "model",
      "customer_name",
      "technician_name",
      "complaint_type",
      "purchase_date",
      "complaint_date",
      "closed_date",
      "hardware_products",
  ]

  fb_to_save.to_sql(
      "complaints_master", conn, if_exists="replace", index=False
  )

  # Parts Catalog
  parts_to_save = parts_df.copy()
  parts_to_save.columns = ["model", "part_no", "part_name", "price"]
  parts_to_save.to_sql("parts_catalog", conn, if_exists="replace", index=False)

  # Create Search Indexes
  c = conn.cursor()
  c.execute(
      "CREATE INDEX IF NOT EXISTS idx_search_keys ON"
      " complaints_master(serial, phone, c_no)"
  )
  c.execute(
      "CREATE INDEX IF NOT EXISTS idx_parts_model ON parts_catalog(model)"
  )
  conn.commit()
  conn.close()


@st.cache_data
def load_app_data():
  # Agar SQLite DB nahi hai ya empty hai, toh base files se create karein
  if not os.path.exists(DB_NAME):
    if os.path.exists(DEFAULT_FB_FILE) and os.path.exists(DEFAULT_COLL_FILE):
      fb_df = pd.read_csv(DEFAULT_FB_FILE, low_memory=False)
      coll_df = pd.read_excel(DEFAULT_COLL_FILE)
      parts_df, fb_df = build_parts_catalog(fb_df, coll_df)
      sync_to_sqlite(parts_df, fb_df)

  conn = sqlite3.connect(DB_NAME)
  parts_df = pd.read_sql_query("SELECT * FROM parts_catalog", conn)
  models = pd.read_sql_query(
      "SELECT DISTINCT model FROM complaints_master WHERE model != '' ORDER BY"
      " model ASC",
      conn,
  )["model"].tolist()
  conn.close()
  return parts_df, models


parts_df, all_models = load_app_data()


# =========================================================
# SIDEBAR: DATA UPDATE & DAILY UPLOAD
# =========================================================
with st.sidebar:
  st.subheader("⚙️ Data Sync Center")
  st.caption("Upload daily fresh ERP report to append or update records.")

  up_fb = st.file_uploader(
      "1. Quality Feedback (CSV/Excel)",
      type=["csv", "xlsx", "xls"],
      key="fb_up",
  )
  up_coll = st.file_uploader(
      "2. Collection Pricing (Excel)", type=["xlsx", "xls"], key="coll_up"
  )

  if up_fb and up_coll:
    if st.button("Sync & Update Complete System"):
      with st.spinner("Processing & updating database..."):
        df_fb_new = (
            pd.read_csv(up_fb, low_memory=False)
            if up_fb.name.endswith(".csv")
            else pd.read_excel(up_fb)
        )
        df_coll_new = pd.read_excel(up_coll)
        new_parts_df, new_fb_df = build_parts_catalog(df_fb_new, df_coll_new)
        sync_to_sqlite(new_parts_df, new_fb_df)
        st.cache_data.clear()
        st.success("Database fully synchronized!")
        st.rerun()


# =========================================================
# TONNAGE & BENCHMARK RULES
# =========================================================
def get_tonnage_specs(model_str):
  m = str(model_str).upper()
  if any(x in m for x in ["12", "11", "10"]):
    return "1.0 Ton", 5500, 20000, 35000
  elif any(x in m for x in ["18", "16"]):
    return "1.5 Ton", 7000, 26000, 40000
  elif any(x in m for x in ["24", "26"]):
    return "2.0 Ton", 8500, 39000, 45000
  elif any(x in m for x in ["48", "60"]):
    return "4.0 Ton", 13000, 70000, 55000
  return "1.5 Ton", 7000, 26000, 40000


# UI Tabs
tab_estimator, tab_history = st.tabs(
    ["🧮 Cost Estimator", "🔍 Unit & Customer History"]
)

# ==========================================
# TAB 1: ORIGINAL COST ESTIMATOR LOGIC
# ==========================================
with tab_estimator:
  selected_model = st.selectbox(
      "🔍 Step 1: Select Appliance Model Number",
      options=["-- Search Model --"] + all_models,
  )

  if selected_model != "-- Search Model --":
    ton_label, gas_charge_amount, def_evap, def_pcb = get_tonnage_specs(
        selected_model
    )

    fam_match = re.match(r"^([A-Z0-9]+-[0-9]{2}[A-Z]+)", selected_model)
    family_code = fam_match.group(1) if fam_match else selected_model[:7]

    direct_parts = parts_df[parts_df["model"] == selected_model]
    family_parts = parts_df[parts_df["model"].str.startswith(family_code)]
    available = (
        pd.concat([direct_parts, family_parts])
        .drop_duplicates(subset=["part_no"])
        .copy()
    )

    for i, r in available.iterrows():
      if r["price"] == 0:
        name_lower = str(r["part_name"]).lower()
        if "evap" in name_lower:
          available.at[i, "price"] = def_evap
        elif "1/4" in name_lower:
          available.at[i, "price"] = 1600
        elif any(v in name_lower for v in ["1/2", "5/8", "3/8", "valve"]):
          available.at[i, "price"] = 2100
        elif "motor" in name_lower:
          available.at[i, "price"] = 2000
        elif "sensor" in name_lower:
          available.at[i, "price"] = 1500
        elif any(b in name_lower for b in ["board", "pcb"]):
          available.at[i, "price"] = def_pcb

    st.success(f"**Model:** `{selected_model}` | **Capacity:** `{ton_label}`")
    st.markdown("##### 🛠️ Step 2: Select Faulty Parts (Tap category to open)")

    categories = [
        (
            "❄️ Evaporator Assemblies",
            available[
                available["part_name"].str.contains("evap", case=False, na=False)
            ],
            True,
        ),
        (
            "🔩 Cut-off & Service Valves",
            available[
                available["part_name"].str.contains(
                    "valve", case=False, na=False
                )
            ],
            True,
        ),
        (
            "⚡ Circuit Boards (PCBs)",
            available[
                available["part_name"].str.contains(
                    "board|pcb", case=False, na=False
                )
            ],
            False,
        ),
        (
            "🔄 Compressors",
            available[
                available["part_name"].str.contains(
                    "compressor", case=False, na=False
                )
            ],
            True,
        ),
        (
            "🔌 Motors & Temperature Sensors",
            available[
                available["part_name"].str.contains(
                    "motor|sensor", case=False, na=False
                )
            ],
            False,
        ),
        (
            "📦 Other Historical Parts",
            available[
                ~available["part_name"].str.contains(
                    "evap|valve|board|pcb|compressor|motor|sensor",
                    case=False,
                    na=False,
                )
            ],
            False,
        ),
    ]

    selected_parts = []
    parts_total = 0
    cooling_cycle_selected = False

    for cat_title, cat_data, is_cooling in categories:
      part_count = len(cat_data)
      with st.expander(f"{cat_title} ({part_count} Available)", expanded=False):
        if not cat_data.empty:
          for _, part in cat_data.iterrows():
            p_name = part["part_name"]
            p_no = part["part_no"]
            p_price = int(part["price"])

            checked = st.checkbox(
                f"{p_name} — Rs. {p_price:,}", key=f"part_{p_no}"
            )
            if checked:
              selected_parts.append(
                  {"name": p_name, "part_no": p_no, "price": p_price}
              )
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
      inc_mobility = st.checkbox(
          "Mobility / Labor (Rs. 2,000)", value=True
      )
      mobility_cost = 2000 if inc_mobility else 0

    inc_gas = st.checkbox(
        f"Gas Charging ({ton_label} - Rs. {gas_charge_amount:,})",
        value=cooling_cycle_selected,
    )
    gas_cost = gas_charge_amount if inc_gas else 0

    grand_total = parts_total + visit_cost + mobility_cost + gas_cost

    st.markdown("---")
    st.markdown(
        f"""
    <div class="bill-card">
        <div style="font-size: 0.9rem; color: #475569;">Grand Total Estimate:</div>
        <div class="grand-total">Rs. {grand_total:,}</div>
        <div style="font-size: 0.8rem; color: #64748B;">Includes Selected Parts + Gas + Overheads</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    part_bullets = (
        "\n".join(
            [f"• {sp['name']}: Rs. {sp['price']:,}" for sp in selected_parts]
        )
        if selected_parts
        else "• Nil (General Service)"
    )
    whatsapp_text = (
        "*DWP OFFICIAL SERVICE ESTIMATE*\n"
        "----------------------------------\n"
        f"Appliance: {selected_model} ({ton_label})\n\n"
        f"*Parts Replaced:*\n{part_bullets}\n\n"
        "*Standard Overheads:*\n"
        f"• Technician Visit: Rs. {visit_cost:,}\n"
        f"• Mobility / Labor: Rs. {mobility_cost:,}\n"
        f"• Gas Charging ({ton_label}): Rs. {gas_cost:,}\n"
        "----------------------------------\n"
        f"*TOTAL PAYABLE: Rs. {grand_total:,}*\n"
        "----------------------------------\n"
        "_DWP Authorized Customer Care_"
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
# TAB 2: FAST SQL UNIT & CUSTOMER HISTORY
# ==========================================
with tab_history:
  st.markdown("##### 🔎 Smart Complaint & Unit Search")
  st.caption(
      "Enter Serial No, Customer Phone, or Complaint No to fetch complete"
      " historical service logs."
  )

  query = st.text_input(
      "Enter Search Key:",
      placeholder="e.g. A1021288DD... or 03322260552 or 282622633",
  ).strip()

  if query:
    q_clean = query.upper().replace("=", "").replace('"', "").strip()
    conn = sqlite3.connect(DB_NAME)

    sql_search = """
        SELECT c_no, serial, phone, model, customer_name, technician_name,
               complaint_type, purchase_date, complaint_date, closed_date, hardware_products
        FROM complaints_master
        WHERE serial LIKE ? OR phone LIKE ? OR c_no LIKE ?
        ORDER BY closed_date DESC LIMIT 25
    """
    match_df = pd.read_sql_query(
        sql_search,
        conn,
        params=(f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%"),
    )
    conn.close()

    if match_df.empty:
      st.warning(f"No previous closed complaints found matching `{query}`.")
    else:
      st.info(
          f"Found **{len(match_df)}** closed service record(s) for `{query}`:"
      )

      for _, r in match_df.iterrows():
        c_no = r["c_no"]
        model = r["model"]
        serial = r["serial"]
        cust_name = r["customer_name"]
        phone = r["phone"]
        tech = r["technician_name"]
        c_type = str(r["complaint_type"]).strip()
        p_date = clean_val(r["purchase_date"])
        c_date = clean_val(r["complaint_date"])
        closed_date = clean_val(r["closed_date"])
        parts_used = clean_val(r["hardware_products"])
        if not parts_used or parts_used.lower() == "nan":
          parts_used = "No hardware parts logged (Service / Checking call)"

        badge_class = "badge-warranty"
        if "cash" in c_type.lower():
          badge_class = "badge-cash"
        elif "partial" in c_type.lower():
          badge_class = "badge-partial"

        st.markdown(
            f"""
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
            """,
            unsafe_allow_html=True,
        )

# Footer Credit
st.markdown(
    """
<div class="credit-footer">
    DWP Service Logistics & Operations Platform<br>
    System Architecture & Logic: <b>M. Abrar</b> | Operations Support
</div>
""",
    unsafe_allow_html=True,
)
