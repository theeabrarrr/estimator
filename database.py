# database.py
import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import sqlite3
import pandas as pd
import json
from config import (
    DB_NAME, BASELINE_JSON_PATH, COMPONENT_ROLE_GROUPS,
    tokenize_appliance_model, classify_component_role
)

_BASELINE_CACHE = None

def load_ground_truth_baseline():
    global _BASELINE_CACHE
    if _BASELINE_CACHE is not None:
        return _BASELINE_CACHE
        
    if os.path.exists(BASELINE_JSON_PATH):
        try:
            with open(BASELINE_JSON_PATH, 'r', encoding='utf-8') as f:
                _BASELINE_CACHE = json.load(f)
                return _BASELINE_CACHE
        except Exception:
            pass
    return {'models': {}, 'series': {}, 'global_stock': {}}

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db_schema():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parts_master (
                model TEXT,
                part_no TEXT,
                part_name TEXT,
                price INTEGER,
                PRIMARY KEY (model, part_no)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_master (
                part_no TEXT PRIMARY KEY,
                item_code TEXT,
                item_desc TEXT,
                product TEXT,
                brand TEXT,
                category TEXT,
                capacity TEXT,
                bal_qty INTEGER DEFAULT 0,
                amount REAL DEFAULT 0.0,
                unit_price INTEGER DEFAULT 0,
                last_synced TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_pno ON stock_master(part_no)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_desc ON stock_master(item_desc)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_cat ON stock_master(category)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history_master (
                complaint_no TEXT PRIMARY KEY,
                serial TEXT,
                phone TEXT,
                model TEXT,
                customer_name TEXT,
                technician_name TEXT,
                complaint_type TEXT,
                purchase_date TEXT,
                complaint_date TEXT,
                closed_date TEXT,
                remarks TEXT,
                closed_amount INTEGER
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_search ON history_master(serial, phone, complaint_no)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_model ON history_master(model)")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tech_performance_master (
                complaint_no TEXT PRIMARY KEY,
                technician_name TEXT,
                status TEXT,
                closed_date TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tp ON tech_performance_master(technician_name, status, closed_date)")

def fetch_parts_and_models():
    init_db_schema()
    baseline = load_ground_truth_baseline()
    base_models = list(baseline.get('models', {}).keys())
    
    with get_connection() as conn:
        h_models = pd.read_sql_query("SELECT DISTINCT model FROM history_master WHERE model != '' AND model != 'NAN'", conn)['model'].tolist()
        parts_df = pd.read_sql_query("SELECT * FROM parts_master", conn)
        p_models = parts_df['model'].dropna().unique().tolist() if not parts_df.empty else []
        all_models = sorted(list(set([m for m in (base_models + h_models + p_models) if len(m) > 1])))
    return parts_df, all_models

def fetch_tiered_compatible_parts(selected_model):
    init_db_schema()
    baseline = load_ground_truth_baseline()
    tok = tokenize_appliance_model(selected_model)
    model_name = tok['model']
    series_key = tok['series_key']
    
    # Live stock lookup dictionary from SQLite stock_master
    live_stock_map = {}
    with get_connection() as conn:
        stock_rows = pd.read_sql_query("SELECT part_no, bal_qty, unit_price FROM stock_master", conn)
        for _, sr in stock_rows.iterrows():
            live_stock_map[sr['part_no'].upper()] = {
                'bal_qty': int(sr['bal_qty']),
                'unit_price': int(sr['unit_price'])
            }

    def is_series_compatible(pname, target_series, role):
        if not target_series:
            return True
        pn = pname.upper()
        if 'COMMON' in pn or 'UNIVERSAL' in pn:
            return True
        chassis_sensitive = [
            'Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 
            'Display Board', 'Cross Flow Fan', 'Front Panel'
        ]
        tokens = ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'LM', 'ECH']
        found = [s for s in tokens if s in pn]
        if found:
            if target_series in found:
                return True
            if role in chassis_sensitive:
                return False
        return True

    # 1. Tier 1: Exact Model Match (Ground Truth)
    t1_records = baseline.get('models', {}).get(model_name, {}).get('parts', [])
    t1_part_nos = set()
    scored_parts = []
    
    total_verified_jobs = 0
    for p in t1_records:
        if not is_series_compatible(p['part_name'], tok['series'], p['role']):
            continue
        p_copy = p.copy()
        pno = p['part_no'].upper()
        # Override with live stock if available
        if pno in live_stock_map:
            p_copy['bal_qty'] = live_stock_map[pno]['bal_qty']
            p_copy['in_stock'] = p_copy['bal_qty'] > 0
            if p_copy['price'] <= 0 and live_stock_map[pno]['unit_price'] > 0:
                p_copy['price'] = live_stock_map[pno]['unit_price']
                
        p_copy['tier'] = "Tier 1: Exact Model Verified"
        p_copy['tier_code'] = 1
        p_copy['score'] = (p['verified_jobs'] * 2) + (10 if p_copy['in_stock'] else 0) + 20
        scored_parts.append(p_copy)
        t1_part_nos.add(pno)
        total_verified_jobs += p['verified_jobs']

    # 2. Tier 2: Strict Platform Series Match (Strictly Isolated by Series Key)
    series_records = baseline.get('series', {}).get(series_key, [])
    for p in series_records:
        if not is_series_compatible(p['part_name'], tok['series'], p['role']):
            continue
        pno = p['part_no'].upper()
        if pno not in t1_part_nos:
            p_copy = p.copy()
            if pno in live_stock_map:
                p_copy['bal_qty'] = live_stock_map[pno]['bal_qty']
                p_copy['in_stock'] = p_copy['bal_qty'] > 0
                if p_copy['price'] <= 0 and live_stock_map[pno]['unit_price'] > 0:
                    p_copy['price'] = live_stock_map[pno]['unit_price']
                    
            p_copy['tier'] = f"Tier 2: {tok['series']} Series Platform"
            p_copy['tier_code'] = 2
            p_copy['score'] = (p['verified_jobs'] * 2) + (10 if p_copy['in_stock'] else 0) + 5
            scored_parts.append(p_copy)
            t1_part_nos.add(pno)

    # Group candidate parts by Functional Role
    role_map = {}
    for p in scored_parts:
        r = p['role']
        if r not in role_map:
            role_map[r] = []
        role_map[r].append(p)

    structured_groups = []
    
    for group_title, roles in COMPONENT_ROLE_GROUPS:
        matched_items = []
        for r in roles:
            matched_items.extend(role_map.get(r, []))
            
        if not matched_items:
            continue
            
        # Deduplication & Ranking: Sort by Score descending
        matched_items.sort(key=lambda x: (x['score'], x['in_stock'], x['verified_jobs']), reverse=True)
        primary_item = matched_items[0]
        alt_items = matched_items[1:]
        
        in_stock_count = sum(1 for it in matched_items if it['in_stock'])
        
        structured_groups.append({
            'group_title': group_title,
            'primary': primary_item,
            'alternatives': alt_items,
            'total_items': len(matched_items),
            'in_stock_items': in_stock_count
        })

    return {
        'model': selected_model,
        'meta': tok,
        'role_groups': structured_groups,
        'total_verified_jobs': total_verified_jobs,
        'total_parts_found': len(scored_parts)
    }

def fetch_parts_with_live_stock(selected_model):
    res = fetch_tiered_compatible_parts(selected_model)
    flat_list = []
    for grp in res.get('role_groups', []):
        flat_list.append(grp['primary'])
        flat_list.extend(grp['alternatives'])
    return pd.DataFrame(flat_list) if flat_list else pd.DataFrame()

def search_stock_global(query_str, limit=60):
    init_db_schema()
    q = f"%{query_str.strip()}%"
    with get_connection() as conn:
        sql = """
            SELECT 
                part_no,
                item_desc as part_name,
                brand,
                category,
                capacity,
                bal_qty,
                unit_price as price
            FROM stock_master
            WHERE part_no LIKE ? OR UPPER(item_desc) LIKE UPPER(?) OR UPPER(category) LIKE UPPER(?)
            ORDER BY bal_qty DESC, item_desc ASC
            LIMIT ?
        """
        df = pd.read_sql_query(sql, conn, params=(q, q, q, limit))
        
    baseline = load_ground_truth_baseline()
    if df.empty:
        g_stock = baseline.get('global_stock', {})
        q_upper = query_str.strip().upper()
        matches = []
        for pno, item in g_stock.items():
            if q_upper in pno or q_upper in item['item_desc'].upper() or q_upper in item['category'].upper():
                matches.append({
                    'part_no': pno,
                    'part_name': item['item_desc'],
                    'brand': item['brand'],
                    'category': item['category'],
                    'capacity': item['capacity'],
                    'bal_qty': item['bal_qty'],
                    'price': item['stock_cost']
                })
                if len(matches) >= limit:
                    break
        if matches:
            df = pd.DataFrame(matches)
            
    if not df.empty:
        price_book = baseline.get('price_book', {})
        floors = baseline.get('category_floors', {})
        from config import classify_component_role
        
        def resolve_price(r):
            pr = int(r.get('price') or 0)
            if pr > 0:
                return pr
            pno = str(r['part_no']).upper()
            if pno in price_book and price_book[pno].get('price', 0) > 0:
                return int(price_book[pno]['price'])
            role = classify_component_role(r['part_name'])
            return int(floors.get(role, 1500))
            
        df['price'] = df.apply(resolve_price, axis=1)
            
    return df

def get_stock_metadata():
    init_db_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*), SUM(CASE WHEN bal_qty > 0 THEN 1 ELSE 0 END), MAX(last_synced) FROM stock_master")
        row = cursor.fetchone()
        if row and row[0] > 0:
            return {
                'total_items': row[0] or 0,
                'in_stock_items': row[1] or 0,
                'last_synced': row[2] or 'Synced'
            }
            
    baseline = load_ground_truth_baseline()
    g_stock = baseline.get('global_stock', {})
    tot = len(g_stock)
    in_stk = sum(1 for it in g_stock.values() if it.get('bal_qty', 0) > 0)
    return {
        'total_items': tot,
        'in_stock_items': in_stk,
        'last_synced': baseline.get('generated_at', 'Bundled Baseline')
    }

def search_history_records(query_str, clean_phone_str):
    with get_connection() as conn:
        sql = """
            SELECT complaint_no, model, serial, customer_name, phone, technician_name,
                   complaint_type, purchase_date, complaint_date, closed_date, remarks, closed_amount
            FROM history_master
            WHERE serial LIKE ? 
               OR complaint_no LIKE ? 
               OR (phone != '' AND phone LIKE ?)
            ORDER BY closed_date DESC LIMIT 30
        """
        match_df = pd.read_sql_query(sql, conn, params=(
            f"%{query_str}%", 
            f"%{query_str}%", 
            f"%{clean_phone_str if clean_phone_str else query_str}%"
        ))
    return match_df

def fetch_performance_data():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='tech_performance_master'")
        if cursor.fetchone()[0] == 0:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM tech_performance_master", conn)