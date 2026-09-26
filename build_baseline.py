# build_baseline.py
import os
import re
import json
import pandas as pd
from datetime import datetime
from config import (
    classify_component_role, get_role_price_floor, tokenize_appliance_model,
    is_valve_tonnage_compatible, get_tonnage_valve_pairing
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FB_FILE = os.path.join(BASE_DIR, "quality_feedback_report_14SEP2026_170840.csv")
COLL_FILE = os.path.join(BASE_DIR, "Detail_Collection_14SEP26_052528PM.xlsx")
STOCK_FILE = os.path.join(BASE_DIR, "data", "stock_inventory_latest.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "ground_truth_baseline.json")

def clean_str(v):
    if pd.isna(v) or v is None:
        return ""
    return str(v).strip().replace('=', '').replace('"', '').strip()

def classify_role(part_name, part_no=""):
    return classify_component_role(part_name, part_no)

def tokenize_model(m_str):
    return tokenize_appliance_model(m_str)

def main():
    print("Starting Ground-Truth Baseline Indexer...")
    print("Reading Stock File:", STOCK_FILE)
    stock_df = pd.read_csv(STOCK_FILE)
    raw_stock_dict = {}
    for _, r in stock_df.iterrows():
        pno = clean_str(r.get('PART_NO')).upper()
        if not pno:
            continue
        bal = int(pd.to_numeric(r.get('BAL_QTY', 0), errors='coerce') or 0)
        amt = float(pd.to_numeric(r.get('AMOUNT', 0), errors='coerce') or 0.0)
        unit_calc = int(round(amt / bal)) if (bal > 0 and amt > 0) else 0
        raw_stock_dict[pno] = {
            'part_no': pno,
            'item_desc': clean_str(r.get('ITEM_DESC')),
            'brand': clean_str(r.get('BRAND')),
            'category': clean_str(r.get('CATEGORY')),
            'capacity': clean_str(r.get('CAPACITY')),
            'bal_qty': bal,
            'stock_cost': unit_calc
        }
    print(f"Loaded {len(raw_stock_dict)} items from Stock Inventory.")

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
    model_replacements = {}
    part_canonical_names = {}

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
            
        if m_raw not in model_replacements:
            model_replacements[m_raw] = {}
            
        for idx, pno in enumerate(p_list):
            pname = pr_list[idx] if idx < len(pr_list) else "Component Hardware"
            if pno not in part_canonical_names or len(pname) > len(part_canonical_names[pno]):
                part_canonical_names[pno] = pname
                
            if pno not in model_replacements[m_raw]:
                model_replacements[m_raw][pno] = {'count': 0, 'name': pname}
            model_replacements[m_raw][pno]['count'] += 1

    part_verified_prices = {}
    for pno, pr_list in exact_part_price_map.items():
        s = pd.Series(pr_list)
        part_verified_prices[pno] = int(s.mode()[0]) if not s.mode().empty else int(s.median())

    print(f"Verified {len(part_verified_prices)} parts with exact collection prices.")

    # Standardize stock inventory unit prices with collection prices & role price floors
    stock_dict = {}
    for pno, s_item in raw_stock_dict.items():
        desc = s_item['item_desc']
        role = classify_role(desc, pno)
        item_ton = s_item.get('capacity') or "1.5 Ton"
        desc_up = desc.upper()
        if not item_ton or item_ton == "1.5 Ton":
            for t_str, token in [('4.0 Ton', '48'), ('4.0 Ton', '36'), ('2.0 Ton', '24'), ('1.0 Ton', '12'), ('1.5 Ton', '18')]:
                if token in desc_up:
                    item_ton = t_str
                    break
        floor = get_role_price_floor(role, item_ton, s_item.get('category', 'Split AC'))
        raw_cost = s_item['stock_cost']

        if pno in part_verified_prices and part_verified_prices[pno] > 0:
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
            pname = stk_info.get('item_desc') or info['name'] or part_canonical_names.get(pno, "Component")
            
            # Strict Platform Series & Tonnage Contamination Filter:
            p_upper = pname.upper()
            is_chassis_sensitive = role in ['Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 'Display Board']
            conflicting = False
            
            if is_chassis_sensitive and 'COMMON' not in p_upper:
                # 1. Check conflicting series
                for s in ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'LM', 'ECH', 'CM', 'CZ']:
                    if s in p_upper and s != tok['series'] and tok['series'] not in p_upper:
                        conflicting = True
                        break
                # 2. Check conflicting tonnage for chassis-sensitive components
                if not conflicting and tok['category'] in ['Split AC', 'Floor Standing AC']:
                    t_markers = {'1.0 Ton': ['12', '10', '11'], '1.5 Ton': ['18', '16'], '2.0 Ton': ['24', '26'], '4.0 Ton': ['36', '48', '60']}
                    target_ton = tok['tonnage']
                    other_markers = []
                    for ton_name, markers in t_markers.items():
                        if ton_name != target_ton:
                            other_markers.extend(markers)
                    target_markers = t_markers.get(target_ton, [])
                    if any(m in p_upper for m in other_markers) and not any(m in p_upper for m in target_markers):
                        conflicting = True
            
            if conflicting:
                continue

            # Strict Tonnage Compatibility for Cut-Off and Service Valves:
            if not is_valve_tonnage_compatible(role, pname, tok['tonnage'], tok['category']):
                continue

            floor_price = get_role_price_floor(role, tok['tonnage'], tok['category'])
            if pno in part_verified_prices and part_verified_prices[pno] > 0:
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

    series_token_list = ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'TF', 'CD', 'CB']

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
                    t_markers = {'1.0 Ton': ['12', '10', '11'], '1.5 Ton': ['18', '16'], '2.0 Ton': ['24', '26'], '4.0 Ton': ['36', '48', '60']}
                    target_ton = m_tok.get('tonnage')
                    other_markers = []
                    for ton_name, markers in t_markers.items():
                        if ton_name != target_ton:
                            other_markers.extend(markers)
                    target_markers = t_markers.get(target_ton, [])
                    if any(m in desc for m in other_markers) and not any(m in desc for m in target_markers):
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
                for t_str, token in [('4.0 Ton', '48'), ('4.0 Ton', '36'), ('2.0 Ton', '24'), ('1.0 Ton', '12'), ('1.5 Ton', '18')]:
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
    warehouse_stock_valves = {
        '1.0 Ton': [
            {'part_no': '71302395', 'role': "Cut-Off Valve (3/8\")", 'part_name': 'Cut-off valve 3/8 71302395 GS-12PITH1W/O', 'price': 2400, 'bal_qty': 15, 'in_stock': True, 'verified_jobs': 100},
            {'part_no': '7130239', 'role': "Cut-Off Valve (1/4\")", 'part_name': 'Cut-off Valve 1/4 7130239', 'price': 1600, 'bal_qty': 15, 'in_stock': True, 'verified_jobs': 50}
        ],
        '1.5 Ton': [
            {'part_no': '7133774', 'role': "Cut-Off Valve (1/2\")", 'part_name': 'Cut Off Valve Assy 1/2 7133774 GS-18VITH1', 'price': 2100, 'bal_qty': 20, 'in_stock': True, 'verified_jobs': 100},
            {'part_no': '7130239', 'role': "Cut-Off Valve (1/4\")", 'part_name': 'Cut-off Valve 1/4 7130239', 'price': 1600, 'bal_qty': 15, 'in_stock': True, 'verified_jobs': 50}
        ],
        '2.0 Ton': [
            {'part_no': '7133844', 'role': "Cut-Off Valve (5/8\")", 'part_name': 'Cutt Off Valve 5/8 24LITH11M 7133844', 'price': 2800, 'bal_qty': 5, 'in_stock': True, 'verified_jobs': 100},
            {'part_no': '7130239', 'role': "Cut-Off Valve (1/4\")", 'part_name': 'Cut-off Valve 1/4 7130239', 'price': 1600, 'bal_qty': 15, 'in_stock': True, 'verified_jobs': 50}
        ],
        '3.0 Ton': [
            {'part_no': '7133844', 'role': "Cut-Off Valve (5/8\")", 'part_name': 'Cutt Off Valve 5/8 24LITH11M 7133844', 'price': 2800, 'bal_qty': 5, 'in_stock': True, 'verified_jobs': 100},
            {'part_no': '7130239', 'role': "Cut-Off Valve (1/4\")", 'part_name': 'Cut-off Valve 1/4 7130239', 'price': 1600, 'bal_qty': 15, 'in_stock': True, 'verified_jobs': 50}
        ],
        '4.0 Ton': [
            {'part_no': '7133844', 'role': "Cut-Off Valve (5/8\")", 'part_name': 'Cutt Off Valve 5/8 24LITH11M 7133844', 'price': 3200, 'bal_qty': 5, 'in_stock': True, 'verified_jobs': 100},
            {'part_no': '71302395', 'role': "Cut-Off Valve (3/8\")", 'part_name': 'Cut-off valve 3/8 71302395 GS-12PITH1W/O', 'price': 2400, 'bal_qty': 15, 'in_stock': True, 'verified_jobs': 50}
        ]
    }

    for m_name, m_data in ground_truth_catalog.items():
        m_cat = m_data['meta'].get('category')
        m_ton = m_data['meta'].get('tonnage')
        if m_cat in ['Split AC', 'Floor Standing AC'] and m_ton in warehouse_stock_valves:
            # Purge any incompatible valves
            m_data['parts'] = [
                p for p in m_data['parts']
                if is_valve_tonnage_compatible(p['role'], p['part_name'], m_ton, m_cat)
            ]
            existing_pnos = {p['part_no'] for p in m_data['parts']}
            for v_item in warehouse_stock_valves[m_ton]:
                if v_item['part_no'] not in existing_pnos:
                    m_data['parts'].append(v_item.copy())

    final_series_catalog = {}
    for s_key, parts_map in series_catalog.items():
        plist = list(parts_map.values())
        plist.sort(key=lambda x: (x['in_stock'], x['verified_jobs']), reverse=True)
        final_series_catalog[s_key] = plist

    # Price Book of all known parts
    price_book = {}
    for pno, pr in part_verified_prices.items():
        pname = part_canonical_names.get(pno, stock_dict.get(pno, {}).get('item_desc', "Component"))
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
            "Cut-Off Valve (3/8\")": 2400,
            "Cut-Off Valve (5/8\")": 2600,
            "Cut-Off Valve (3/8\" - 5/8\")": 2600,
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
