import pandas as pd
import re
from database import get_connection, init_estimator_schema

def safe_read(file_obj):
    if isinstance(file_obj, str):
        if file_obj.lower().endswith('.csv'):
            return pd.read_csv(file_obj, dtype=str)
        return pd.read_excel(file_obj, dtype=str)
    
    fname = getattr(file_obj, 'name', '').lower()
    if fname.endswith('.csv'):
        return pd.read_csv(file_obj, dtype=str)
    else:
        try:
            return pd.read_excel(file_obj, dtype=str)
        except Exception:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            return pd.read_csv(file_obj, dtype=str)

def standardize_columns(df):
    df.columns = (
        df.columns.astype(str)
        .str.lower()
        .str.replace(r'[^a-z0-9]+', '_', regex=True)
        .str.strip('_')
    )
    
    # Complaint Number Aliases
    for col in ['complain_no', 'complaintno', 'complain_number', 'complaint_number', 'job_no', 'ticket_no']:
        if col in df.columns and 'complaint_no' not in df.columns:
            df.rename(columns={col: 'complaint_no'}, inplace=True)
            
    # Status Aliases (e.g. COMPLETED_STATUS -> status)
    for col in ['completed_status', 'job_status', 'call_status', 'complaint_status', 'current_status', 'job_type']:
        if col in df.columns and 'status' not in df.columns:
            df.rename(columns={col: 'status'}, inplace=True)

    # Technician Name Aliases
    for col in ['tech_name', 'technician', 'tech', 'emp_name', 'engineer_name', 'allocated_tech']:
        if col in df.columns and 'technician_name' not in df.columns:
            df.rename(columns={col: 'technician_name'}, inplace=True)

    # Closed Date Aliases
    for col in ['complete_date', 'completion_date', 'close_date', 'resolved_date', 'action_date']:
        if col in df.columns and 'closed_date' not in df.columns:
            df.rename(columns={col: 'closed_date'}, inplace=True)

    if 'item_desc' in df.columns and 'part_name' not in df.columns:
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
    init_estimator_schema()
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
        conn.commit()

def ingest_performance_pipeline(fb_source, cancel_source=None):
    init_estimator_schema()
    fb = standardize_columns(safe_read(fb_source))

    if 'complaint_no' in fb.columns:
        fb['complaint_no'] = fb['complaint_no'].apply(clean_val)

    fb_sub = pd.DataFrame({
        'complaint_no': fb['complaint_no'] if 'complaint_no' in fb.columns else pd.Series(dtype=str),
        'technician_name': fb['technician_name'].apply(clean_val) if 'technician_name' in fb.columns else '',
        'status': fb['status'].astype(str).str.upper().str.strip() if 'status' in fb.columns else 'COMPLETED',
        'closed_date': fb['closed_date'].apply(clean_val) if 'closed_date' in fb.columns else '',
        '_priority': 2
    })

    if cancel_source is not None:
        cancel = standardize_columns(safe_read(cancel_source))
        if 'complaint_no' in cancel.columns:
            cancel['complaint_no'] = cancel['complaint_no'].apply(clean_val)

        can_sub = pd.DataFrame({
            'complaint_no': cancel['complaint_no'] if 'complaint_no' in cancel.columns else pd.Series(dtype=str),
            'technician_name': cancel['technician_name'].apply(clean_val) if 'technician_name' in cancel.columns else '',
            'status': cancel['status'].astype(str).str.upper().str.strip() if 'status' in cancel.columns else 'CANCELED',
            'closed_date': cancel['closed_date'].apply(clean_val) if 'closed_date' in cancel.columns else '',
            '_priority': 1
        })
    else:
        can_sub = pd.DataFrame(columns=['complaint_no', 'technician_name', 'status', 'closed_date', '_priority'])

    comb = pd.concat([fb_sub, can_sub], ignore_index=True)
    if comb.empty or 'complaint_no' not in comb.columns:
        return 0

    comb.sort_values(by=['complaint_no', '_priority'], ascending=[True, True], inplace=True)
    master_perf = comb.drop_duplicates(subset=['complaint_no'], keep='last').copy()
    
    # Exclude TRANSFERED jobs
    master_perf = master_perf[master_perf['status'] != 'TRANSFERED'].copy()

    clean_dates = master_perf['closed_date'].astype(str).str.replace('Sept', 'Sep', regex=False)
    parsed = pd.to_datetime(clean_dates, format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
    today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
    parsed_dates = parsed.fillna(clean_dates).replace('', today_str).replace('nan', today_str)

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
        conn.commit()
    return len(perf_records)

# ============================================================================
# ESTIMATOR PIPELINES: STORE STOCK PDF & QUALITY FEEDBACK CATALOG
# ============================================================================
import json
import pdfplumber
import config
from database import upsert_master_parts, upsert_model_catalog, append_model_catalog

def clean_excel_str(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    return s.strip()

def parse_store_stock_pdf(pdf_source=None) -> int:
    """
    Parses Karachi-2 HA Store stock report PDF (vp786), extracts prices, store stock,
    technician hand allocations, and enterprise totals. Normalizes negative balances.
    Filters out complete B-grade finished units.
    """
    if pdf_source is None:
        pdf_source = getattr(config, 'DEFAULT_STOCK_PDF', 'vp786 (1 year stock movement report).pdf')
    
    # Technician names in PDF headers
    tech_p1_names = ["Ameer Hamza", "Arslan Kh2HA", "Asghar Ali", "Faizan", "Haroon", 
                     "Irfan Malik", "Jafar Raza", "Jibran Ahmed", "Kaleem Uddin", "Mohsin"]
    tech_p1_indices = [5, 6, 7, 8, 9, 10, 11, 12, 13, 16]
    
    tech_p2_names = ["Muhammad Faraz", "Naveed Khan", "Sheharyar Khan", "Syed Jahanzaib",
                     "Ubaid Raza", "Umer Hayat Khi2", "Waseem Raja", "amin karachi 2ha", "muhammad naeem Kh"]
    tech_p2_indices = [5, 6, 7, 8, 9, 10, 11, 12, 13]
    
    parsed_records = []
    seen_parts = set()
    
    with pdfplumber.open(pdf_source) as pdf:
        num_pages = len(pdf.pages)
        for pair_idx in range(0, num_pages, 2):
            p1 = pdf.pages[pair_idx]
            p2 = pdf.pages[pair_idx + 1] if pair_idx + 1 < num_pages else None
            
            t1 = p1.extract_tables()
            t2 = p2.extract_tables() if p2 else []
            if not t1 or not t2:
                continue
                
            table1 = t1[0]
            table2 = t2[0]
            min_rows = min(len(table1), len(table2))
            
            for r_idx in range(1, min_rows):
                r1 = table1[r_idx]
                r2 = table2[r_idx]
                
                p_no = str(r1[1] if r1[1] is not None else (r2[1] if r2[1] is not None else '')).replace('\n', '').strip()
                desc = str(r1[2] if r1[2] is not None else (r2[2] if r2[2] is not None else '')).replace('\n', ' ').strip()
                model = str(r1[3] if r1[3] is not None else (r2[3] if r2[3] is not None else '')).replace('\n', ' ').strip()
                price_str = str(r1[4] if r1[4] is not None else (r2[4] if r2[4] is not None else '')).replace('\n', '').replace(',', '').strip()
                
                if not p_no and not desc:
                    continue
                
                # Rule 7: Filter out complete B-Grade finished units
                if re.search(r'b[- ]?grade\s+set', p_no + ' ' + desc, re.IGNORECASE):
                    continue
                
                if p_no in seen_parts:
                    continue
                seen_parts.add(p_no)
                
                try:
                    price = int(round(float(price_str))) if price_str else 0
                except Exception:
                    price = 0
                
                def parse_qty(v):
                    if v is None:
                        return 0
                    s = str(v).replace('\n', '').replace(',', '').strip()
                    try:
                        return int(float(s))
                    except Exception:
                        return 0
                
                sales_store = parse_qty(r1[14] if len(r1) > 14 else 0)
                branch_store = parse_qty(r1[15] if len(r1) > 15 else 0)
                total_stock = parse_qty(r2[14] if len(r2) > 14 else 0)
                
                tech_dict = {}
                for t_name, idx in zip(tech_p1_names, tech_p1_indices):
                    val = parse_qty(r1[idx] if len(r1) > idx else 0)
                    if val != 0:
                        tech_dict[t_name] = val
                        
                for t_name, idx in zip(tech_p2_names, tech_p2_indices):
                    val = parse_qty(r2[idx] if len(r2) > idx else 0)
                    if val != 0:
                        tech_dict[t_name] = val
                
                tech_total = sum(tech_dict.values())
                avail_branch = max(0, branch_store)
                avail_total = max(0, total_stock)
                stock_status = 'In Stock' if avail_branch > 0 else 'Out of Stock'
                
                source_doc = getattr(pdf_source, 'name', str(pdf_source))
                
                parsed_records.append((
                    p_no,
                    desc,
                    model,
                    price,
                    branch_store,
                    sales_store,
                    tech_total,
                    total_stock,
                    avail_branch,
                    avail_total,
                    stock_status,
                    json.dumps(tech_dict),
                    0,  # is_pricing_pending = 0 since present in stock report
                    source_doc
                ))
    
    if parsed_records:
        upsert_master_parts(parsed_records)
    return len(parsed_records)

def sync_model_part_catalog_from_feedback(fb_source=None, is_incremental: bool = False) -> tuple[int, int, int]:
    """
    Ingests Quality Feedback Report, extracts ground-truth model-to-part compatibility,
    explodes comma-separated parts, resolves Excel scientific notation artifacts,
    and populates model_part_catalog and pending entries in master_parts_lookup.
    If is_incremental is True, appends onto existing catalog without overwriting baseline.
    Returns (unique_models, unique_parts, total_installation_events).
    """
    if fb_source is None:
        fb_source = getattr(config, 'DEFAULT_FB_FILE', 'quality_feedback_report_28SEP2026_142900.csv')
    
    if isinstance(fb_source, str):
        df = pd.read_csv(fb_source, dtype=str)
    else:
        df = safe_read(fb_source)
    
    # Standardize column lookup
    col_map = {str(c).strip().upper(): c for c in df.columns}
    def get_c(key):
        return col_map.get(str(key).strip().upper(), '')
        
    c_status = get_c('COMPLETED_STATUS')
    if c_status and c_status in df.columns:
        df = df[df[c_status].astype(str).str.upper().str.strip() == 'COMPLETED'].copy()
        
    c_parts = get_c('HARDWARE_PART_NOS')
    if not c_parts or c_parts not in df.columns:
        return 0, 0, 0
        
    c_model = get_c('MODEL_NAME')
    c_prods = get_c('HARDWARE_PRODUCTS')
    c_boards = get_c('HARDWARE_BOARD_TYPES')
    c_qtys = get_c('HARDWARE_QTYS')
    c_closed = get_c('CLOSED_DATE')
    
    events = []
    
    for row in df.to_dict('records'):
        p_raw = clean_excel_str(row.get(c_parts, ''))
        if not p_raw or p_raw.lower() == 'nan':
            continue
            
        model = clean_excel_str(row.get(c_model, '')).upper()
        if not model:
            continue
            
        prods_raw = clean_excel_str(row.get(c_prods, ''))
        boards_raw = clean_excel_str(row.get(c_boards, ''))
        closed_date = clean_excel_str(row.get(c_closed, ''))
        
        p_nos = [p.strip() for p in p_raw.split(',') if p.strip()]
        p_prods = [p.strip() for p in prods_raw.split(',') if p.strip()]
        p_boards = [p.strip() for p in boards_raw.split(',') if p.strip()]
        
        for i, raw_part in enumerate(p_nos):
            prod_desc = p_prods[i] if i < len(p_prods) else (prods_raw if len(p_nos) == 1 else "")
            board = p_boards[i] if i < len(p_boards) else (boards_raw if len(p_nos) == 1 else "Component")
            
            clean_part = raw_part
            # Excel Scientific Notation Recovery (e.g. 3.00002E+11)
            if 'E+' in raw_part:
                digit_candidates = re.findall(r'[0-9A-Z\-]{7,15}', prod_desc)
                if digit_candidates:
                    clean_part = digit_candidates[-1]
            
            events.append({
                'model': model,
                'part_no': clean_part,
                'part_description': prod_desc,
                'board_type': board,
                'closed_date': closed_date
            })
            
    # Aggregate by (model, part_no) in pure Python dict
    grp_dict = {}
    for ev in events:
        key = (ev['model'], ev['part_no'])
        if key not in grp_dict:
            grp_dict[key] = {'freq': 0, 'descs': [], 'boards': [], 'dates': []}
        grp_dict[key]['freq'] += 1
        if ev['part_description']:
            grp_dict[key]['descs'].append(ev['part_description'])
        if ev['board_type']:
            grp_dict[key]['boards'].append(ev['board_type'])
        if ev['closed_date']:
            grp_dict[key]['dates'].append(ev['closed_date'])

    catalog_records = []
    unique_parts_set = set()
    models_set = set()

    for (m, p_no), data in grp_dict.items():
        best_desc = data['descs'][0] if data['descs'] else ""
        best_board = data['boards'][0] if data['boards'] else "Spare Part"
        last_date = data['dates'][-1] if data['dates'] else ""
        
        catalog_records.append((m, p_no, best_desc, best_board, data['freq'], last_date))
        unique_parts_set.add((p_no, best_desc, best_board))
        models_set.add(m)
        
    if is_incremental:
        append_model_catalog(catalog_records)
    else:
        upsert_model_catalog(catalog_records)
    
    # Ensure all parts exist in master_parts_lookup (flag unpriced parts as is_pricing_pending = 1)
    with get_connection() as conn:
        cursor = conn.cursor()
        pending_records = [(p_no, p_desc) for p_no, p_desc, _ in unique_parts_set]
        cursor.executemany("""
            INSERT OR IGNORE INTO master_parts_lookup 
            (part_no, erp_description, retail_price, is_pricing_pending, stock_status, last_synced)
            VALUES (?, ?, 0, 1, 'Out of Stock', CURRENT_TIMESTAMP)
        """, pending_records)
        conn.commit()
        
    return len(models_set), len(unique_parts_set), len(events)

