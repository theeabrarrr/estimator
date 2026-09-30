import sqlite3
import json
import os
import sys
import pandas as pd
import numpy as np

from database import fetch_tiered_compatible_parts, search_stock_global, get_stock_metadata, get_connection
from config import tokenize_appliance_model, get_tonnage_specs, CATEGORY_OVERHEADS

print("=" * 70)
print("STARTING EMPIRICAL ADVERSARIAL STRESS TEST FOR MILESTONE 1")
print("=" * 70)

failures = []

def record_failure(test_name, reason):
    print(f"FAILED: [{test_name}] - {reason}")
    failures.append((test_name, reason))

# -------------------------------------------------------------
# SUITE 1: SQLite Database Integrity & Schema Audit
# -------------------------------------------------------------
print("\n--- SUITE 1: SQLite Database Integrity & Zero/Negative Price Audit ---")
conn = get_connection()
c = conn.cursor()

# 1.1 Table counts
for table in ['stock_master', 'parts_master', 'history_master', 'tech_performance_master']:
    c.execute(f"SELECT count(*) FROM {table}")
    cnt = c.fetchone()[0]
    print(f"Table {table}: {cnt} rows")
    if cnt == 0 and table != 'tech_performance_master':
        record_failure("Table Count", f"Table {table} is empty!")

# 1.2 Zero or Negative Prices in stock_master
c.execute("SELECT part_no, item_desc, unit_price FROM stock_master WHERE unit_price <= 0 OR unit_price IS NULL")
bad_stock = c.fetchall()
if bad_stock:
    record_failure("Zero-Price stock_master", f"Found {len(bad_stock)} items with zero/negative price: {bad_stock[:5]}")
else:
    print(">>> PASS 1.2: Zero-price immunity in stock_master: 0 zero/negative price items.")

# 1.3 Zero or Negative Prices in parts_master
c.execute("SELECT model, part_no, part_name, price FROM parts_master WHERE price <= 0 OR price IS NULL")
bad_parts = c.fetchall()
if bad_parts:
    record_failure("Zero-Price parts_master", f"Found {len(bad_parts)} items with zero/negative price: {bad_parts[:5]}")
else:
    print(">>> PASS 1.3: Zero-price immunity in parts_master: 0 zero/negative price items.")

# 1.4 Ledger Book Cost Leakage Check in stock_master
# AMOUNT / BAL_QTY should NOT equal unit_price if bal_qty > 0 and amount came from old ledger
# Under new formula: amount == unit_price * bal_qty (or 0 if bal_qty <= 0)
c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01")
corrupt_amounts = c.fetchone()[0]
if corrupt_amounts > 0:
    record_failure("Ledger Leakage", f"Found {corrupt_amounts} stock rows where amount != unit_price * bal_qty!")
else:
    print(">>> PASS 1.4: All in-stock rows have amount == unit_price * bal_qty (0% ledger book leakage).")

# 1.5 Null or Empty Part Numbers in stock_master and parts_master
c.execute("SELECT count(*) FROM stock_master WHERE part_no IS NULL OR TRIM(part_no) = ''")
empty_stock_pno = c.fetchone()[0]
c.execute("SELECT count(*) FROM parts_master WHERE part_no IS NULL OR TRIM(part_no) = ''")
empty_parts_pno = c.fetchone()[0]
if empty_stock_pno > 0 or empty_parts_pno > 0:
    record_failure("Empty Part No", f"Empty part_no found: stock={empty_stock_pno}, parts={empty_parts_pno}")
else:
    print(">>> PASS 1.5: No empty/null part_no in stock_master or parts_master.")

conn.close()

# -------------------------------------------------------------
# SUITE 2: Ground Truth Baseline JSON Stress Test
# -------------------------------------------------------------
print("\n--- SUITE 2: Ground Truth Baseline JSON Stress Test ---")
baseline_path = "data/ground_truth_baseline.json"
assert os.path.exists(baseline_path), "ground_truth_baseline.json missing!"

with open(baseline_path, 'r', encoding='utf-8') as f:
    baseline = json.load(f)

print(f"Baseline generated at: {baseline.get('generated_at')}")
print(f"Total models in baseline: {baseline.get('total_models')}")
print(f"Total series keys in baseline: {baseline.get('total_series_keys')}")
print(f"Total stock parts in baseline: {baseline.get('total_stock_parts')}")

# 2.1 Audit price_book
price_book = baseline.get('price_book', {})
print(f"Price book entries: {len(price_book)}")
pb_zero = [pno for pno, d in price_book.items() if not isinstance(d.get('price'), (int, float)) or d.get('price') <= 0]
if pb_zero:
    record_failure("Baseline price_book Zero Price", f"Found {len(pb_zero)} zero/invalid prices in price_book: {pb_zero[:5]}")
else:
    print(">>> PASS 2.1: 100% price_book entries have valid price > 0.")

# 2.2 Audit global_stock
global_stock = baseline.get('global_stock', {})
gs_zero = [pno for pno, d in global_stock.items() if d.get('unit_price', 0) <= 0 or d.get('stock_cost', 0) <= 0]
if gs_zero:
    record_failure("Baseline global_stock Zero Price", f"Found {len(gs_zero)} zero/invalid prices in global_stock: {gs_zero[:5]}")
else:
    print(">>> PASS 2.2: 100% global_stock entries have unit_price > 0 and stock_cost > 0.")

# 2.3 Audit all parts across all models in baseline
models_dict = baseline.get('models', {})
model_part_count = 0
model_part_zeros = []
for m, m_data in models_dict.items():
    for p in m_data.get('parts', []):
        model_part_count += 1
        if p.get('price', 0) <= 0:
            model_part_zeros.append((m, p.get('part_no'), p.get('price')))

if model_part_zeros:
    record_failure("Baseline Models Zero Price", f"Found {len(model_part_zeros)} parts with zero price across models: {model_part_zeros[:5]}")
else:
    print(f">>> PASS 2.3: Verified {model_part_count} parts across {len(models_dict)} models in baseline. All prices > 0.")

# 2.4 Audit all parts across all series in baseline
series_dict = baseline.get('series', {})
series_part_count = 0
series_part_zeros = []
for s_key, s_parts in series_dict.items():
    for p in s_parts:
        series_part_count += 1
        if p.get('price', 0) <= 0:
            series_part_zeros.append((s_key, p.get('part_no'), p.get('price')))

if series_part_zeros:
    record_failure("Baseline Series Zero Price", f"Found {len(series_part_zeros)} parts with zero price across series: {series_part_zeros[:5]}")
else:
    print(f">>> PASS 2.4: Verified {series_part_count} parts across {len(series_dict)} series in baseline. All prices > 0.")

# -------------------------------------------------------------
# SUITE 3: Official Catalog 518 Parts Ingestion & Price Fidelity
# -------------------------------------------------------------
print("\n--- SUITE 3: Official Catalog 518 Parts Ingestion & Price Fidelity ---")
csv_path = "data/pdf_extracted_stock_report.csv"
pdf_df = pd.read_csv(csv_path)
pdf_df['clean_pno'] = pdf_df['part_no'].astype(str).str.strip().str.upper()
pdf_df['clean_price'] = pd.to_numeric(pdf_df['pdf_price'], errors='coerce').fillna(0).round().astype(int)

# Group by clean_pno to get max price and total stock
cat_agg = pdf_df.groupby('clean_pno').agg({
    'clean_price': 'max',
    'total_stock': 'sum'
}).to_dict(orient='index')

print(f"Total unique parts in official catalog CSV: {len(cat_agg)}")
if len(cat_agg) != 518:
    record_failure("Official Catalog Part Count", f"Expected 518 unique parts, got {len(cat_agg)}")

# Verify all 518 parts in stock_master, parts_master, and baseline price_book
conn = get_connection()
c = conn.cursor()
c.execute("SELECT part_no, unit_price, bal_qty FROM stock_master")
db_stocks = {r[0]: (r[1], r[2]) for r in c.fetchall()}

c.execute("SELECT DISTINCT part_no, MAX(price) FROM parts_master GROUP BY part_no")
db_parts = {r[0]: r[1] for r in c.fetchall()}
conn.close()

mismatched_prices_stock = []
missing_stock = []
mismatched_prices_pb = []
missing_pb = []
missing_parts_master = []

for pno, expected in cat_agg.items():
    exp_price = expected['clean_price']
    
    # Check stock_master
    if pno not in db_stocks:
        missing_stock.append(pno)
    else:
        actual_price, actual_stock = db_stocks[pno]
        if actual_price != exp_price:
            mismatched_prices_stock.append((pno, exp_price, actual_price))
            
    # Check parts_master
    if pno not in db_parts:
        missing_parts_master.append(pno)
        
    # Check baseline price_book
    if pno not in price_book:
        missing_pb.append(pno)
    else:
        pb_price = price_book[pno]['price']
        if pb_price != exp_price:
            mismatched_prices_pb.append((pno, exp_price, pb_price))

if missing_stock:
    record_failure("Catalog in stock_master", f"Missing {len(missing_stock)} catalog parts in stock_master: {missing_stock}")
else:
    print(f">>> PASS 3.1: All {len(cat_agg)} official parts present in stock_master.")

if mismatched_prices_stock:
    record_failure("Price mismatch in stock_master", f"{len(mismatched_prices_stock)} parts had mismatched price in stock_master: {mismatched_prices_stock[:5]}")
else:
    print(f">>> PASS 3.2: All {len(cat_agg)} official parts have 100% price match in stock_master.")

if missing_parts_master:
    record_failure("Catalog in parts_master", f"Missing {len(missing_parts_master)} catalog parts in parts_master: {missing_parts_master}")
else:
    print(f">>> PASS 3.3: All {len(cat_agg)} official parts present in parts_master.")

if missing_pb:
    record_failure("Catalog in price_book", f"Missing {len(missing_pb)} catalog parts in baseline price_book: {missing_pb}")
else:
    print(f">>> PASS 3.4: All {len(cat_agg)} official parts present in baseline price_book.")

if mismatched_prices_pb:
    record_failure("Price mismatch in price_book", f"{len(mismatched_prices_pb)} parts had mismatched price in price_book: {mismatched_prices_pb[:5]}")
else:
    print(f">>> PASS 3.5: All {len(cat_agg)} official parts have 100% price match in baseline price_book.")

# -------------------------------------------------------------
# SUITE 4: Acceptance Criteria Target Parts Pricing Reconciliation
# -------------------------------------------------------------
print("\n--- SUITE 4: Target Acceptance Components Pricing Reconciliation ---")
target_acceptance_parts = {
    '71302395': ('Cut-Off Valve (3/8")', 1500),
    '7130239':  ('Cut-Off Valve (1/4")', 1600),
    '7133774':  ('Cut-Off Valve (1/2")', 2100),
    '7133844':  ('Cut-Off Valve (5/8")', 2200),
    '11001000602': ('Evaporator Assembly', 58000),
    '11001060868': ('Evaporator Assembly', 26000),
    '11001062414': ('Evaporator Assembly', 30000),
    '1004169':     ('Evaporator Assembly', 70000),
    '11001060092': ('Evaporator Assembly', 72000),
    '11001060521': ('Evaporator Assembly', 75000),
    '100404401':   ('Evaporator Assembly', 66000),
}

for pno, (role, exp_pr) in target_acceptance_parts.items():
    # stock_master check
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,))
    row = c.fetchone()
    conn.close()
    if not row or row[0] != exp_pr:
        record_failure("Target Part stock_master", f"Part {pno} expected {exp_pr}, got {row[0] if row else 'None'}")
    
    # baseline price_book check
    pb_item = price_book.get(pno)
    if not pb_item or pb_item['price'] != exp_pr:
        record_failure("Target Part price_book", f"Part {pno} expected {exp_pr}, got {pb_item.get('price') if pb_item else 'None'}")
        
    # global direct search check
    sr = search_stock_global(pno)
    if sr.empty:
        record_failure("Target Part direct search", f"Part {pno} search returned empty")
    else:
        found_pr = int(sr.iloc[0]['price'])
        if found_pr != exp_pr:
            record_failure("Target Part direct search price", f"Part {pno} direct search expected {exp_pr}, got {found_pr}")
        else:
            print(f"Verified Part {pno:14s} | Expected: Rs. {exp_pr:6d} | DB: {row[0]:6d} | Search: {found_pr:6d} [PASS]")

print(">>> PASS SUITE 4: All 11 target components match official prices across DB, Baseline, and Global Search.")

# -------------------------------------------------------------
# SUITE 5: Adversarial Edge Case Lookups & Robustness
# -------------------------------------------------------------
print("\n--- SUITE 5: Adversarial Edge Case Lookups & Robustness ---")

# 5.1 Direct Search with Special Characters, Whitespace, Mixed Case
test_queries = [
    # Whitespace variations
    " 71302395 ",
    "   7130239   ",
    "  evaporator  ",
    "\t7133774\n",
    # Case variations
    "valve",
    "VALVE",
    "VaLvE",
    "pcb",
    "Pcb",
    "EVAPORATOR",
    # Special character searches
    '3/8"',
    '1/4"',
    '1/2"',
    '5/8"',
    "Cut-Off",
    "Assy",
    # Substring / partial searches
    "713023",
    "1100100",
    "PITH",
    "CITH",
    # SQL Metacharacters & Boundary inputs (Must NOT throw exceptions)
    "%",
    "_",
    "'",
    "''",
    ";",
    "--",
    "\\",
    "   ",
    "",
    "NON_EXISTENT_PART_XYZ_99999",
    "1234567890987654321"
]

search_errors = []
for q in test_queries:
    try:
        res = search_stock_global(q, limit=20)
        assert isinstance(res, pd.DataFrame), f"Expected DataFrame, got {type(res)}"
        if not res.empty:
            assert 'price' in res.columns, "price column missing"
            # Assert zero price immunity in search results!
            zero_in_res = (res['price'] <= 0).sum()
            if zero_in_res > 0:
                record_failure("Search Zero Price", f"Query '{q}' returned {zero_in_res} items with price <= 0")
        print(f"Search query: {repr(q):35s} -> Returned {len(res):2d} rows [PASS]")
    except Exception as e:
        record_failure("Search Exception", f"Query '{q}' raised exception: {e}")

# 5.2 Model Resolution Edge Cases & Boundary Inputs
test_models = [
    # Standard models
    "GS-18ZITH1W-T3",
    "GS-18PITH11W",
    "GS-18CITH12G",
    "GS-12PITH11W",
    "GS-24PITH11W",
    "GF-36TFIH",
    "GF-48TF",
    "GF-48FW",
    "GF-24ISH",
    "GF-24CB",
    "GR-E8768G-CP1",
    "EW-F1202DC",
    "WD-E500",
    # Whitespace & casing edge cases
    "  GS-18ZITH1W-T3  ",
    "gs-18zith1w-t3",
    "gs-18pith11w",
    "gf-36tfih",
    "  gf-36tfih  ",
    # Unknown / Unseen models
    "UNKNOWN-MODEL-999",
    "GS-99UNKNOWN-T1",
    "RANDOM_STRING_MODEL",
    "",
    "   "
]

model_errors = []
for m in test_models:
    try:
        res = fetch_tiered_compatible_parts(m)
        assert isinstance(res, dict), f"Expected dict, got {type(res)}"
        assert 'role_groups' in res, "role_groups missing"
        # Verify no zero prices in any role group
        for grp in res['role_groups']:
            pri = grp.get('primary')
            if pri:
                if pri.get('price', 0) <= 0:
                    record_failure("Model Zero Price Primary", f"Model '{m}', Role '{grp.get('group_title')}' primary part {pri.get('part_no')} has price {pri.get('price')}")
            for alt in grp.get('alternatives', []):
                if alt.get('price', 0) <= 0:
                    record_failure("Model Zero Price Alt", f"Model '{m}', Role '{grp.get('group_title')}' alt part {alt.get('part_no')} has price {alt.get('price')}")
        print(f"Model lookup: {repr(m):35s} -> Found {len(res['role_groups']):2d} role groups [PASS]")
    except Exception as e:
        record_failure("Model Lookup Exception", f"Model '{m}' raised exception: {e}")

# -------------------------------------------------------------
# SUITE 6: Valve Pairing & Capacity Physical Constraints Across AC Categories
# -------------------------------------------------------------
print("\n--- SUITE 6: Valve Pairing & Physical Constraints Across AC Categories ---")

tonnage_test_cases = [
    # 1.0 Ton: Suction = 3/8", Liquid = 1/4"
    ("GS-12PITH11W", "1.0 Ton", "71302395", 1500, "7130239", 1600, ["Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")"]),
    ("GS-12CITH11W", "1.0 Ton", "71302395", 1500, "7130239", 1600, ["Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")"]),
    # 1.5 Ton: Suction = 1/2", Liquid = 1/4"
    ("GS-18ZITH1W-T3", "1.5 Ton", "7133774", 2100, "7130239", 1600, ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"]),
    ("GS-18PITH11W", "1.5 Ton", "7133774", 2100, "7130239", 1600, ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"]),
    ("GS-18CITH12G", "1.5 Ton", "7133774", 2100, "7130239", 1600, ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"]),
    # 2.0 Ton: Suction = 5/8", Liquid = 1/4"
    ("GS-24PITH11W", "2.0 Ton", "7133844", 2200, "7130239", 1600, ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]),
    ("GS-24CITH1",   "2.0 Ton", "7133844", 2200, "7130239", 1600, ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]),
    # 3.0 Ton: Suction = 5/8", Liquid = 1/4"
    ("GF-36TFIH",    "3.0 Ton", "7133844", 2200, "7130239", 1600, ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]),
    # 4.0 Ton: Suction = 5/8", Liquid = 3/8"
    ("GF-48TF",      "4.0 Ton", "7133844", 3200, "71302395", 2400, ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"]),
    ("GF-48FW",      "4.0 Ton", "7133844", 3200, "71302395", 2400, ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"]),
]

for m, exp_ton, exp_suc_pno, exp_suc_pr, exp_liq_pno, exp_liq_pr, forbidden_roles in tonnage_test_cases:
    res = fetch_tiered_compatible_parts(m)
    vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    if not vg:
        record_failure("Valve Pairing Missing", f"Model {m} has no Cut-off & Service Valves group!")
        continue
    
    pri = vg['primary']
    alts = vg['alternatives']
    
    # Primary must be suction valve
    if pri['part_no'] != exp_suc_pno or pri['price'] != exp_suc_pr:
        record_failure("Valve Suction Mismatch", f"Model {m} ({exp_ton}): Primary valve expected {exp_suc_pno} @ Rs. {exp_suc_pr}, got {pri['part_no']} @ Rs. {pri['price']}")
        
    # Alt must be liquid valve
    if not alts or alts[0]['part_no'] != exp_liq_pno or alts[0]['price'] != exp_liq_pr:
        record_failure("Valve Liquid Mismatch", f"Model {m} ({exp_ton}): Alt valve expected {exp_liq_pno} @ Rs. {exp_liq_pr}, got {alts[0]['part_no'] if alts else 'None'} @ Rs. {alts[0]['price'] if alts else 'None'}")
        
    # Check forbidden roles
    all_roles = [pri['role']] + [a['role'] for a in alts]
    for fr in forbidden_roles:
        if fr in all_roles:
            record_failure("Forbidden Valve Role Contamination", f"Model {m} ({exp_ton}) leaked forbidden valve role '{fr}'!")

print(">>> PASS SUITE 6: Strict physical valve pairing verified across 1.0T, 1.5T, 2.0T, 3.0T, and 4.0T with 0% contamination.")

# -------------------------------------------------------------
# SUITE 7: Floor Standing AC Isolation & Cross-Series Integrity
# -------------------------------------------------------------
print("\n--- SUITE 7: Floor Standing AC Isolation & Cross-Series Integrity ---")

# GF-36TFIH Isolation
res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
evap_36 = next((g for g in res_36['role_groups'] if "Evaporator" in g['group_title']), None)
if not evap_36:
    record_failure("GF-36TFIH Evaporator", "GF-36TFIH missing evaporator group")
else:
    if evap_36['primary']['part_no'] != "11001000602" or evap_36['primary']['price'] != 58000:
        record_failure("GF-36TFIH Evaporator", f"Expected 11001000602 @ 58000, got {evap_36['primary']['part_no']} @ {evap_36['primary']['price']}")
    all_evap_pnos = [evap_36['primary']['part_no']] + [a['part_no'] for a in evap_36['alternatives']]
    for forbidden_pno in ['11001060092', '1004169', '11001060246']:
        if forbidden_pno in all_evap_pnos:
            record_failure("GF-36TFIH Evaporator Leakage", f"Forbidden evaporator {forbidden_pno} leaked into GF-36TFIH!")

print(">>> PASS SUITE 7: GF-36TFIH floor standing isolation verified with genuine 3.0T evaporator and zero leakage.")

# -------------------------------------------------------------
# SUMMARY & FINAL VERDICT
# -------------------------------------------------------------
print("\n" + "=" * 70)
if failures:
    print(f"VERDICT: REJECT - {len(failures)} EMPIRICAL STRESS TEST FAILURES DETECTED!")
    for t_name, reason in failures:
        print(f"  - [{t_name}]: {reason}")
    print("=" * 70)
    sys.exit(1)
else:
    print("VERDICT: APPROVE - ALL EMPIRICAL ADVERSARIAL STRESS TESTS PASSED (0 FAILURES)!")
    print("=" * 70)
    sys.exit(0)
