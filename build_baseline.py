# build_baseline.py
import os
import re
import json
import pandas as pd
from datetime import datetime
from config import (
    classify_component_role, get_role_price_floor, tokenize_appliance_model,
    is_valve_tonnage_compatible, get_tonnage_valve_pairing,
    DEFAULT_FB_FILE, DEFAULT_COLL_FILE
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FB_FILE = DEFAULT_FB_FILE
COLL_FILE = DEFAULT_COLL_FILE
OFFICIAL_CATALOG_FILE = os.path.join(BASE_DIR, "data", "pdf_extracted_stock_report.csv")
STOCK_FILE = os.path.join(BASE_DIR, "data", "stock_inventory_latest.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "ground_truth_baseline.json")

def clean_str(v):
    if pd.isna(v) or v is None:
        return ""
    s = str(v).strip().replace('=', '').replace('"', '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s

def classify_role(part_name, part_no=""):
    return classify_component_role(part_name, part_no)

def tokenize_model(m_str):
    return tokenize_appliance_model(m_str)

def main():
    print("Starting Ground-Truth Baseline Indexer...")
    print("Reading Official Master Catalog File (Authority 1):", OFFICIAL_CATALOG_FILE)
    cat_df = pd.read_csv(OFFICIAL_CATALOG_FILE)
    catalog_parts_master = {}
    catalog_model_parts = {}
    raw_stock_dict = {}

    def normalize_desc(s):
        val = clean_str(s)
        val = re.sub(r'\b(GS|GF|ES|EF|EW|GR|GW|WD|CX|EM)-\s+([0-9A-Za-z])', r'\1-\2', val)
        return re.sub(r'\s+', ' ', val).strip()

    sec_stocks = {}
    if os.path.exists(STOCK_FILE):
        try:
            s_df = pd.read_csv(STOCK_FILE)
            for _, r in s_df.iterrows():
                p = clean_str(r.get('PART_NO')).upper()
                b = int(pd.to_numeric(r.get('BAL_QTY', 0), errors='coerce') or 0)
                if p and b > 0:
                    sec_stocks[p] = b
        except Exception:
            pass

    for _, r in cat_df.iterrows():
        pno = clean_str(r.get('part_no')).upper()
        if not pno:
            continue
        p_price = int(round(float(pd.to_numeric(r.get('pdf_price', 0), errors='coerce') or 0)))
        t_stock = int(pd.to_numeric(r.get('total_stock', 0), errors='coerce') or 0)
        if t_stock <= 0 and pno in sec_stocks:
            t_stock = sec_stocks[pno]
        p_desc = normalize_desc(r.get('item_desc'))
        p_model = clean_str(r.get('model')).upper()
        page_no = int(pd.to_numeric(r.get('page', 1), errors='coerce') or 1)

        # Consolidate duplicate entries across bin locations
        if pno in catalog_parts_master:
            existing = catalog_parts_master[pno]
            existing['price'] = max(existing['price'], p_price)
            existing['bal_qty'] = existing['bal_qty'] + max(0, t_stock)
            if existing['bal_qty'] <= 0 and pno in sec_stocks:
                existing['bal_qty'] = sec_stocks[pno]
            if len(p_desc) > len(existing['item_desc']):
                existing['item_desc'] = p_desc
            if p_model and len(p_model) > 1 and not p_model.startswith('GASR-'):
                catalog_model_parts.setdefault(p_model, []).append(pno)
        else:
            tok = tokenize_appliance_model(p_model if p_model else p_desc)
            catalog_parts_master[pno] = {
                'part_no': pno,
                'item_desc': p_desc,
                'model': p_model,
                'brand': tok['brand'],
                'category': tok['category'],
                'capacity': tok['tonnage'],
                'bal_qty': t_stock,
                'price': p_price,
                'page': page_no
            }
            if p_model and len(p_model) > 1 and not p_model.startswith('GASR-'):
                catalog_model_parts.setdefault(p_model, []).append(pno)

        raw_stock_dict[pno] = {
            'part_no': pno,
            'item_desc': catalog_parts_master[pno]['item_desc'],
            'brand': catalog_parts_master[pno]['brand'],
            'category': catalog_parts_master[pno]['category'],
            'capacity': catalog_parts_master[pno]['capacity'],
            'bal_qty': catalog_parts_master[pno]['bal_qty'],
            'stock_cost': catalog_parts_master[pno]['price']
        }
    print(f"Loaded {len(catalog_parts_master)} unique parts from Master Price Authority (vp786.pdf).")

    # Ingest secondary items from stock_inventory_latest.csv (e.g. LED TVs, Microwave Ovens)
    if os.path.exists(STOCK_FILE):
        sec_df = pd.read_csv(STOCK_FILE)
        for _, r in sec_df.iterrows():
            pno = clean_str(r.get('PART_NO')).upper()
            if not pno or pno in raw_stock_dict:
                continue
            bal = int(pd.to_numeric(r.get('BAL_QTY', 0), errors='coerce') or 0)
            raw_stock_dict[pno] = {
                'part_no': pno,
                'item_desc': clean_str(r.get('ITEM_DESC')),
                'brand': clean_str(r.get('BRAND')),
                'category': clean_str(r.get('CATEGORY')),
                'capacity': clean_str(r.get('CAPACITY')),
                'bal_qty': bal,
                'stock_cost': 0  # Permanently discard AMOUNT / BAL_QTY ledger calculation
            }
        print(f"Total unified stock parts (Catalog + Secondary): {len(raw_stock_dict)}")

    print("Reading Collection File:", COLL_FILE)
    coll_df = pd.read_excel(COLL_FILE)
    coll_df['c_no'] = coll_df['Complaint No'].apply(clean_str)
    p_cash = pd.to_numeric(coll_df.get('Part Cash', 0), errors='coerce').fillna(0)
    p_warr = pd.to_numeric(coll_df.get('Part Warranty', 0), errors='coerce').fillna(0)
    coll_df['eff_price'] = p_cash.where(p_cash > 0, p_warr).astype(int)
    coll_map = coll_df[coll_df['eff_price'] > 0].set_index('c_no')['eff_price'].to_dict()
    print(f"Loaded {len(coll_map)} collection transactions with positive pricing.")

    print("Reading Quality Feedback Report:", FB_FILE)
    fb_df = pd.read_csv(FB_FILE, low_memory=False)
    print(f"Loaded {len(fb_df)} feedback complaint records.")

    exact_part_price_map = {}
    model_part_price_map = {}
    model_part_canonical_names = {}
    model_replacements = {}
    part_canonical_names = {}
    multi_part_complaints = []

    for _, r in fb_df.iterrows():
        cno = clean_str(r.get('COMPLAINT_NO'))
        m_raw = clean_str(r.get('MODEL_NAME')).upper()
        pnos_str = clean_str(r.get('HARDWARE_PART_NOS'))
        prods_str = clean_str(r.get('HARDWARE_PRODUCTS'))
        
        if not m_raw or not pnos_str or pnos_str.lower() == 'nan':
            continue
            
        p_list = [clean_str(x).upper() for x in pnos_str.split(',') if clean_str(x)]
        pr_list = [clean_str(x) for x in prods_str.split(',') if clean_str(x)]
        
        if len(p_list) == 1 and cno in coll_map:
            pno = p_list[0]
            pr = coll_map[cno]
            if pno not in exact_part_price_map:
                exact_part_price_map[pno] = []
            exact_part_price_map[pno].append(pr)
            
            m_key = (m_raw, pno)
            if m_key not in model_part_price_map:
                model_part_price_map[m_key] = []
            model_part_price_map[m_key].append(pr)
        elif len(p_list) > 1 and cno in coll_map:
            multi_part_complaints.append((cno, m_raw, p_list, pr_list, coll_map[cno]))
            
        if m_raw not in model_replacements:
            model_replacements[m_raw] = {}
            
        for idx, pno in enumerate(p_list):
            pname = pr_list[idx] if idx < len(pr_list) else "Component Hardware"
            if pno not in part_canonical_names or len(pname) > len(part_canonical_names[pno]):
                part_canonical_names[pno] = pname
                
            m_key = (m_raw, pno)
            if m_key not in model_part_canonical_names or len(pname) > len(model_part_canonical_names[m_key]):
                model_part_canonical_names[m_key] = pname
                
            if pno not in model_replacements[m_raw]:
                model_replacements[m_raw][pno] = {'count': 0, 'name': pname}
            model_replacements[m_raw][pno]['count'] += 1
            if len(pname) > len(model_replacements[m_raw][pno]['name']):
                model_replacements[m_raw][pno]['name'] = pname

    # Seed all designated models from Master Price Catalog into model_replacements
    for c_model, pno_list in catalog_model_parts.items():
        if c_model not in model_replacements:
            model_replacements[c_model] = {}
        for pno in pno_list:
            if pno not in model_replacements[c_model]:
                p_desc = catalog_parts_master.get(pno, {}).get('item_desc', 'Component Hardware')
                model_replacements[c_model][pno] = {
                    'count': 0,
                    'name': p_desc
                }

    part_verified_prices = {}
    for pno, pr_list in exact_part_price_map.items():
        s = pd.Series(pr_list)
        part_verified_prices[pno] = int(s.mode()[0]) if not s.mode().empty else int(s.median())

    model_part_verified_prices = {}
    for (m_key, pno), pr_list in model_part_price_map.items():
        s = pd.Series(pr_list)
        model_part_verified_prices[(m_key, pno)] = int(s.mode()[0]) if not s.mode().empty else int(s.median())

    # Authority 1: Master Price Authority establishes official retail prices for all 518 parts
    for pno, c_item in catalog_parts_master.items():
        part_verified_prices[pno] = c_item['price']

    # Multi-Part Deduction Pass (e.g. Evap + Valves combined jobs like GF-36TFIH 282629821)
    for _ in range(3):
        for cno, m_raw, p_list, pr_list, total_eff in multi_part_complaints:
            unknown_indices = []
            known_sum = 0
            for i, p in enumerate(p_list):
                p_price = model_part_verified_prices.get((m_raw, p), 0) or part_verified_prices.get(p, 0)
                if p_price > 0:
                    known_sum += p_price
                else:
                    unknown_indices.append(i)
                    
            if len(unknown_indices) == 1:
                idx = unknown_indices[0]
                target_pno = p_list[idx]
                residual = total_eff - known_sum
                if residual > 0:
                    m_key = (m_raw, target_pno)
                    if m_key not in model_part_price_map:
                        model_part_price_map[m_key] = []
                    model_part_price_map[m_key].append(residual)
                    
                    if target_pno not in exact_part_price_map:
                        exact_part_price_map[target_pno] = []
                    exact_part_price_map[target_pno].append(residual)
                    
                    s_m = pd.Series(model_part_price_map[m_key])
                    model_part_verified_prices[m_key] = int(s_m.mode()[0]) if not s_m.mode().empty else int(s_m.median())
                    
                    s_g = pd.Series(exact_part_price_map[target_pno])
                    if target_pno not in catalog_parts_master:
                        part_verified_prices[target_pno] = int(s_g.mode()[0]) if not s_g.mode().empty else int(s_g.median())

    print(f"Verified {len(part_verified_prices)} parts globally, and {len(model_part_verified_prices)} exact (model, part) rates.")

    # Standardize stock inventory unit prices with collection prices & role price floors
    stock_dict = {}
    for pno, s_item in raw_stock_dict.items():
        desc = s_item['item_desc']
        role = classify_role(desc, pno)
        item_ton = s_item.get('capacity') or "1.5 Ton"
        desc_up = desc.upper()
        if not item_ton or item_ton == "1.5 Ton":
            for t_str, token in [('4.0 Ton', '48'), ('3.0 Ton', '36'), ('2.0 Ton', '24'), ('1.0 Ton', '12'), ('1.5 Ton', '18')]:
                if token in desc_up:
                    item_ton = t_str
                    break
        floor = get_role_price_floor(role, item_ton, s_item.get('category', 'Split AC'))
        raw_cost = s_item['stock_cost']

        if pno in catalog_parts_master and catalog_parts_master[pno]['price'] > 0:
            unit_pr = catalog_parts_master[pno]['price']
        elif pno in part_verified_prices and part_verified_prices[pno] > 0:
            unit_pr = part_verified_prices[pno]
        elif raw_cost > 0:
            if raw_cost < floor:
                unit_pr = floor
            elif raw_cost > 100000 and role not in ["Compressor & Fittings"]:
                unit_pr = floor
            else:
                unit_pr = raw_cost
        else:
            unit_pr = floor

        s_copy = dict(s_item)
        s_copy['stock_cost'] = unit_pr
        s_copy['unit_price'] = unit_pr
        s_copy['role'] = role
        stock_dict[pno] = s_copy

    ground_truth_catalog = {}
    series_catalog = {}

    for m_raw, parts_dict in model_replacements.items():
        tok = tokenize_model(m_raw)
        series_key = tok['series_key']
        
        if series_key not in series_catalog:
            series_catalog[series_key] = {}
            
        model_parts_list = []
        
        for pno, info in parts_dict.items():
            role = classify_role(info['name'], pno)
            cnt = info['count']
            
            stk_info = stock_dict.get(pno, {})
            bal_qty = stk_info.get('bal_qty', 0)
            # Closed complaint field description is primary truth for this model:
            pname = info.get('name') or model_part_canonical_names.get((m_raw, pno)) or part_canonical_names.get(pno) or stk_info.get('item_desc') or "Component"
            
            # Strict Platform Series & Tonnage Contamination Filter:
            p_upper = pname.upper()
            is_chassis_sensitive = role in ['Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 'Display Board']
            conflicting = False
            
            if is_chassis_sensitive and 'COMMON' not in p_upper:
                # 1. Check conflicting series
                series_tokens = ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'FWITH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'ISH', 'FW', 'TF', 'CD', 'CB']
                found_series = [s for s in series_tokens if s in p_upper]
                if found_series and tok['series'] not in found_series and tok['series'] != "FLOOR":
                    conflicting = True
                    
                # 2. Check conflicting tonnage for chassis-sensitive components
                if not conflicting and tok['category'] in ['Split AC', 'Floor Standing AC']:
                    cap_tokens = re.findall(r'(?:GS-|GF-|ES-|EF-|\b)(10|11|12|16|18|24|26|36|48|60)(?=[A-Za-z]|\b|-)', p_upper)
                    if cap_tokens:
                        ton_map = {
                            '10': '1.0 Ton', '11': '1.0 Ton', '12': '1.0 Ton',
                            '16': '1.5 Ton', '18': '1.5 Ton',
                            '24': '2.0 Ton', '26': '2.0 Ton',
                            '36': '3.0 Ton',
                            '48': '4.0 Ton', '60': '4.0 Ton'
                        }
                        detected_tons = {ton_map[ct] for ct in cap_tokens if ct in ton_map}
                        if detected_tons and tok['tonnage'] not in detected_tons:
                            conflicting = True
            
            if conflicting:
                continue

            # Strict Tonnage Compatibility for Cut-Off and Service Valves:
            if not is_valve_tonnage_compatible(role, pname, tok['tonnage'], tok['category']):
                continue

            floor_price = get_role_price_floor(role, tok['tonnage'], tok['category'])
            m_key = (m_raw, pno)
            if pno in catalog_parts_master and catalog_parts_master[pno]['price'] > 0:
                final_price = catalog_parts_master[pno]['price']
            elif m_key in model_part_verified_prices and model_part_verified_prices[m_key] > 0:
                final_price = model_part_verified_prices[m_key]
            elif pno in part_verified_prices and part_verified_prices[pno] > 0:
                final_price = part_verified_prices[pno]
            elif pno in stock_dict and stock_dict[pno]['unit_price'] > 0:
                final_price = stock_dict[pno]['unit_price']
            else:
                final_price = floor_price
                
            part_record = {
                'part_no': pno,
                'part_name': pname,
                'role': role,
                'verified_jobs': cnt,
                'price': final_price,
                'bal_qty': bal_qty,
                'in_stock': bal_qty > 0
            }
            model_parts_list.append(part_record)
            
            if pno not in series_catalog[series_key]:
                series_catalog[series_key][pno] = part_record.copy()
            else:
                series_catalog[series_key][pno]['verified_jobs'] += cnt
                
        model_parts_list.sort(key=lambda x: (x['in_stock'], x['verified_jobs']), reverse=True)
        ground_truth_catalog[m_raw] = {
            'meta': tok,
            'parts': model_parts_list
        }

    series_token_list = ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'FWITH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'ISH', 'FW', 'TF', 'CD', 'CB']

    for pno, s_item in stock_dict.items():
        desc = s_item['item_desc'].upper()
        role = s_item['role']
        price = s_item['unit_price']
        bal_qty = s_item['bal_qty']
        in_stk = bal_qty > 0

        # Direct Model Attachment: If stock item explicitly names a model or model family
        for m_name, m_data in ground_truth_catalog.items():
            m_up = m_name.upper()
            m_parts = m_up.split('-')
            m_prefix = m_parts[0] + '-' + m_parts[1][:6] if len(m_parts) > 1 else m_up
            is_model_match = (m_up in desc) or (len(m_prefix) >= 7 and m_prefix in desc)

            if is_model_match:
                m_tok = m_data['meta']
                m_series = m_tok.get('series', '')
                is_chassis_sensitive = role in ['Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 'Display Board']

                # Reject if desc mentions a conflicting series
                if is_chassis_sensitive and m_series and 'COMMON' not in desc:
                    has_conflict = False
                    for st in series_token_list:
                        if st in desc and st != m_series and m_series not in desc:
                            has_conflict = True
                            break
                    if has_conflict:
                        continue

                # Reject if desc mentions a conflicting tonnage
                if is_chassis_sensitive and m_tok.get('category') in ['Split AC', 'Floor Standing AC']:
                    cap_tokens = re.findall(r'(?:GS-|GF-|ES-|EF-|\b)(10|11|12|16|18|24|26|36|48|60)(?=[A-Za-z]|\b|-)', desc)
                    if cap_tokens:
                        ton_map = {
                            '10': '1.0 Ton', '11': '1.0 Ton', '12': '1.0 Ton',
                            '16': '1.5 Ton', '18': '1.5 Ton',
                            '24': '2.0 Ton', '26': '2.0 Ton',
                            '36': '3.0 Ton',
                            '48': '4.0 Ton', '60': '4.0 Ton'
                        }
                        detected_tons = {ton_map[ct] for ct in cap_tokens if ct in ton_map}
                        if detected_tons and m_tok.get('tonnage') not in detected_tons:
                            continue

                # Reject if valve is incompatible with model tonnage
                if not is_valve_tonnage_compatible(role, desc, m_tok.get('tonnage'), m_tok.get('category')):
                    continue

                existing_pnos = {p['part_no'] for p in m_data['parts']}
                if pno not in existing_pnos:
                    m_data['parts'].append({
                        'part_no': pno,
                        'part_name': s_item['item_desc'],
                        'role': role,
                        'verified_jobs': 0,
                        'price': price,
                        'bal_qty': bal_qty,
                        'in_stock': in_stk
                    })

        # Series platform attachment
        for s in series_token_list:
            if s in desc:
                brand = s_item['brand'] or "Gree"
                cat = s_item['category'] or "Split AC"
                ton = "1.5 Ton"
                for t_str, token in [('4.0 Ton', '48'), ('3.0 Ton', '36'), ('2.0 Ton', '24'), ('1.0 Ton', '12'), ('1.5 Ton', '18')]:
                    if token in desc:
                        ton = t_str
                        break
                
                # Reject if valve is incompatible with series tonnage
                if not is_valve_tonnage_compatible(role, desc, ton, cat):
                    continue

                s_key = f"{brand}|{cat}|{ton}|{s}"
                if s_key not in series_catalog:
                    series_catalog[s_key] = {}
                if pno not in series_catalog[s_key]:
                    series_catalog[s_key][pno] = {
                        'part_no': pno,
                        'part_name': s_item['item_desc'],
                        'role': role,
                        'verified_jobs': 0,
                        'price': price,
                        'bal_qty': bal_qty,
                        'in_stock': in_stk
                    }

    # Universal In-Stock Warehouse Valve Attachment for AC models
    standard_valve_pairings = {
        '1.0 Ton': [
            ('71302395', "Cut-Off Valve (3/8\")", 'Cut-off valve 3/8 71302395 GS-12PITH1W/O'),
            ('7130239', "Cut-Off Valve (1/4\")", 'Cut-off Valve 1/4 7130239')
        ],
        '1.5 Ton': [
            ('7133774', "Cut-Off Valve (1/2\")", 'Cut Off Valve Assy 1/2 7133774 GS-18VITH1'),
            ('7130239', "Cut-Off Valve (1/4\")", 'Cut-off Valve 1/4 7130239')
        ],
        '2.0 Ton': [
            ('7133844', "Cut-Off Valve (5/8\")", 'Cutt Off Valve 5/8  24LITH11M 7133844'),
            ('7130239', "Cut-Off Valve (1/4\")", 'Cut off Valve 1/4 GS-11CITH3F  7130239')
        ],
        '3.0 Ton': [
            ('7133844', "Cut-Off Valve (5/8\")", 'Cutt Off Valve 5/8  24LITH11M 7133844'),
            ('7130239', "Cut-Off Valve (1/4\")", 'Cut off Valve 1/4 GS-11CITH3F  7130239')
        ],
        '4.0 Ton': [
            ('7133844', "Cut-Off Valve (5/8\")", 'Cutt Off Valve 5/8 24LITH11M 7133844'),
            ('71302395', "Cut-Off Valve (3/8\")", 'Cut-off valve 3/8 71302395 GS-12PITH1W/O')
        ],
        '5.0 Ton': [
            ('7133844', "Cut-Off Valve (5/8\")", 'Cutt Off Valve 5/8 24LITH11M 7133844'),
            ('71302395', "Cut-Off Valve (3/8\")", 'Cut-off valve 3/8 71302395 GS-12PITH1W/O')
        ]
    }

    for m_name, m_data in ground_truth_catalog.items():
        m_cat = m_data['meta'].get('category')
        m_ton = m_data['meta'].get('tonnage')
        if m_cat in ['Split AC', 'Floor Standing AC'] and m_ton in standard_valve_pairings:
            # Purge any incompatible valves
            m_data['parts'] = [
                p for p in m_data['parts']
                if is_valve_tonnage_compatible(p['role'], p['part_name'], m_ton, m_cat)
            ]
            existing_pnos = {p['part_no'] for p in m_data['parts']}
            for v_pno, v_role, v_name in standard_valve_pairings[m_ton]:
                dyn_price = catalog_parts_master.get(v_pno, {}).get('price', 0)
                if dyn_price <= 0:
                    dyn_price = part_verified_prices.get(v_pno, 0)
                if dyn_price <= 0:
                    dyn_price = stock_dict.get(v_pno, {}).get('unit_price', 0)
                if dyn_price <= 0:
                    dyn_price = get_role_price_floor(v_role, m_ton, m_cat)

                stk_info = stock_dict.get(v_pno, {})
                b_qty = stk_info.get('bal_qty', 15)

                if v_pno not in existing_pnos:
                    m_data['parts'].append({
                        'part_no': v_pno,
                        'part_name': v_name,
                        'role': v_role,
                        'price': dyn_price,
                        'bal_qty': b_qty,
                        'in_stock': b_qty > 0,
                        'verified_jobs': 50
                    })
                else:
                    for p in m_data['parts']:
                        if p['part_no'] == v_pno:
                            p['price'] = dyn_price

    for m_name, m_data in ground_truth_catalog.items():
        m_data['parts'].sort(
            key=lambda x: (
                x['in_stock'],
                x['verified_jobs'],
                0 if 'SUB ASSY' in str(x.get('part_name', '')).upper() else 1,
                x.get('bal_qty', 0)
            ),
            reverse=True
        )

    final_series_catalog = {}
    for s_key, parts_map in series_catalog.items():
        plist = list(parts_map.values())
        plist.sort(key=lambda x: (x['in_stock'], x['verified_jobs']), reverse=True)
        final_series_catalog[s_key] = plist

    # Price Book of all known parts
    price_book = {}
    for pno, c_item in catalog_parts_master.items():
        price_book[pno] = {
            'price': c_item['price'],
            'part_name': c_item['item_desc'],
            'role': classify_role(c_item['item_desc'], pno)
        }
    for pno, pr in part_verified_prices.items():
        pname = part_canonical_names.get(pno, stock_dict.get(pno, {}).get('item_desc', "Component"))
        if pno not in price_book:
            price_book[pno] = {
                'price': pr,
                'part_name': pname,
                'role': classify_role(pname, pno)
            }
    for pno, s_item in stock_dict.items():
        if pno not in price_book:
            price_book[pno] = {
                'price': s_item['unit_price'],
                'part_name': s_item['item_desc'],
                'role': s_item['role']
            }

    payload = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_models': len(ground_truth_catalog),
        'total_series_keys': len(final_series_catalog),
        'total_stock_parts': len(stock_dict),
        'models': ground_truth_catalog,
        'series': final_series_catalog,
        'global_stock': stock_dict,
        'price_book': price_book,
        'category_floors': {
            "Evaporator Assembly": 26000,
            "Outdoor Inverter PCB": 40000,
            "Indoor Main PCB": 6500,
            "Circuit Board (PCB)": 6500,
            "Compressor & Fittings": 38000,
            "Indoor Fan Motor": 2000,
            "Outdoor Fan Motor": 2500,
            "Fan Motor": 2000,
            "Stepping / Swing Motor": 1395,
            "Cut-Off Valve (1/4\")": 1600,
            "Cut-Off Valve (1/2\")": 2100,
            "Cut-Off Valve (3/8\")": 1500,
            "Cut-Off Valve (5/8\")": 2200,
            "Cut-Off Valve (3/8\" - 5/8\")": 1500,
            "4-Way Valve Assembly": 3500,
            "Temperature Sensor": 1500,
            "Capacitor": 900
        }
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

    print(f"SUCCESS: Baseline generated at {OUTPUT_FILE}")
    print(f"Models indexed: {len(ground_truth_catalog)}, Series indexed: {len(final_series_catalog)}, Price Book items: {len(price_book)}")

if __name__ == '__main__':
    main()
