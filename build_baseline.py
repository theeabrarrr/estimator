# build_baseline.py
import os
import re
import json
import pandas as pd
from datetime import datetime

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
    nl = (str(part_name) + " " + str(part_no)).lower()
    
    if any(k in nl for k in ['evap', 'evaporator', 'indoor coil']):
        return "Evaporator Assembly"
    elif any(k in nl for k in ['outdoor pcb', 'pcb odu', 'odu pcb', 'inverter board', 'outdoor board', 'pcb outdoor', '300027', '11222031']):
        return "Outdoor Inverter PCB"
    elif any(k in nl for k in ['indoor main board', 'main board indoor', 'pcb idu', 'indoor pcb', 'pcb indoor', 'display board', '300002', '300001']):
        return "Indoor Main PCB"
    elif any(k in nl for k in ['pcb', 'board', 'circuit']):
        return "Circuit Board (PCB)"
    elif any(k in nl for k in ['compressor']):
        return "Compressor & Fittings"
    elif any(k in nl for k in ['step motor', 'stepping motor', 'swing motor', 'mp24', '1521212', '1521210']):
        return "Stepping / Swing Motor"
    elif any(k in nl for k in ['indoor motor', 'fan motor indoor', 'motor idu', 'cross flow motor']):
        return "Indoor Fan Motor"
    elif any(k in nl for k in ['outdoor motor', 'fan motor outdoor', 'motor odu', 'propeller motor']):
        return "Outdoor Fan Motor"
    elif any(k in nl for k in ['motor']):
        return "Fan Motor"
    elif any(k in nl for k in ['1/4', 'quarter']) and 'valve' in nl:
        return "Cut-Off Valve (1/4\")"
    elif any(k in nl for k in ['1/2', 'half']) and 'valve' in nl:
        return "Cut-Off Valve (1/2\")"
    elif any(k in nl for k in ['3/8', '5/8']) and 'valve' in nl:
        return "Cut-Off Valve (3/8\" - 5/8\")"
    elif any(k in nl for k in ['4-way', '4 way', 'reversing valve']):
        return "4-Way Valve Assembly"
    elif any(k in nl for k in ['valve']):
        return "Service Valve"
    elif any(k in nl for k in ['sensor', 'temp sensor', 'thermistor', 'probe', 'ambient sensor', 'tube sensor']):
        return "Temperature Sensor"
    elif any(k in nl for k in ['capacitor', 'cap 50uf', 'cap 35uf', 'cap 60uf', 'cbb65']):
        return "Capacitor"
    elif any(k in nl for k in ['remote', 'controller']):
        return "Remote Control"
    elif any(k in nl for k in ['gear box', 'gearbox']):
        return "Gear Box"
    elif any(k in nl for k in ['t-con', 'glassboard', 'light bar', 'speaker', 'led panel']):
        return "LED TV Module"
    return "Component Hardware"

def tokenize_model(m_str):
    m = clean_str(m_str).upper()
    
    brand = "Gree" if m.startswith(('GS-', 'GR-', 'GF-', 'GW-')) else ("EcoStar" if m.startswith(('ES-', 'EW-', 'CX-', 'EM-')) else "Other")
    cat = "Split AC"
    ton = "1.5 Ton"
    series = "STANDARD"
    
    if any(k in m for k in ['GR-', 'REF-']):
        cat = "Refrigerator"
        ton = "Domestic Ref"
        series = "REF"
    elif any(k in m for k in ['EW-', 'WM-', 'SPIN']):
        cat = "Washing Machine"
        ton = "Standard Unit"
        series = "WM"
    elif any(k in m for k in ['GW-', 'WD-']):
        cat = "Water Dispenser"
        ton = "Dispenser"
        series = "WD"
    elif any(k in m for k in ['CX-', 'U57', 'U87', 'UD96', 'QD8', 'LED']):
        cat = "LED TV"
        ton = "Standard Unit"
        series = "LED"
    elif any(k in m for k in ['EM-', 'MW-']):
        cat = "Microwave Oven"
        ton = "Standard Unit"
        series = "MW"
    elif any(k in m for k in ['GF-', 'FLOOR', 'STANDING']) or any(x in m for x in ['48', '60', '36', '36TFIH', 'TFIH']):
        cat = "Floor Standing AC"
        ton = "4.0 Ton"
        series = "FLOOR"
    else:
        cat = "Split AC"
        cap_match = re.search(r'-(10|11|12|16|18|24|26|36|48|60)', m)
        if cap_match:
            cv = cap_match.group(1)
            if cv in ['48', '60', '36']:
                ton = "4.0 Ton"
            elif cv in ['24', '26']:
                ton = "2.0 Ton"
            elif cv in ['18', '16']:
                ton = "1.5 Ton"
            elif cv in ['12', '11', '10']:
                ton = "1.0 Ton"
            
        for s in ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'TF', 'CD', 'CB']:
            if s in m:
                series = s
                break
                
    return {
        'model': m,
        'brand': brand,
        'category': cat,
        'tonnage': ton,
        'series': series
    }

def get_role_price_floor(role, ton, cat):
    if cat == 'Split AC' or cat == 'Floor Standing AC':
        if ton == '4.0 Ton':
            floors = {
                "Evaporator Assembly": 70000,
                "Outdoor Inverter PCB": 55000,
                "Indoor Main PCB": 9500,
                "Compressor & Fittings": 75000,
                "Fan Motor": 4500,
                "Indoor Fan Motor": 4500,
                "Outdoor Fan Motor": 5000,
                "Stepping / Swing Motor": 2000,
                "Cut-Off Valve (1/4\")": 2100,
                "Cut-Off Valve (1/2\")": 2800,
                "Cut-Off Valve (3/8\" - 5/8\")": 3200,
                "4-Way Valve Assembly": 6500,
                "Temperature Sensor": 1500,
                "Capacitor": 1200
            }
        elif ton == '2.0 Ton':
            floors = {
                "Evaporator Assembly": 39000,
                "Outdoor Inverter PCB": 45000,
                "Indoor Main PCB": 7500,
                "Compressor & Fittings": 48000,
                "Fan Motor": 2500,
                "Indoor Fan Motor": 2500,
                "Outdoor Fan Motor": 3000,
                "Stepping / Swing Motor": 1500,
                "Cut-Off Valve (1/4\")": 1800,
                "Cut-Off Valve (1/2\")": 2400,
                "Cut-Off Valve (3/8\" - 5/8\")": 2800,
                "4-Way Valve Assembly": 4500,
                "Temperature Sensor": 1500,
                "Capacitor": 1000
            }
        elif ton == '1.0 Ton':
            floors = {
                "Evaporator Assembly": 20000,
                "Outdoor Inverter PCB": 35000,
                "Indoor Main PCB": 6500,
                "Compressor & Fittings": 32000,
                "Fan Motor": 2000,
                "Indoor Fan Motor": 2000,
                "Outdoor Fan Motor": 2200,
                "Stepping / Swing Motor": 1395,
                "Cut-Off Valve (1/4\")": 1600,
                "Cut-Off Valve (1/2\")": 2100,
                "Cut-Off Valve (3/8\" - 5/8\")": 2400,
                "4-Way Valve Assembly": 3300,
                "Temperature Sensor": 1500,
                "Capacitor": 800
            }
        else: # 1.5 Ton default
            floors = {
                "Evaporator Assembly": 26000,
                "Outdoor Inverter PCB": 40000,
                "Indoor Main PCB": 6500,
                "Compressor & Fittings": 38000,
                "Fan Motor": 2000,
                "Indoor Fan Motor": 2000,
                "Outdoor Fan Motor": 2500,
                "Stepping / Swing Motor": 1395,
                "Cut-Off Valve (1/4\")": 1600,
                "Cut-Off Valve (1/2\")": 2100,
                "Cut-Off Valve (3/8\" - 5/8\")": 2600,
                "4-Way Valve Assembly": 3500,
                "Temperature Sensor": 1500,
                "Capacitor": 900
            }
        return floors.get(role, 2000)
    elif cat == 'Refrigerator':
        floors = {
            "Evaporator Assembly": 8000,
            "Compressor & Fittings": 18000,
            "Temperature Sensor": 1500,
            "Circuit Board (PCB)": 4500,
            "Fan Motor": 2000
        }
        return floors.get(role, 1500)
    elif cat == 'Washing Machine':
        floors = {
            "Gear Box": 16000,
            "Circuit Board (PCB)": 14500,
            "Fan Motor": 6500,
            "Temperature Sensor": 6300
        }
        return floors.get(role, 1500)
    elif cat == 'LED TV':
        floors = {
            "LED TV Module": 12000,
            "Circuit Board (PCB)": 12000,
            "Remote Control": 1500
        }
        return floors.get(role, 2000)
    return 2000

def main():
    print("Starting Ground-Truth Baseline Indexer...")
    print("Reading Stock File:", STOCK_FILE)
    stock_df = pd.read_csv(STOCK_FILE)
    stock_dict = {}
    for _, r in stock_df.iterrows():
        pno = clean_str(r.get('PART_NO')).upper()
        if not pno:
            continue
        bal = int(pd.to_numeric(r.get('BAL_QTY', 0), errors='coerce') or 0)
        amt = float(pd.to_numeric(r.get('AMOUNT', 0), errors='coerce') or 0.0)
        unit_calc = int(round(amt / bal)) if (bal > 0 and amt > 0) else 0
        stock_dict[pno] = {
            'part_no': pno,
            'item_desc': clean_str(r.get('ITEM_DESC')),
            'brand': clean_str(r.get('BRAND')),
            'category': clean_str(r.get('CATEGORY')),
            'capacity': clean_str(r.get('CAPACITY')),
            'bal_qty': bal,
            'stock_cost': unit_calc
        }
    print(f"Loaded {len(stock_dict)} items from Stock Inventory.")

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

    ground_truth_catalog = {}
    series_catalog = {}

    for m_raw, parts_dict in model_replacements.items():
        tok = tokenize_model(m_raw)
        series_key = f"{tok['brand']}|{tok['category']}|{tok['tonnage']}|{tok['series']}"
        
        if series_key not in series_catalog:
            series_catalog[series_key] = {}
            
        model_parts_list = []
        
        for pno, info in parts_dict.items():
            role = classify_role(info['name'], pno)
            cnt = info['count']
            
            stk_info = stock_dict.get(pno, {})
            bal_qty = stk_info.get('bal_qty', 0)
            stock_cost = stk_info.get('stock_cost', 0)
            pname = stk_info.get('item_desc') or info['name'] or part_canonical_names.get(pno, "Component")
            
            # Strict Platform Series Contamination Filter:
            # If a chassis-sensitive part explicitly specifies another series and does not state COMMON, exclude from conflicting series
            p_upper = pname.upper()
            is_chassis_sensitive = role in ['Evaporator Assembly', 'Outdoor Inverter PCB', 'Indoor Main PCB', 'Display Board']
            conflicting_series = False
            if is_chassis_sensitive and 'COMMON' not in p_upper:
                for s in ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'LM', 'ECH', 'CM', 'CZ']:
                    if s in p_upper and s != tok['series'] and tok['series'] not in p_upper:
                        conflicting_series = True
                        break
            
            if conflicting_series:
                continue

            if pno in part_verified_prices and part_verified_prices[pno] > 0:
                final_price = part_verified_prices[pno]
            elif stock_cost > 0:
                final_price = stock_cost
            else:
                final_price = get_role_price_floor(role, tok['tonnage'], tok['category'])
                
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
        role = classify_role(desc, pno)
        price = s_item['stock_cost'] if s_item['stock_cost'] > 0 else get_role_price_floor(role, "1.5 Ton", s_item['category'])
        bal_qty = s_item['bal_qty']
        in_stk = bal_qty > 0

        # Direct Model Attachment: If stock item explicitly names a model or model family, add to model's exact catalog
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
                for t_str in ['4.0 Ton', '2.0 Ton', '1.0 Ton', '1.5 Ton']:
                    if ('48' in desc or '36' in desc) and t_str == '4.0 Ton': ton = t_str; break
                    elif '24' in desc and t_str == '2.0 Ton': ton = t_str; break
                    elif '12' in desc and t_str == '1.0 Ton': ton = t_str; break
                
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

    final_series_catalog = {}
    for s_key, parts_map in series_catalog.items():
        plist = list(parts_map.values())
        plist.sort(key=lambda x: (x['in_stock'], x['verified_jobs']), reverse=True)
        final_series_catalog[s_key] = plist

    payload = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_models': len(ground_truth_catalog),
        'total_series_keys': len(final_series_catalog),
        'total_stock_parts': len(stock_dict),
        'models': ground_truth_catalog,
        'series': final_series_catalog,
        'global_stock': stock_dict
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

    print(f"SUCCESS: Baseline generated at {OUTPUT_FILE}")
    print(f"Models indexed: {len(ground_truth_catalog)}, Series indexed: {len(final_series_catalog)}")

if __name__ == '__main__':
    main()
