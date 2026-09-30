# deep_audit.py
import os
import sys
import json
import sqlite3
import pandas as pd

BASE_DIR = r"c:\Users\PC\Desktop\estimator"
DB_PATH = os.path.join(BASE_DIR, "dwp_service.db")
BASELINE_PATH = os.path.join(BASE_DIR, "data", "ground_truth_baseline.json")
CSV_PATH = os.path.join(BASE_DIR, "data", "pdf_extracted_stock_report.csv")

print("=== 1. AUDITING CSV SOURCE ===")
df_csv = pd.read_csv(CSV_PATH)
print("CSV total rows:", len(df_csv))
csv_parts = df_csv['part_no'].dropna().astype(str).str.strip().str.upper().unique()
print("CSV unique parts count:", len(csv_parts))

print("\n=== 2. AUDITING DWP_SERVICE.DB ===")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT count(*), count(distinct part_no) FROM stock_master")
stock_count, stock_unique = cursor.fetchone()
print(f"stock_master: total={stock_count}, unique={stock_unique}")

cursor.execute("SELECT count(*), count(distinct part_no) FROM parts_master")
parts_count, parts_unique = cursor.fetchone()
print(f"parts_master: total={parts_count}, unique={parts_unique}")

cursor.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0")
zero_stock = cursor.fetchone()[0]
cursor.execute("SELECT count(*) FROM parts_master WHERE price <= 0")
zero_parts = cursor.fetchone()[0]
print(f"Zero price items: stock_master={zero_stock}, parts_master={zero_parts}")

# Check 518 parts in stock_master
cursor.execute("SELECT part_no, unit_price, bal_qty, amount FROM stock_master")
db_stock = {row[0].strip().upper(): {'unit_price': row[1], 'bal_qty': row[2], 'amount': row[3]} for row in cursor.fetchall()}

# Check 518 parts in parts_master
cursor.execute("SELECT part_no, price FROM parts_master")
db_parts = {}
for p, pr in cursor.fetchall():
    p = p.strip().upper()
    db_parts.setdefault(p, []).append(pr)

missing_in_stock = [p for p in csv_parts if p not in db_stock]
missing_in_parts = [p for p in csv_parts if p not in db_parts]
print(f"518 parts missing in stock_master: {len(missing_in_stock)} -> {missing_in_stock}")
print(f"518 parts missing in parts_master: {len(missing_in_parts)} -> {missing_in_parts}")

# Price accuracy of 518 parts in stock_master
csv_max_prices = df_csv.groupby(df_csv['part_no'].str.strip().str.upper())['pdf_price'].max().to_dict()
price_mismatches = []
for p, expected_pr in csv_max_prices.items():
    exp_int = int(round(float(expected_pr)))
    actual_pr = db_stock.get(p, {}).get('unit_price', -1)
    if actual_pr != exp_int:
        price_mismatches.append((p, exp_int, actual_pr))
print(f"Price mismatches between CSV and stock_master: {len(price_mismatches)}")
if price_mismatches:
    for m in price_mismatches[:10]:
        print("  Mismatch:", m)

print("\n=== 3. AUDITING GROUND_TRUTH_BASELINE.JSON ===")
with open(BASELINE_PATH, 'r', encoding='utf-8') as f:
    baseline = json.load(f)

price_book = baseline.get('price_book', {})
models = baseline.get('models', {})
series = baseline.get('series', {})
print(f"Baseline price_book entries: {len(price_book)}")
print(f"Baseline models entries: {len(models)}")
print(f"Baseline series entries: {len(series)}")

missing_in_price_book = [p for p in csv_parts if p not in price_book]
print(f"518 parts missing in baseline price_book: {len(missing_in_price_book)}")

baseline_price_mismatches = []
for p, exp_pr in csv_max_prices.items():
    exp_int = int(round(float(exp_pr)))
    actual_pr = price_book.get(p, {}).get('price', -1)
    if actual_pr != exp_int:
        baseline_price_mismatches.append((p, exp_int, actual_pr))
print(f"Price mismatches between CSV and baseline price_book: {len(baseline_price_mismatches)}")
if baseline_price_mismatches:
    for m in baseline_price_mismatches[:10]:
        print("  Baseline Mismatch:", m)

print("\n=== 4. AUDITING TARGET COMPONENTS ===")
targets = {
    '71302395': ('3/8" Valve', 1500),
    '7130239': ('1/4" Valve', 1600),
    '7133774': ('1/2" Valve', 2100),
    '7133844': ('5/8" Valve', 2200),
    '11001000602': ('GF-36TFIH Evaporator', 58000),
    '11001060868': ('GS-18PITH1W Evaporator', 26000),
    '11001062414': ('GS-18AITH23W-T3 Evaporator', 30000),
    '1004169': ('GF-48FW Evaporator', 70000),
    '11001060092': ('GF-24ISH Evaporator', 72000),
    '11001060521': ('GF-48TF Evaporator', 75000),
    '100404401': ('GF-24CB Evaporator', 66000)
}

for pno, (name, exp_p) in targets.items():
    csv_p = csv_max_prices.get(pno, None)
    db_p = db_stock.get(pno, {}).get('unit_price', None)
    base_p = price_book.get(pno, {}).get('price', None)
    print(f"Target {pno:12s} ({name:25s}) | Exp: {exp_p:6d} | CSV: {str(csv_p):6s} | DB: {str(db_p):6s} | Base: {str(base_p):6s}")

conn.close()
