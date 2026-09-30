import pandas as pd
import re
from database import get_connection

def safe_read(file_obj):
    if file_obj.name.endswith('.csv'):
        return pd.read_csv(file_obj, dtype=str)
    return pd.read_excel(file_obj, dtype=str)

def standardize_columns(df):
    df.columns = (
        df.columns.astype(str)
        .str.lower()
        .str.replace(r'[^a-z0-9]+', '_', regex=True)
        .str.strip('_')
    )
    if 'complain_no' in df.columns:
        df.rename(columns={'complain_no': 'complaint_no'}, inplace=True)
    if 'item_desc' in df.columns:
        df.rename(columns={'item_desc': 'part_name'}, inplace=True)
    return df

def clean_val(val):
    return str(val).strip() if pd.notna(val) else ""

def normalize_phone(ph):
    p = clean_val(ph).replace('-', '').replace(' ', '')
    p = re.sub(r'[^0-9+]', '', p)
    if p.startswith('+92'): p = '0' + p[3:]
    elif p.startswith('92'): p = '0' + p[2:]
    return p[:11]

def ingest_feedback_and_pricing(fb_source, coll_source=None):
    fb = standardize_columns(safe_read(fb_source))
    fb['complaint_no'] = fb['complaint_no'].apply(clean_val)
    fb['serial'] = fb['serial'].apply(clean_val).str.upper() if 'serial' in fb.columns else ""
    fb['phone'] = fb['phone'].apply(normalize_phone) if 'phone' in fb.columns else ""
    fb['model'] = fb['model'].astype(str).str.strip().str.upper() if 'model' in fb.columns else ""
    fb['remarks'] = fb['remarks'].apply(clean_val) if 'remarks' in fb.columns else ""

    for col in ['customer_name', 'technician_name', 'complaint_type', 'purchase_date', 'complaint_date', 'closed_date']:
        fb[col] = fb[col].apply(clean_val) if col in fb.columns else ""

    fb['closed_amount'] = 0

    if coll_source is not None:
        try:
            coll = standardize_columns(safe_read(coll_source))
            coll['complaint_no'] = coll['complaint_no'].apply(clean_val)
            coll['net_amt'] = pd.to_numeric(coll.get('net_collection', 0), errors='coerce').fillna(0).astype(int)
            amt_map = coll.groupby('complaint_no')['net_amt'].max().to_dict()
            fb['closed_amount'] = fb['complaint_no'].map(amt_map).fillna(0).astype(int)
        except Exception:
            pass

    with get_connection() as conn:
        cursor = conn.cursor()
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
