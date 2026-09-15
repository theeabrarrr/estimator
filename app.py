import os
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
# FAST BULK INGESTION LOGIC
# =========================================================
def ingest_feedback_fast(df):
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()

  # Clean values
  df["c_no"] = df["COMPLAINT_NO"].apply(clean_val)
  df["serial"] = df["SERIAL"].apply(clean_val).str.upper()
  df["phone"] = df["PHONE_NO"].apply(clean_val)
  df["model"] = df["MODEL_NAME"].astype(str).str.strip().str.upper()
  df["customer_name"] = df.get(
      "CUSTOMER_NAME", pd.Series([""] * len(df))
  ).apply(clean_val)
  df["technician_name"] = df.get(
      "TECHNICIAN_NAME", pd.Series([""] * len(df))
  ).apply(clean_val)
  df["complaint_type"] = df.get(
      "COMPLAINT_TYPE", pd.Series([""] * len(df))
  ).apply(clean_val)
  df["purchase_date"] = df.get(
      "PURCHASE_DATE", pd.Series([""] * len(df))
  ).apply(clean_val)
  df["complaint_date"] = df.get(
      "COMPLAINT_DATE", pd.Series([""] * len(df))
  ).apply(clean_val)
  df["closed_date"] = df.get("CLOSED_DATE", pd.Series([""] * len(df))).apply(
      clean_val
  )
  df["hardware_products"] = df.get(
      "HARDWARE_PRODUCTS", pd.Series([""] * len(df))
  ).apply(clean_val)
  df["hardware_part_nos"] = df.get(
      "HARDWARE_PART_NOS", pd.Series([""] * len(df))
  ).apply(clean_val)

  # Filter empty complaint numbers
  valid_df = df[df["c_no"] != ""][
      [
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
          "hardware_part_nos",
      ]
  ]

  records = valid_df.values.tolist()

  # Ultra fast C-level Bulk Upsert
  c.executemany(
      """
        INSERT OR REPLACE INTO complaints_master (
            c_no, serial, phone, model, customer_name, technician_name,
            complaint_type, purchase_date, complaint_date, closed_date,
            hardware_products, hardware_part_nos
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      records,
  )

  conn.commit()
  conn.close()
  return len(records)


def ingest_pricing_fast(coll_df):
  conn = sqlite3.connect(DB_NAME)
  coll_df["C_NO_CLEAN"] = coll_df["Complaint No"].apply(clean_val)
  coll_df["EFFECTIVE_PART_PRICE"] = coll_df["Part Cash"].where(
      coll_df["Part Cash"] > 0, coll_df["Part Warranty"]
  )
  coll_sub = coll_df[coll_df["EFFECTIVE_PART_PRICE"] > 0][
      ["C_NO_CLEAN", "EFFECTIVE_PART_PRICE"]
  ]

  fb = pd.read_sql_query(
      "SELECT c_no, model, hardware_part_nos, hardware_products FROM"
      " complaints_master",
      conn,
  )
  if fb.empty:
    conn.close()
    return 0

  merged = pd.merge(
      fb, coll_sub, left_on="c_no", right_on="C_NO_CLEAN", how="inner"
  )
  single_jobs = merged[
      ~merged["hardware_part_nos"].str.contains(",", na=False)
  ].copy()
  single_jobs["PART_NO"] = single_jobs["hardware_part_nos"].str.strip()

  exact_price_map = (
      single_jobs.groupby("PART_NO")["EFFECTIVE_PART_PRICE"]
      .agg(lambda x: x.mode()[0] if not x.mode().empty else x.median())
      .to_dict()
  )

  part_rows = []
  for _, row in fb.iterrows():
    pnos = str(row["hardware_part_nos"])
    prods = str(row["hardware_products"])
    if not pnos or pnos.lower() == "nan":
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
      part_rows.append((row["model"], pno, pname, price))

  c = conn.cursor()
  c.executemany(
      """
        INSERT OR REPLACE INTO parts_catalog (model, part_no, part_name, price)
        VALUES (?, ?, ?, ?)
    """,
      part_rows,
  )

  conn.commit()
  conn.close()
  return len(part_rows)


# =========================================================
# AUTO DATABASE BOOTSTRAP
# =========================================================
def ensure_database_ready():
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()

  c.execute("""
    CREATE TABLE IF NOT EXISTS complaints_master (
        c_no TEXT PRIMARY KEY, serial TEXT, phone TEXT, model TEXT,
        customer_name TEXT, technician_name TEXT, complaint_type TEXT,
        purchase_date TEXT, complaint_date TEXT, closed_date TEXT,
        hardware_products TEXT, hardware_part_nos TEXT
    )""")
  c.execute(
      "CREATE INDEX IF NOT EXISTS idx_search_keys ON"
      " complaints_master(serial, phone, c_no)"
  )
  c.execute(
      "CREATE INDEX IF NOT EXISTS idx_model ON complaints_master(model)"
  )

  c.execute("""
    CREATE TABLE IF NOT EXISTS parts_catalog (
        model TEXT, part_no TEXT, part_name TEXT, price INTEGER,
        PRIMARY KEY (model, part_no)
    )""")
  conn.commit()

  c.execute("SELECT COUNT(*) FROM complaints_master")
  count = c.fetchone()[0]
  conn.close()

  # Agar DB khali hai toh folder mein pari original files se auto-populate karein
  if count == 0:
    if os.path.exists(DEFAULT_FB_FILE):
      with st.spinner("Initializing Database from archive files..."):
        df_fb = pd.read_csv(DEFAULT_FB_FILE, low_memory=False)
        ingest_feedback_fast(df_fb)
        if os.path.exists(DEFAULT_COLL_FILE):
          df_coll = pd.read_excel(DEFAULT_COLL_FILE)
          ingest_pricing_fast(df_coll)


ensure_database_ready()


# =========================================================
# CACHED FETCHERS
# =========================================================
@st.cache_data
def get_all_models():
  conn = sqlite3.connect(DB_NAME)
  models = pd.read_sql_query(
      "SELECT DISTINCT model FROM complaints_master WHERE model != '' ORDER BY"
      " model ASC",
      conn,
  )
  conn.close()
  return models["model"].tolist()


@st.cache_data
def get_parts_for_model(selected_model, family_code):
  conn = sqlite3.connect(DB_NAME)
  query = """
        SELECT model, part_no, part_name, price 
        FROM parts_catalog 
        WHERE model = ? OR model LIKE ?
    """
  df = pd.read_sql_query(query, conn, params=(selected_model, f"{family_code}%"))
  conn.close()
  return df.drop_duplicates(subset=["part_no"])


# =========================================================
# SIDEBAR (FOR DAILY REFRESH ONLY)
# =========================================================
with st.sidebar:
  st.subheader("⚙️ Data Sync Center")
  st.caption("Upload daily fresh ERP report to append or update complaints.")

  up_fb = st.file_uploader(
      "1. Quality Feedback (CSV/Excel)",
      type=["csv", "xlsx", "xls"],
      key="fb_up",
  )
  if up_fb:
    if st.button("Sync Feedback Records"):
      with st.spinner("Syncing records to DB..."):
        df_in = (
            pd.read_csv(up_fb, low_memory=False)
            if up_fb.name.endswith(".csv")
            else pd.read_excel(up_fb)
        )
        cnt = ingest_feedback_fast(df_in)
        st.success(f"{cnt:,} records synced!")
        st.cache_data.clear()
        st.rerun()

  st.divider()
  up_coll = st.file_uploader(
      "2. Collection Pricing (Excel)", type=["xlsx", "xls"], key="coll_up"
  )
  if up_coll:
    if st.button("Update Parts Catalog"):
      with st.spinner("Updating pricing..."):
        df_c = pd.read_excel(up_coll)
        cnt = ingest_pricing_fast(df_c)
        st.success(f"{cnt:,} parts updated!")
        st.cache_data.clear()
        st.rerun()


# =========================================================
# BENCHMARK RULES
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


all_models = get_all_models()
tab_estimator, tab_history = st.tabs(
    ["🧮 Cost Estimator", "🔍 Unit & Customer History"]
)

# ==========================================
# TAB 1: ESTIMATOR
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
    family_code = selected_model[:7]
    available = get_parts_for_model(selected_model, family_code).copy()

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
      inc_mobility = st.checkbox("Mobility / Labor (Rs. 2,000)", value=True)
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
# TAB 2: INSTANT SEARCH (WITH AUTO-DATABASE)
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
        p_date = r["purchase_date"]
        c_date = r["complaint_date"]
        closed_date = r["closed_date"]
        parts_used = r["hardware_products"]
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

st.markdown(
    """
<div class="credit-footer">
    DWP Service Logistics & Operations Platform<br>
    System Architecture & Logic: <b>M. Abrar</b> | Operations Support
</div>
""",
    unsafe_allow_html=True,
)
