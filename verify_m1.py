import sqlite3
import json
import pandas as pd
from database import fetch_tiered_compatible_parts, search_stock_global

print("=" * 60)
print("RUNNING COMPREHENSIVE MILESTONE 1 VERIFICATION")
print("=" * 60)

# Check 1: Catalog parts indexing in DB
df_pdf = pd.read_csv("data/pdf_extracted_stock_report.csv")
pdf_parts = set(df_pdf['part_no'].astype(str).str.strip().str.upper().unique())
print(f"Total unique parts in official catalog CSV: {len(pdf_parts)}")
assert len(pdf_parts) == 518, f"Expected 518 unique parts, got {len(pdf_parts)}"

conn = sqlite3.connect("dwp_service.db")
c = conn.cursor()

c.execute("SELECT part_no, unit_price, bal_qty FROM stock_master")
stock_rows = c.fetchall()
db_stock = {row[0]: (row[1], row[2]) for row in stock_rows}
print(f"Total parts in stock_master: {len(db_stock)}")

missing_from_stock = pdf_parts - set(db_stock.keys())
assert len(missing_from_stock) == 0, f"Missing from stock_master: {len(missing_from_stock)} parts: {missing_from_stock}"
print(">>> CHECK 1A PASS: All 518 parts present in stock_master.")

c.execute("SELECT DISTINCT part_no FROM parts_master")
db_parts = set(row[0] for row in c.fetchall())
print(f"Total distinct parts in parts_master: {len(db_parts)}")
missing_from_parts = pdf_parts - db_parts
assert len(missing_from_parts) == 0, f"Missing from parts_master: {len(missing_from_parts)} parts: {missing_from_parts}"
print(">>> CHECK 1B PASS: All 518 parts present in parts_master.")

# Check 2: Target components pricing in stock_master, parts_master, and baseline price_book
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

with open("data/ground_truth_baseline.json", "r", encoding="utf-8") as f:
    baseline = json.load(f)
price_book = baseline.get("price_book", {})

for pno, (expected_role, expected_price) in target_acceptance_parts.items():
    # 1. stock_master check
    c.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,))
    row = c.fetchone()
    assert row is not None, f"Part {pno} missing from stock_master"
    assert row[0] == expected_price, f"stock_master mismatch for {pno}: got {row[0]}, expected {expected_price}"
    
    # 2. baseline price_book check
    assert pno in price_book, f"Part {pno} missing from baseline price_book"
    pb_item = price_book[pno]
    assert pb_item['price'] == expected_price, f"price_book price mismatch for {pno}: got {pb_item['price']}, expected {expected_price}"
    
    # 3. direct search check
    search_res = search_stock_global(pno)
    assert not search_res.empty, f"Direct search for {pno} returned empty"
    direct_price = int(search_res.iloc[0]['price'])
    assert direct_price == expected_price, f"Direct search price mismatch for {pno}: got {direct_price}, expected {expected_price}"
    
    print(f"Verified Part {pno:14s} | Expected: Rs. {expected_price:6d} | DB: {row[0]:6d} | Baseline: {pb_item['price']:6d} | Direct Search: {direct_price:6d}")

print(">>> CHECK 2 PASS: All 11 target components match official prices across DB, Baseline, and Search.")

# Check 3: Check 1/2" valve in 1.5T model search
res_15 = fetch_tiered_compatible_parts("GS-18ZITH1W-T3")
v_grp = next(g for g in res_15['role_groups'] if "Cut-off & Service Valves" in g['group_title'])
assert v_grp['primary']['part_no'] == "7133774"
assert v_grp['primary']['price'] == 2100, f"Expected 1/2\" valve price 2,100, got {v_grp['primary']['price']}"
assert v_grp['alternatives'][0]['part_no'] == "7130239"
assert v_grp['alternatives'][0]['price'] == 1600, f"Expected 1/4\" valve price 1,600, got {v_grp['alternatives'][0]['price']}"
print(">>> CHECK 3 PASS: 1.5 Ton AC strictly paired with 1/2\" (Rs. 2,100) + 1/4\" (Rs. 1,600).")

# Check 4: Check GF-36TFIH in model search
res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
evap_36 = next(g for g in res_36['role_groups'] if "Evaporator" in g['group_title'])
assert evap_36['primary']['part_no'] == "11001000602"
assert evap_36['primary']['price'] == 58000
v_36 = next(g for g in res_36['role_groups'] if "Cut-off & Service Valves" in g['group_title'])
assert v_36['primary']['part_no'] == "7133844"
assert v_36['primary']['price'] == 2200
assert v_36['alternatives'][0]['part_no'] == "7130239"
assert v_36['alternatives'][0]['price'] == 1600
print(">>> CHECK 4 PASS: GF-36TFIH Floor Standing has genuine Evaporator 11001000602 (Rs. 58,000) and valves 5/8\" (Rs. 2,200) + 1/4\" (Rs. 1,600).")

# Check 5: Zero-price immunity
c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0")
zero_stock = c.fetchone()[0]
assert zero_stock == 0, f"Found {zero_stock} zero price items in stock_master"

c.execute("SELECT count(*) FROM parts_master WHERE price <= 0")
zero_parts = c.fetchone()[0]
assert zero_parts == 0, f"Found {zero_parts} zero price items in parts_master"
print(f">>> CHECK 5 PASS: Zero-price immunity confirmed (0 zero-price items in stock_master and parts_master).")

conn.close()
print("=" * 60)
print("ALL MILESTONE 1 VERIFICATION CHECKS SUCCEEDED!")
print("=" * 60)
