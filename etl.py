# etl.py
import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import re
import glob
from datetime import datetime
import pandas as pd
from config import (
    COLUMN_ALIASES, DEFAULT_FB_FILE, DEFAULT_COLL_FILE, STOCK_SEARCH_DIRS, STOCK_CSV_PATH,
    classify_component_role, get_role_price_floor, tokenize_appliance_model
)
from database import get_connection, init_db_schema

OFFICIAL_STOCK_CSV_PATH = os.path.join(BASE_DIR, "data", "pdf_extracted_stock_report.csv")

def clean_val(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip().replace('=', '').replace('"', '').strip()

def normalize_phone(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip().replace('=', '').replace('"', '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    digits = re.sub(r'\D', '', s)
    if digits.startswith('92') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif len(digits) == 10 and digits.startswith('3'):
        digits = '0' + digits
    return digits

def safe_read(source):
    if source is None:
        return pd.DataFrame()
    if isinstance(source, pd.DataFrame):
        return source.copy()
    if isinstance(source, str):
        if source.endswith('.csv'):
            try:
                return pd.read_csv(source, encoding='utf-8-sig', low_memory=False)
            except Exception:
                return pd.read_csv(source, encoding='latin1', low_memory=False)
        return pd.read_excel(source)
    else:
        filename = getattr(source, 'name', '')
        if filename.endswith('.csv'):
            try:
                return pd.read_csv(source, encoding='utf-8-sig', low_memory=False)
            except Exception:
                source.seek(0)
                return pd.read_csv(source, encoding='latin1', low_memory=False)
        return pd.read_excel(source)

def standardize_columns(df):
    mapping = {}
    for col in df.columns:
        norm = str(col).strip().upper()
        mapping[col] = COLUMN_ALIASES.get(norm, norm.lower())
    return df.rename(columns=mapping)

def find_latest_stock_file():
    candidates = []
    if os.path.exists(STOCK_CSV_PATH):
        candidates.append((os.path.getmtime(STOCK_CSV_PATH), STOCK_CSV_PATH))

    for d in STOCK_SEARCH_DIRS:
        if not os.path.exists(d):
            continue
        for pattern in ["*stock*.*", "*STOCK*.*", "*Stock*.*", "STOCK_DETAIL*.*", "Stock Balance*.*"]:
            for f in glob.glob(os.path.join(d, pattern)):
                if f.endswith(('.csv', '.xlsx', '.xls')) and not os.path.basename(f).startswith('~$'):
                    candidates.append((os.path.getmtime(f), f))
    if not candidates:
        return None
    # Sort candidates by modification time descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def ingest_pdf_stock_catalog(csv_path=None):
    """
    Ingests the official DWP Store Wise Stock Report (vp786.pdf / data/pdf_extracted_stock_report.csv)
    directly into stock_master and parts_master.
    Establishes official retail selling prices (pdf_price) and store total_stock (bal_qty).
    Returns count of unique parts ingested.
    """
    init_db_schema()
    target_path = csv_path or OFFICIAL_STOCK_CSV_PATH
    if not target_path or not os.path.exists(target_path):
        return 0

    raw_df = safe_read(target_path)
    if raw_df.empty or 'part_no' not in raw_df.columns:
        return 0

    df = raw_df.copy()
    df['part_no'] = df['part_no'].apply(clean_val).str.upper()
    df = df[df['part_no'] != ''].copy()

    def normalize_desc(s):
        val = clean_val(s)
        val = re.sub(r'\b(GS|GF|ES|EF|EW|GR|GW|WD|CX|EM)-\s+([0-9A-Za-z])', r'\1-\2', val)
        return re.sub(r'\s+', ' ', val).strip()

    df['item_desc'] = df['item_desc'].apply(normalize_desc)
    df['model'] = df['model'].apply(clean_val).str.upper()
    df['pdf_price'] = pd.to_numeric(df.get('pdf_price', 0), errors='coerce').fillna(0.0)
    df['total_stock'] = pd.to_numeric(df.get('total_stock', 0), errors='coerce').fillna(0).astype(int)

    now_str = datetime.now().strftime('%Y-%m-%d %I:%M %p')

    sec_stocks = {}
    if os.path.exists(STOCK_CSV_PATH):
        try:
            s_df = pd.read_csv(STOCK_CSV_PATH)
            for _, r in s_df.iterrows():
                p = clean_val(r.get('PART_NO')).upper()
                b = int(pd.to_numeric(r.get('BAL_QTY', 0), errors='coerce') or 0)
                if p and b > 0:
                    sec_stocks[p] = b
        except Exception:
            pass

    # 1. Populate parts_master with all model-part assignments (524 unique pairs)
    parts_rows = []
    for _, r in df.iterrows():
        m = r['model']
        pno = r['part_no']
        desc = r['item_desc']
        pr = int(round(float(r['pdf_price'])))
        if m and pno:
            parts_rows.append((m, pno, desc, pr))

    # 2. Aggregate 518 unique parts for stock_master
    agg_dict = {}
    for _, r in df.iterrows():
        pno = r['part_no']
        pr = int(round(float(r['pdf_price'])))
        stk = int(r['total_stock'])
        if stk <= 0 and pno in sec_stocks:
            stk = sec_stocks[pno]
        desc = r['item_desc']
        m = r['model']

        if pno not in agg_dict:
            agg_dict[pno] = {
                'part_no': pno,
                'item_desc': desc,
                'model': m,
                'pdf_price': pr,
                'total_stock': stk
            }
        else:
            # Select maximum executive retail price
            if pr > agg_dict[pno]['pdf_price']:
                agg_dict[pno]['pdf_price'] = pr
            # Sum stock balance across bins
            agg_dict[pno]['total_stock'] += stk
            if agg_dict[pno]['total_stock'] <= 0 and pno in sec_stocks:
                agg_dict[pno]['total_stock'] = sec_stocks[pno]
            # Keep longest canonical description
            if len(desc) > len(agg_dict[pno]['item_desc']):
                agg_dict[pno]['item_desc'] = desc
            if not agg_dict[pno]['model'] and m:
                agg_dict[pno]['model'] = m

    stock_rows = []
    for pno, info in agg_dict.items():
        tok = tokenize_appliance_model(info['model'] if info['model'] else info['item_desc'])
        brand = tok.get('brand') or "Gree"
        category = tok.get('category') or "Split AC"
        capacity = tok.get('tonnage') or "1.5 Ton"
        product = "Audio Video" if category in ["LED TV", "Microwave Oven"] else "Home Appliances"
        bal_qty = info['total_stock']
        unit_price = info['pdf_price']
        amount = float(unit_price * bal_qty) if bal_qty > 0 else 0.0

        stock_rows.append((
            pno,
            "",                 # item_code
            info['item_desc'],  # item_desc
            product,            # product
            brand,              # brand
            category,           # category
            capacity,           # capacity
            bal_qty,            # bal_qty
            amount,             # amount
            unit_price,         # unit_price
            "DWP Official Price Catalog (vp786.pdf)"  # last_synced
        ))

    with get_connection() as conn:
        cursor = conn.cursor()
        # Upsert parts_master
        cursor.executemany("""
            INSERT INTO parts_master (model, part_no, part_name, price)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(model, part_no) DO UPDATE SET
                price = excluded.price,
                part_name = excluded.part_name
        """, parts_rows)

        # Upsert stock_master
        cursor.executemany("""
            INSERT INTO stock_master 
            (part_no, item_code, item_desc, product, brand, category, capacity, bal_qty, amount, unit_price, last_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(part_no) DO UPDATE SET
                item_desc = excluded.item_desc,
                brand = CASE WHEN stock_master.brand IS NULL OR stock_master.brand = '' THEN excluded.brand ELSE stock_master.brand END,
                category = CASE WHEN stock_master.category IS NULL OR stock_master.category = '' THEN excluded.category ELSE stock_master.category END,
                capacity = CASE WHEN stock_master.capacity IS NULL OR stock_master.capacity = '' THEN excluded.capacity ELSE stock_master.capacity END,
                product = CASE WHEN stock_master.product IS NULL OR stock_master.product = '' THEN excluded.product ELSE stock_master.product END,
                bal_qty = excluded.bal_qty,
                amount = excluded.amount,
                unit_price = excluded.unit_price,
                last_synced = excluded.last_synced
        """, stock_rows)

        # Cross-enrich parts_master with valid prices from stock_master
        cursor.execute("""
            UPDATE parts_master
            SET price = (
                SELECT s.unit_price FROM stock_master s 
                WHERE s.part_no = parts_master.part_no AND s.unit_price > 0
            )
            WHERE (price IS NULL OR price = 0)
              AND EXISTS (
                SELECT 1 FROM stock_master s 
                WHERE s.part_no = parts_master.part_no AND s.unit_price > 0
              )
        """)

        # Ensure zero-pricing immunity across parts_master
        cursor.execute("SELECT model, part_no, part_name FROM parts_master WHERE price IS NULL OR price <= 0")
        zero_rows = cursor.fetchall()
        if zero_rows:
            zero_updates = []
            for m, pno, pname in zero_rows:
                tok = tokenize_appliance_model(m)
                role = classify_component_role(pname, pno)
                pr = get_role_price_floor(role, tok.get('tonnage', '1.5 Ton'), tok.get('category', 'Split AC'))
                zero_updates.append((int(pr), m, pno))
            cursor.executemany("UPDATE parts_master SET price = ? WHERE model = ? AND part_no = ?", zero_updates)

    return len(stock_rows)

def ingest_stock_file(stock_source):
    init_db_schema()
    raw = safe_read(stock_source)
    if raw.empty:
        return 0, 0

    df = standardize_columns(raw)
    if 'part_no' not in df.columns:
        return 0, 0

    df['part_no'] = df['part_no'].apply(clean_val).str.upper()
    df = df[df['part_no'] != ''].copy()

    for col in ['item_desc', 'item_code', 'product', 'brand', 'category', 'capacity']:
        df[col] = df[col].apply(clean_val) if col in df.columns else ""

    df['bal_qty'] = pd.to_numeric(df.get('bal_qty', 0), errors='coerce').fillna(0).astype(int)
    df['amount'] = pd.to_numeric(df.get('amount', 0), errors='coerce').fillna(0.0)

    now_str = datetime.now().strftime('%Y-%m-%d %I:%M %p')

    # Load official price catalog authority (Master Price Authority)
    official_prices = {}
    if os.path.exists(OFFICIAL_STOCK_CSV_PATH):
        try:
            pdf_df = pd.read_csv(OFFICIAL_STOCK_CSV_PATH, dtype=str)
            pdf_df['p_clean'] = pdf_df['part_no'].apply(clean_val).str.upper()
            pdf_df['pr_clean'] = pd.to_numeric(pdf_df['pdf_price'], errors='coerce').fillna(0)
            official_prices = pdf_df.groupby('p_clean')['pr_clean'].max().to_dict()
        except Exception:
            pass

    # Fetch any established prices from parts_master
    with get_connection() as conn:
        existing_prices = pd.read_sql_query(
            "SELECT part_no, MAX(price) as hist_price FROM parts_master WHERE price > 0 GROUP BY part_no",
            conn
        ).set_index('part_no')['hist_price'].to_dict()

    def calculate_clean_unit_price(r):
        pno = r['part_no']
        # 1. Authority 1: Master Price Catalog
        if pno in official_prices and official_prices[pno] > 0:
            return int(round(float(official_prices[pno])))
        # 2. Authority 2: Existing verified collection price
        if pno in existing_prices and existing_prices[pno] > 0:
            return int(existing_prices[pno])
            
        # 3. Authority 3: Role floor protection
        desc = str(r.get('item_desc', ''))
        role = classify_component_role(desc, pno)
        
        cap = str(r.get('capacity', ''))
        desc_up = desc.upper()
        ton = "1.5 Ton"
        for t_str, token in [('4.0 Ton', '48'), ('3.0 Ton', '36'), ('2.0 Ton', '24'), ('1.0 Ton', '12'), ('1.5 Ton', '18')]:
            if token in desc_up or token in cap:
                ton = t_str
                break
                
        cat = str(r.get('category', 'Split AC'))
        return get_role_price_floor(role, ton, cat)

    df['unit_price'] = df.apply(calculate_clean_unit_price, axis=1)
    df['amount'] = df.apply(lambda r: float(round(r['unit_price'] * r['bal_qty'], 2)) if r['bal_qty'] > 0 else 0.0, axis=1)

    stock_records = df[[
        'part_no', 'item_code', 'item_desc', 'product', 'brand', 
        'category', 'capacity', 'bal_qty', 'amount', 'unit_price'
    ]].copy()
    stock_records['last_synced'] = now_str

    records_list = stock_records.values.tolist()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO stock_master 
            (part_no, item_code, item_desc, product, brand, category, capacity, bal_qty, amount, unit_price, last_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records_list)

        # Cross-enrich parts_master with valid prices from stock_master
        cursor.execute("""
            UPDATE parts_master
            SET price = (
                SELECT s.unit_price FROM stock_master s 
                WHERE s.part_no = parts_master.part_no AND s.unit_price > 0
            )
            WHERE (price IS NULL OR price = 0)
              AND EXISTS (
                SELECT 1 FROM stock_master s 
                WHERE s.part_no = parts_master.part_no AND s.unit_price > 0
              )
        """)

    in_stock_count = int((df['bal_qty'] > 0).sum())
    return len(records_list), in_stock_count

def bootstrap_master_data():
    init_db_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM history_master")
        hist_count = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM stock_master")
        stock_count = cursor.fetchone()[0]

    if hist_count == 0 and os.path.exists(DEFAULT_FB_FILE):
        coll_path = DEFAULT_COLL_FILE if os.path.exists(DEFAULT_COLL_FILE) else None
        ingest_feedback_and_pricing(DEFAULT_FB_FILE, coll_path)

    if stock_count == 0:
        latest_stock = find_latest_stock_file()
        if latest_stock:
            ingest_stock_file(latest_stock)

    # Master Price Authority: Always synchronize the official PDF catalog
    if os.path.exists(OFFICIAL_STOCK_CSV_PATH):
        ingest_pdf_stock_catalog(OFFICIAL_STOCK_CSV_PATH)

    # Cross-enrich parts_master with baseline ground-truth model-specific parts and prices
    try:
        from database import load_ground_truth_baseline
        baseline = load_ground_truth_baseline()
        models_dict = baseline.get("models", {})
        model_updates = []
        for m_name, m_data in models_dict.items():
            for p in m_data.get('parts', []):
                if p.get('price', 0) > 0:
                    model_updates.append((int(p['price']), p.get('part_name', ''), m_name, p['part_no']))

        price_book = baseline.get("price_book", {})
        stk_updates = [(int(info.get('price', 0)), pno) for pno, info in price_book.items() if info.get('price', 0) > 0]
        
        with get_connection() as conn:
            cursor = conn.cursor()
            if model_updates:
                cursor.executemany("""
                    INSERT INTO parts_master (price, part_name, model, part_no)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(model, part_no) DO UPDATE SET
                        price = excluded.price,
                        part_name = excluded.part_name
                """, model_updates)
            if stk_updates:
                cursor.executemany("""
                    UPDATE stock_master SET unit_price = ? WHERE part_no = ?
                """, stk_updates)

            # Database hygiene: eliminate obsolete accounting ledger valuation residues
            cursor.execute("""
                UPDATE stock_master 
                SET amount = ROUND(unit_price * bal_qty, 2) 
                WHERE abs(amount - (unit_price * bal_qty)) > 0.01
            """)
            cursor.execute("""
                UPDATE stock_master 
                SET amount = 0.0 
                WHERE bal_qty <= 0 AND amount != 0.0
            """)

            # Ensure zero-pricing immunity across parts_master
            cursor.execute("SELECT model, part_no, part_name FROM parts_master WHERE price IS NULL OR price <= 0")
            zero_rows = cursor.fetchall()
            if zero_rows:
                zero_updates = []
                for m, pno, pname in zero_rows:
                    pr = price_book.get(pno, {}).get('price', 0)
                    if pr <= 0:
                        tok = tokenize_appliance_model(m)
                        role = classify_component_role(pname, pno)
                        pr = get_role_price_floor(role, tok.get('tonnage', '1.5 Ton'), tok.get('category', 'Split AC'))
                    zero_updates.append((int(pr), m, pno))
                cursor.executemany("UPDATE parts_master SET price = ? WHERE model = ? AND part_no = ?", zero_updates)
    except Exception:
        pass

def ingest_feedback_and_pricing(fb_source, coll_source=None):
    fb = standardize_columns(safe_read(fb_source))
    fb['complaint_no'] = fb['complaint_no'].apply(clean_val)
    fb['serial'] = fb['serial'].apply(clean_val).str.upper() if 'serial' in fb.columns else ""
    fb['phone'] = fb['phone'].apply(normalize_phone) if 'phone' in fb.columns else ""
    fb['model'] = fb['model'].astype(str).str.strip().str.upper() if 'model' in fb.columns else ""
    fb['remarks'] = fb['remarks'].apply(clean_val) if 'remarks' in fb.columns else ""

    for col in ['customer_name', 'technician_name', 'complaint_type', 'purchase_date', 'complaint_date', 'closed_date']:
        fb[col] = fb[col].apply(clean_val) if col in fb.columns else ""

    parts_records = []
    fb['closed_amount'] = 0

    if coll_source is not None:
        try:
            coll = standardize_columns(safe_read(coll_source))
            coll['complaint_no'] = coll['complaint_no'].apply(clean_val)
            coll['net_amt'] = pd.to_numeric(coll.get('net_collection', 0), errors='coerce').fillna(0).astype(int)

            part_cash = pd.to_numeric(coll.get('part_cash', 0), errors='coerce').fillna(0)
            part_warr = pd.to_numeric(coll.get('part_warranty', 0), errors='coerce').fillna(0)
            coll['eff_price'] = part_cash.where(part_cash > 0, part_warr)

            merged = pd.merge(fb, coll[['complaint_no', 'eff_price']], on='complaint_no', how='inner')

            if 'part_nos' in fb.columns and not merged.empty:
                single = merged[~merged['part_nos'].astype(str).str.contains(',', na=False)].copy()
                single['p_clean'] = single['part_nos'].astype(str).str.strip()
                exact_map = single.groupby('p_clean')['eff_price'].agg(
                    lambda x: x.mode()[0] if not x.mode().empty else x.median()
                ).to_dict()

                for _, row in fb.iterrows():
                    pnos = str(row.get('part_nos', ''))
                    prods = str(row.get('products', ''))
                    if not pnos or pnos.lower() == 'nan':
                        continue
                    p_list = [p.strip() for p in pnos.split(',') if p.strip()]
                    pr_list = [p.strip() for p in prods.split(',') if p.strip()]
                    for i, pno in enumerate(p_list):
                        pname = pr_list[i] if i < len(pr_list) else (pr_list[0] if pr_list else "Component")
                        parts_records.append((row['model'], pno, pname, int(exact_map.get(pno, 0))))

            amt_map = coll.groupby('complaint_no')['net_amt'].max().to_dict()
            fb['closed_amount'] = fb['complaint_no'].map(amt_map).fillna(0).astype(int)
        except Exception:
            pass

    with get_connection() as conn:
        cursor = conn.cursor()
        if parts_records:
            cursor.executemany("INSERT OR REPLACE INTO parts_master (model, part_no, part_name, price) VALUES (?, ?, ?, ?)", parts_records)

        hist_records = fb[['complaint_no', 'serial', 'phone', 'model', 'customer_name', 
                           'technician_name', 'complaint_type', 'purchase_date', 
                           'complaint_date', 'closed_date', 'remarks', 'closed_amount']].values.tolist()
        cursor.executemany("""
            INSERT OR REPLACE INTO history_master 
            (complaint_no, serial, phone, model, customer_name, technician_name, complaint_type, purchase_date, complaint_date, closed_date, remarks, closed_amount) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, hist_records)

def ingest_performance_pipeline(fb_source, cancel_source):
    fb = standardize_columns(safe_read(fb_source))
    cancel = standardize_columns(safe_read(cancel_source))

    fb['complaint_no'] = fb['complaint_no'].apply(clean_val)
    cancel['complaint_no'] = cancel['complaint_no'].apply(clean_val)

    fb_sub = pd.DataFrame({
        'complaint_no': fb['complaint_no'],
        'technician_name': fb['technician_name'].apply(clean_val),
        'status': fb['status'].astype(str).str.upper().str.strip() if 'status' in fb.columns else 'COMPLETED',
        'closed_date': fb['closed_date'].apply(clean_val),
        '_priority': 2
    })

    can_sub = pd.DataFrame({
        'complaint_no': cancel['complaint_no'],
        'technician_name': cancel['technician_name'].apply(clean_val) if 'technician_name' in cancel.columns else '',
        'status': cancel['status'].astype(str).str.upper().str.strip() if 'status' in cancel.columns else 'CANCELED',
        'closed_date': cancel['closed_date'].apply(clean_val) if 'closed_date' in cancel.columns else '',
        '_priority': 1
    })

    comb = pd.concat([fb_sub, can_sub], ignore_index=True)
    comb.sort_values(by=['complaint_no', '_priority'], ascending=[True, True], inplace=True)
    master_perf = comb.drop_duplicates(subset=['complaint_no'], keep='last').copy()
    
    # Exclude TRANSFERED jobs
    master_perf = master_perf[master_perf['status'] != 'TRANSFERED'].copy()

    clean_dates = master_perf['closed_date'].astype(str).str.replace('Sept', 'Sep', regex=False)
    parsed_dates = pd.to_datetime(clean_dates, format='mixed', errors='coerce').dt.strftime('%Y-%m-%d').fillna('')

    perf_records = pd.DataFrame({
        'complaint_no': master_perf['complaint_no'],
        'technician_name': master_perf['technician_name'],
        'status': master_perf['status'],
        'closed_date': parsed_dates
    }).values.tolist()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tech_performance_master")
        cursor.executemany("INSERT OR REPLACE INTO tech_performance_master (complaint_no, technician_name, status, closed_date) VALUES (?, ?, ?, ?)", perf_records)
