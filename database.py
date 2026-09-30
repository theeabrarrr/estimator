# database.py
import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import sqlite3
import pandas as pd
import json
import re
from config import (
    DB_NAME, BASELINE_JSON_PATH, COMPONENT_ROLE_GROUPS,
    tokenize_appliance_model, classify_component_role,
    is_valve_tonnage_compatible, get_tonnage_valve_pairing
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_brand ON stock_master(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_parts_pno ON parts_master(part_no)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_parts_model ON parts_master(model)")

        cursor.execute("SELECT count(*) FROM stock_master WHERE last_synced = 'DWP Official Price Catalog (vp786.pdf)'")
        official_count = cursor.fetchone()[0]
        if official_count < 518:
            try:
                from etl import ingest_pdf_stock_catalog
                ingest_pdf_stock_catalog()
            except Exception:
                pass

        # Database hygiene: eliminate obsolete accounting ledger valuation residues
        cursor.execute("""
            UPDATE stock_master 
            SET amount = ROUND(unit_price * bal_qty, 2) 
            WHERE abs(amount - (unit_price * bal_qty)) > 0.01
        """)

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

def fetch_tiered_compatible_parts(selected_model, search_query: str = ""):
    init_db_schema()
    baseline = load_ground_truth_baseline()
    tok = tokenize_appliance_model(selected_model)
    model_name = tok['model']
    series_key = tok['series_key']
    price_book = baseline.get('price_book', {})
    
    # Live stock lookup dictionary from SQLite stock_master
    live_stock_map = {}
    with get_connection() as conn:
        stock_rows = pd.read_sql_query("SELECT part_no, bal_qty, unit_price FROM stock_master", conn)
        for _, sr in stock_rows.iterrows():
            live_stock_map[sr['part_no'].upper()] = {
                'bal_qty': int(sr['bal_qty']),
                'unit_price': int(sr['unit_price'])
            }

    def is_series_compatible(pname, target_series, target_tonnage, target_cat, role):
        if not target_series:
            return True
        pn = pname.upper()
        if 'COMMON' in pn or 'UNIVERSAL' in pn:
            return True
        chassis_sensitive = [
            'Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 
            'Display Board', 'Cross Flow Fan', 'Front Panel'
        ]
        tokens = ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'FWITH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'ISH', 'FW', 'TF', 'CD', 'CB']
        found = [s for s in tokens if s in pn]
        if found:
            if target_series in found:
                pass
            elif target_series == "FLOOR":
                pass
            elif role in chassis_sensitive:
                return False
                
        # Tonnage check for chassis sensitive cooling/electrical roles
        if role in chassis_sensitive and target_cat in ['Split AC', 'Floor Standing AC']:
            cap_tokens = re.findall(r'(?:GS-|GF-|ES-|EF-|\b)(10|11|12|16|18|24|26|36|48|60)(?=[A-Za-z]|\b|-)', pn)
            if cap_tokens:
                ton_map = {
                    '10': '1.0 Ton', '11': '1.0 Ton', '12': '1.0 Ton',
                    '16': '1.5 Ton', '18': '1.5 Ton',
                    '24': '2.0 Ton', '26': '2.0 Ton',
                    '36': '3.0 Ton',
                    '48': '4.0 Ton', '60': '4.0 Ton'
                }
                detected_tons = {ton_map[ct] for ct in cap_tokens if ct in ton_map}
                if detected_tons and target_tonnage not in detected_tons:
                    return False

        # Strict Tonnage Compatibility for Cut-off and Service Valves
        if not is_valve_tonnage_compatible(role, pname, target_tonnage, target_cat):
            return False

        return True

    cat_compat_map = {
        'Split AC': ['Split AC', 'SPLIT AC 2', 'T1 R410 DC Inverter Indoor Units'],
        'Floor Standing AC': ['Floor Standing AC'],
        'Refrigerator': ['Refrigerator'],
        'Washing Machine': ['Washing Machine', 'Spinner'],
        'Water Dispenser': ['Water Dispenser', 'Water Dispensor', 'Water Dispensors'],
        'LED TV': ['LED TV'],
        'Microwave Oven': ['Microwave Oven']
    }
    compat_cats = cat_compat_map.get(tok.get('category'), [tok.get('category', 'Split AC')])

    tier1_parts = []
    tier2_parts = []
    tier3_parts = []
    seen_part_nos = set()
    total_verified_jobs = 0

    # 1. Tier 1: Exact Model Match (Ground Truth Catalog & Field Complaints)
    t1_records = baseline.get('models', {}).get(model_name, {}).get('parts', [])
    for p in t1_records:
        if not is_series_compatible(p['part_name'], tok['series'], tok['tonnage'], tok['category'], p['role']):
            continue
        p_copy = p.copy()
        pno = p['part_no'].upper()
        if pno in live_stock_map:
            p_copy['bal_qty'] = live_stock_map[pno]['bal_qty']
            p_copy['in_stock'] = p_copy['bal_qty'] > 0
            if live_stock_map[pno]['unit_price'] > 0:
                p_copy['price'] = live_stock_map[pno]['unit_price']
            
        if p_copy.get('price', 0) <= 0:
            if pno in price_book and price_book[pno].get('price', 0) > 0:
                p_copy['price'] = int(price_book[pno]['price'])
            elif pno in live_stock_map and live_stock_map[pno]['unit_price'] > 0:
                p_copy['price'] = live_stock_map[pno]['unit_price']
                
        if p_copy.get('price', 0) <= 0:
            p_copy['price'] = baseline.get('category_floors', {}).get(p['role'], 26000 if 'Evaporator' in p['role'] else 1500)
                
        p_copy['tier'] = "Tier 1: Exact Model Verified"
        p_copy['tier_code'] = 1
        p_copy['score'] = (p['verified_jobs'] * 2) + (10 if p_copy.get('in_stock', False) else 0) + 20
        tier1_parts.append(p_copy)
        seen_part_nos.add(pno)
        total_verified_jobs += p.get('verified_jobs', 0)

    # 1b. Direct Stock Model Matches (Live stock referencing this model specifically)
    m_clean = model_name.upper().replace('=', '').replace('"', '').strip()
    m_parts = m_clean.split('-')
    m_prefix = m_parts[0] + '-' + m_parts[1][:6] if len(m_parts) > 1 else m_clean

    with get_connection() as conn:
        cat_placeholders = ','.join('?' for _ in compat_cats)
        direct_stk_sql = f"""
            SELECT part_no, item_desc as part_name, category, bal_qty, unit_price as price
            FROM stock_master
            WHERE (UPPER(item_desc) LIKE ? OR (length(?) >= 7 AND UPPER(item_desc) LIKE ?))
              AND category IN ({cat_placeholders})
        """
        direct_params = [f"%{m_clean}%", m_prefix, f"%{m_prefix}%"] + compat_cats
        stk_matches = pd.read_sql_query(direct_stk_sql, conn, params=direct_params)

    for _, sr in stk_matches.iterrows():
        pno = sr['part_no'].upper()
        if pno not in seen_part_nos:
            p_desc = sr['part_name']
            role = classify_component_role(p_desc, pno)
            if not is_series_compatible(p_desc, tok['series'], tok['tonnage'], tok['category'], role):
                continue
            pr = int(sr['price'])
            if pno in price_book and price_book[pno].get('price', 0) > 0:
                pr = int(price_book[pno]['price'])
            elif pno in live_stock_map and live_stock_map[pno]['unit_price'] > 0:
                pr = live_stock_map[pno]['unit_price']
            if pr <= 0:
                pr = baseline.get('category_floors', {}).get(role, 26000 if 'Evaporator' in role else 1500)
            
            b_qty = int(sr['bal_qty'])
            p_record = {
                'part_no': pno,
                'part_name': p_desc,
                'role': role,
                'verified_jobs': 0,
                'price': pr,
                'bal_qty': b_qty,
                'in_stock': b_qty > 0,
                'tier': f"Tier 1: Stock Inventory ({tok['series']})" if tok.get('series') and tok['series'] != 'STANDARD' else "Tier 1: Stock Inventory",
                'tier_code': 1,
                'score': (10 if b_qty > 0 else 0) + 15
            }
            tier1_parts.append(p_record)
            seen_part_nos.add(pno)

    # 2. Tier 2: Strict Platform Series Match (Same series & capacity)
    series_records = baseline.get('series', {}).get(series_key, [])
    for p in series_records:
        if not is_series_compatible(p['part_name'], tok['series'], tok['tonnage'], tok['category'], p['role']):
            continue
        pno = p['part_no'].upper()
        if pno not in seen_part_nos:
            p_copy = p.copy()
            if pno in live_stock_map:
                p_copy['bal_qty'] = live_stock_map[pno]['bal_qty']
                p_copy['in_stock'] = p_copy['bal_qty'] > 0
                if live_stock_map[pno]['unit_price'] > 0:
                    p_copy['price'] = live_stock_map[pno]['unit_price']
                
            if p_copy.get('price', 0) <= 0:
                if pno in price_book and price_book[pno].get('price', 0) > 0:
                    p_copy['price'] = int(price_book[pno]['price'])
                elif pno in live_stock_map and live_stock_map[pno]['unit_price'] > 0:
                    p_copy['price'] = live_stock_map[pno]['unit_price']
                    
            if p_copy.get('price', 0) <= 0:
                p_copy['price'] = baseline.get('category_floors', {}).get(p['role'], 26000 if 'Evaporator' in p['role'] else 1500)
                    
            p_copy['tier'] = f"Tier 2: {tok['series']} Series Platform"
            p_copy['tier_code'] = 2
            p_copy['score'] = (p['verified_jobs'] * 2) + (10 if p_copy.get('in_stock', False) else 0) + 5
            tier2_parts.append(p_copy)
            seen_part_nos.add(pno)

    # 3. Tier 3: Store In-Stock Fallback Components (Live in-stock items with strict constraints)
    with get_connection() as conn:
        cat_placeholders = ','.join('?' for _ in compat_cats)
        t3_sql = f"""
            SELECT part_no, item_desc as part_name, category, bal_qty, unit_price as price
            FROM stock_master
            WHERE bal_qty > 0 AND category IN ({cat_placeholders})
        """
        t3_rows = pd.read_sql_query(t3_sql, conn, params=compat_cats)

    chassis_sensitive = [
        'Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 
        'Display Board', 'Cross Flow Fan', 'Front Panel'
    ]

    for _, sr in t3_rows.iterrows():
        pno = sr['part_no'].upper()
        if pno in seen_part_nos:
            continue
        p_desc = sr['part_name']
        role = classify_component_role(p_desc, pno)

        # Exclude non-functional packaging cartons/boxes from Tier 3
        if any(k in p_desc.lower() for k in ['carton', 'caton', 'packing', 'tray', 'box', 'foam']):
            continue

        # Chassis isolation: never leak chassis-sensitive components across platforms
        if role in chassis_sensitive:
            if not is_series_compatible(p_desc, tok['series'], tok['tonnage'], tok['category'], role):
                continue
            pn = p_desc.upper()
            if 'COMMON' not in pn and 'UNIVERSAL' not in pn and (not tok.get('series') or tok['series'] not in pn):
                continue

        # Physical valve line & capacity constraints for AC
        if tok.get('category') in ['Split AC', 'Floor Standing AC', 'Air Conditioner']:
            if 'valve' in p_desc.lower() or 'Valve' in role:
                if not is_valve_tonnage_compatible(role, p_desc, tok.get('tonnage'), tok.get('category')):
                    continue
        else:
            # Strict non-AC isolation: reject all AC valves and evaporators
            if 'valve' in p_desc.lower() and any(k in p_desc.lower() for k in ['cut-off', 'cutt off', '4-way', 'service']):
                continue
            if 'evaporator' in p_desc.lower() and tok.get('category') != 'Refrigerator':
                continue

        # Capacity-tagged consistency check for cooling/electrical items
        if tok.get('category') in ['Split AC', 'Floor Standing AC']:
            cap_tokens = re.findall(r'(?:GS-|GF-|ES-|EF-|\b)(10|11|12|16|18|24|26|36|48|60)(?=[A-Za-z]|\b|-)', p_desc.upper())
            if cap_tokens:
                ton_map = {
                    '10': '1.0 Ton', '11': '1.0 Ton', '12': '1.0 Ton',
                    '16': '1.5 Ton', '18': '1.5 Ton',
                    '24': '2.0 Ton', '26': '2.0 Ton',
                    '36': '3.0 Ton',
                    '48': '4.0 Ton', '60': '4.0 Ton'
                }
                detected = {ton_map[ct] for ct in cap_tokens if ct in ton_map}
                if detected and tok.get('tonnage') not in detected:
                    continue

        pr = int(sr['price'])
        if pno in price_book and price_book[pno].get('price', 0) > 0:
            pr = int(price_book[pno]['price'])
        elif pno in live_stock_map and live_stock_map[pno]['unit_price'] > 0:
            pr = live_stock_map[pno]['unit_price']
        if pr <= 0:
            pr = baseline.get('category_floors', {}).get(role, 26000 if 'Evaporator' in role else 1500)
            
        b_qty = int(sr['bal_qty'])
        p_record = {
            'part_no': pno,
            'part_name': p_desc,
            'role': role,
            'verified_jobs': 0,
            'price': pr,
            'bal_qty': b_qty,
            'in_stock': True,
            'tier': "Tier 3: Store In-Stock Fallback",
            'tier_code': 3,
            'score': 15
        }
        tier3_parts.append(p_record)
        seen_part_nos.add(pno)

    # Autonomous dynamic valve fallback for AC models from live stock_master
    if tok.get('category') in ['Split AC', 'Floor Standing AC', 'Air Conditioner']:
        suction_role, liquid_role = get_tonnage_valve_pairing(tok.get('tonnage'))
        VALVE_TONNAGE_PARTS = {
            '1.0 Ton': {'suction': '71302395', 'liquid': '7130239'},
            '1.5 Ton': {'suction': '7133774',  'liquid': '7130239'},
            '2.0 Ton': {'suction': '7133844',  'liquid': '7130239'},
            '3.0 Ton': {'suction': '7133844',  'liquid': '7130239'},
            '4.0 Ton': {'suction': '7133844',  'liquid': '71302395'},
            '5.0 Ton': {'suction': '7133844',  'liquid': '71302395'},
        }
        target_v_pair = VALVE_TONNAGE_PARTS.get(tok.get('tonnage'), {'suction': '7133774', 'liquid': '7130239'})
        for req_key, req_role in [('suction', suction_role), ('liquid', liquid_role)]:
            req_pno = target_v_pair[req_key]
            if req_pno not in seen_part_nos:
                with get_connection() as conn:
                    v_row = conn.execute("SELECT part_no, item_desc, bal_qty, unit_price FROM stock_master WHERE part_no = ?", (req_pno,)).fetchone()
                if v_row:
                    v_pno, v_desc, v_bal, v_pr = v_row
                    v_upr = int(v_pr)
                    if v_pno in price_book and price_book[v_pno].get('price', 0) > 0:
                        v_upr = int(price_book[v_pno]['price'])
                    v_rec = {
                        'part_no': v_pno,
                        'part_name': v_desc,
                        'role': req_role,
                        'verified_jobs': 50 if req_key == 'suction' else 25,
                        'price': v_upr,
                        'bal_qty': int(v_bal),
                        'in_stock': int(v_bal) > 0,
                        'tier': "Tier 3: Store In-Stock Fallback",
                        'tier_code': 3,
                        'score': 100 if req_key == 'suction' else 80
                    }
                    tier3_parts.append(v_rec)
                    seen_part_nos.add(req_pno)

    # Build Candidate Scored Parts
    scored_parts = tier1_parts + tier2_parts + tier3_parts

    if search_query and search_query.strip():
        sq = search_query.strip().upper()
        scored_parts = [p for p in scored_parts if sq in p['part_no'].upper() or sq in p['part_name'].upper() or sq in p['role'].upper()]

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
            
        if group_title == "🔩 Cut-off & Service Valves" and tok.get('category') in ['Split AC', 'Floor Standing AC', 'Air Conditioner']:
            suction_role, liquid_role = get_tonnage_valve_pairing(tok.get('tonnage'))
            # 1. Filter out any incompatible valve size for this tonnage
            matched_items = [
                it for it in matched_items 
                if is_valve_tonnage_compatible(it['role'], it['part_name'], tok.get('tonnage'), tok.get('category'))
            ]
            
            # 2. Clean pairing: Suction Valve MUST be Primary (#1), Liquid Valve MUST be Alternative (#2)
            suction_candidates = [it for it in matched_items if it['role'] == suction_role]
            liquid_candidates = [it for it in matched_items if it['role'] == liquid_role]
            
            suction_candidates.sort(key=lambda x: (x['in_stock'], x['score'], x['verified_jobs']), reverse=True)
            liquid_candidates.sort(key=lambda x: (x['in_stock'], x['score'], x['verified_jobs']), reverse=True)
            
            matched_items = []
            if suction_candidates:
                matched_items.append(suction_candidates[0])
            if liquid_candidates:
                matched_items.append(liquid_candidates[0])

        if not matched_items:
            continue
            
        # Deduplication & Ranking: Sort by Score descending (for other groups)
        if group_title != "🔩 Cut-off & Service Valves":
            matched_items.sort(
                key=lambda x: (
                    x['score'], 
                    x['in_stock'], 
                    x['verified_jobs'], 
                    0 if 'SUB ASSY' in str(x.get('part_name', '')).upper() else 1, 
                    x.get('bal_qty', 0)
                ), 
                reverse=True
            )
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
        'metadata': {
            **tok,
            'valve_pairing': get_tonnage_valve_pairing(tok.get('tonnage')) if tok.get('category') in ['Split AC', 'Floor Standing AC', 'Air Conditioner'] else None,
            'tier1_count': len(tier1_parts),
            'tier2_count': len(tier2_parts),
            'tier3_count': len(tier3_parts)
        },
        'tier1': tier1_parts,
        'tier2': tier2_parts,
        'tier3': tier3_parts,
        'compatible_parts': tier1_parts + tier2_parts + tier3_parts,
        'role_groups': structured_groups,
        'total_verified_jobs': total_verified_jobs,
        'total_parts_found': len(tier1_parts) + len(tier2_parts) + len(tier3_parts)
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
            role = classify_component_role(r['part_name'], pno)
            floor = int(floors.get(role, 26000 if 'Evaporator' in role else 1500))
            if pr <= 0 or pr < floor:
                return floor
            if pr > 100000 and role not in ["Compressor & Fittings"]:
                return floor
            return pr
            
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