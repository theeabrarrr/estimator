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
from config import COLUMN_ALIASES, DEFAULT_FB_FILE, DEFAULT_COLL_FILE, STOCK_SEARCH_DIRS
from database import get_connection, init_db_schema

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
    for d in STOCK_SEARCH_DIRS:
        if not os.path.exists(d):
            continue
        for pattern in ["STOCK_DETAIL*.*", "Stock Balance*.*", "*STOCK*.*"]:
            for f in glob.glob(os.path.join(d, pattern)):
                if f.endswith(('.csv', '.xlsx', '.xls')) and not os.path.basename(f).startswith('~$'):
                    candidates.append((os.path.getmtime(f), f))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

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

    # Calculate unit_price from ledger value
    df['calc_price'] = df.apply(
        lambda r: int(round(r['amount'] / r['bal_qty'])) if (r['bal_qty'] > 0 and r['amount'] > 0) else 0,
        axis=1
    )

    now_str = datetime.now().strftime('%Y-%m-%d %I:%M %p')

    # Fetch any established prices from parts_master
    with get_connection() as conn:
        existing_prices = pd.read_sql_query(
            "SELECT part_no, MAX(price) as hist_price FROM parts_master WHERE price > 0 GROUP BY part_no",
            conn
        ).set_index('part_no')['hist_price'].to_dict()

    # Determine final unit price (prefer history/retail price if available)
    df['unit_price'] = df.apply(
        lambda r: existing_prices.get(r['part_no'], r['calc_price']),
        axis=1
    )

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
