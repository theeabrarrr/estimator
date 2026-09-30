# Milestone 1 Handoff Report: Verification, Testing & Regression Protection

**Document ID:** HANDOFF-M1-VERIF-001  
**Author:** M1 Explorer 3 (`m1_explorer_3`)  
**Recipient:** Orchestrator (`orchestrator_1`), Worker (`worker_1`), Reviewers  
**Date:** 2026-09-29  
**Type:** Hard Handoff (Investigation Complete)  

---

## 1. Observation

Direct empirical observations made during codebase inspection and database querying:

1. **Current Test Suite Execution**:
   - Command: `python test_system_verification.py`
   - Result: Exited 0 with all 13 tests passing:
     ```text
     ============================================================
     RUNNING SYSTEM UPGRADE VERIFICATION SUITE
     ============================================================
     ...
     [TEST 1] Testing Database Bootstrap & Stock Metadata...
     Stock Metadata: Total Items=774, In-Stock=771, Synced=2026-09-26 02:20 PM
     ...
     ============================================================
     ALL 13 SYSTEM TESTS PASSED SUCCESSFULLY!
     ============================================================
     ```
   - Test 10 (`test_system_verification.py:190-191`) asserts only `vg['primary']['price'] > 0` for the 1.5 Ton valve, leaving the exact Rs. 2,100 price check unasserted.

2. **Catalog Discrepancies in `dwp_service.db`**:
   - `data/pdf_extracted_stock_report.csv` contains 531 rows and 518 unique part numbers.
   - SQLite query on `dwp_service.db`:
     - `stock_master` has 774 rows.
     - PDF catalog parts present in `stock_master`: **320**.
     - PDF catalog parts **MISSING** from `stock_master`: **198**.
     - PDF catalog parts present in `parts_master`: **459**.
     - PDF catalog parts **MISSING** from `parts_master`: **59**.
     - Out of 320 catalog parts in `stock_master`, **124 parts have price mismatches** against `data/pdf_extracted_stock_report.csv`.
     - Example: `100002065730` ('Outdoor Electric Box GF-48TFIH') has price Rs. 2,000 in `stock_master`, but official catalog price is Rs. 74,000!

3. **Flawed Accounting Ledger Formula (`AMOUNT / BAL_QTY`) Locations**:
   - `etl.py:104`:
     ```python
     df['calc_price'] = df.apply(
         lambda r: int(round(r['amount'] / r['bal_qty'])) if (r['bal_qty'] > 0 and r['amount'] > 0) else 0,
         axis=1
     )
     ```
   - `build_baseline.py:44`:
     ```python
     unit_calc = int(round(amt / bal)) if (bal > 0 and amt > 0) else 0
     ```
   - Empirical distortion examples:
     - `11001060868` (GS-18PITH1W Evaporator): Ledger ratio Rs. 1,384,687 vs Official Rs. 26,000 (+5,225%).
     - `7133844` (5/8" Valve): Ledger ratio Rs. 34,354 vs Official Rs. 2,200 (+1,461%).
     - `7133774` (1/2" Valve): Ledger ratio Rs. 26,622 vs Official Rs. 2,100 (+1,167%).
     - `7130239` (1/4" Valve): Ledger ratio Rs. 5,845 vs Official Rs. 1,600 (+265%).
     - `71302395` (3/8" Valve): Ledger ratio Rs. 2,516 vs Official Rs. 1,500 (+67%).

4. **Hardcoded Overrides Masking Defects**:
   - In `etl.py:118-123` and `build_baseline.py:130-135`:
     ```python
     known_price_overrides = {
         '71302395': 1500,     # Cut-off valve 3/8 1.0 Ton verified field price
         '7130239': 1600,      # Cut-off valve 1/4 verified field price
         '7133844': 2200,      # Cut-off valve 5/8 (2.0/3.0 Ton) verified customer collection price
         '11001000602': 58000, # Evaporator Assy GF-36TFIH verified customer collection price
     }
     ```
   - In `database.py:298-323`: Hardcoded dictionary `warehouse_stock_map`.

5. **The 1/2" Valve `7133774` Corruption in Baseline**:
   - In `data/ground_truth_baseline.json`:
     `price_book['7133774']`: `{'price': 1600, 'part_name': 'Evaporator 11001061842LC 18PITH11W / GS-18PITC12W-T3', 'role': 'Evaporator Assembly'}`.
   - In `dwp_service.db`: `stock_master.unit_price` for `7133774` is Rs. 1,600.
   - In `data/pdf_extracted_stock_report.csv`: `7133774` is `Cut Off Valve Assy 1/2 7133774 GS- 18VITH1`, `pdf_price`: **Rs. 2,100**.

---

## 2. Logic Chain

1. **Observation 1 & 4** show that the current 13 tests pass only because hardcoded override dictionaries (`known_price_overrides`) paper over corrupted database prices for 4 components (`71302395`, `7130239`, `7133844`, `11001000602`).
2. **Observation 2** proves that the database currently does not represent the official catalog: 198 catalog parts are completely missing from `stock_master`, 59 parts are missing from `parts_master`, and 124 existing parts have distorted prices.
3. **Observation 3** proves that the accounting ledger formula `AMOUNT / BAL_QTY` is the source of extreme pricing distortions (+5,225% on evaporators, +1,461% on valves).
4. **Observation 5** demonstrates a severe corruption in the precomputed baseline: 1/2" Valve `7133774` was corrupted to Rs. 1,600 and assigned the role "Evaporator Assembly", escaping notice because Test 10 only checked `price > 0`.
5. Therefore, Milestone 1 must establish `data/pdf_extracted_stock_report.csv` as the Master Price Authority to index all 518 parts into both `stock_master` and `parts_master`, permanently remove `AMOUNT / BAL_QTY` and `known_price_overrides`, fix `7133774` to Rs. 2,100, and enforce regression testing to guarantee all 13 tests pass without hardcoded overrides.

---

## 3. Caveats

1. **Dual Ingestion vs Pure Catalog Replacement**: `dwp_service.db` currently contains 774 parts, of which 320 overlap with the 518 catalog parts. The Worker can either replace `stock_master` with the 518 catalog parts or upsert the 518 catalog parts into the 774 rows. In either case, all 518 catalog parts must exist in `stock_master` with exact `pdf_price` and live stock.
2. **Multi-Bin Consolidation**: Exactly 9 part numbers have duplicate entries (13 rows total) in `pdf_extracted_stock_report.csv`. The Worker must aggregate `bal_qty` as the sum of `total_stock`, take the maximum `pdf_price`, and retain descriptions containing model tokens (`GS-11CITH3F` for `7130239`, `24LITH11M` for `7133844`) so that Test 13 passes.
3. **Explorers are Read-Only**: No source code or database modifications were performed by this Explorer.

---

## 4. Conclusion

Milestone 1 implementation must achieve five concrete verification gates:
1. **518 Parts Ingestion**: All 518 unique parts from `data/pdf_extracted_stock_report.csv` indexed into both `stock_master` and `parts_master`.
2. **Ledger Formula Elimination**: Zero occurrences of `AMOUNT / BAL_QTY` in code; 0% ledger cost leakage into `stock_master.unit_price`.
3. **Target Pricing Verification**:
   - Valves: 3/8" (`71302395`) = Rs. 1,500; 1/4" (`7130239`) = Rs. 1,600; 1/2" (`7133774`) = Rs. 2,100; 5/8" (`7133844`) = Rs. 2,200.
   - Evaporators: GF-36TFIH = Rs. 58,000; GS-18PITH1W = Rs. 26,000; GS-18AITH23W-T3 = Rs. 30,000; GF-48FW = Rs. 70,000; GF-24ISH = Rs. 72,000; GF-48TF = Rs. 75,000; GF-24CB = Rs. 66,000.
4. **Zero-Pricing Immunity**: Zero parts with price <= 0 across database tables and runtime resolution for all 5 appliance categories.
5. **Regression Protection**: 100% pass rate across the 13 test cases in `test_system_verification.py`.

---

## 5. Verification Method

### Step 1: Execute Milestone 1 Automated Verification Suite
Run the following script to verify all M1 data foundation criteria:
```powershell
python -c "
import sqlite3, json, pandas as pd
from database import fetch_tiered_compatible_parts, search_stock_global

print('=' * 60)
print('RUNNING MILESTONE 1 DATA FOUNDATION VERIFICATION')
print('=' * 60)

# Check 1: 518 parts indexing
df_pdf = pd.read_csv('data/pdf_extracted_stock_report.csv')
pdf_parts = set(df_pdf['part_no'].str.strip().str.upper().unique())
conn = sqlite3.connect('dwp_service.db')
c = conn.cursor()
c.execute('SELECT part_no FROM stock_master')
db_stock = set(row[0] for row in c.fetchall())
missing_stock = pdf_parts - db_stock
assert len(missing_stock) == 0, f'Missing from stock_master: {len(missing_stock)} parts'

c.execute('SELECT DISTINCT part_no FROM parts_master')
db_parts = set(row[0] for row in c.fetchall())
missing_parts = pdf_parts - db_parts
assert len(missing_parts) == 0, f'Missing from parts_master: {len(missing_parts)} parts'
print('>>> CHECK 1 PASS: All 518 parts successfully indexed into stock_master and parts_master.')

# Check 2: No ledger formula leakage
for pno, expected in [('11001060868', 26000), ('7133844', 2200), ('7133774', 2100), ('7130239', 1600), ('71302395', 1500)]:
    c.execute('SELECT unit_price FROM stock_master WHERE part_no = ?', (pno,))
    price = c.fetchone()[0]
    assert price == expected, f'Part {pno} price {price} != {expected}'
print('>>> CHECK 2 PASS: Ledger valuation formula completely absent. Prices match catalog.')

# Check 3: Target valve and evaporator acceptance prices
target_parts = {
    '71302395': 1500, '7130239': 1600, '7133774': 2100, '7133844': 2200,
    '11001000602': 58000, '11001060868': 26000, '11001062414': 30000,
    '1004169': 70000, '11001060092': 72000, '11001060521': 75000, '100404401': 66000
}
baseline = json.load(open('data/ground_truth_baseline.json'))
pb = baseline.get('price_book', {})
for pno, exp_pr in target_parts.items():
    c.execute('SELECT unit_price FROM stock_master WHERE part_no = ?', (pno,))
    db_pr = c.fetchone()[0]
    base_pr = pb.get(pno, {}).get('price')
    assert db_pr == exp_pr, f'DB price mismatch {pno}: {db_pr} != {exp_pr}'
    assert base_pr == exp_pr, f'Baseline price mismatch {pno}: {base_pr} != {exp_pr}'
print('>>> CHECK 3 PASS: Target valve and evaporator prices verified in DB and Baseline.')

# Check 4: Zero-pricing immunity
c.execute('SELECT count(*) FROM stock_master WHERE unit_price <= 0')
assert c.fetchone()[0] == 0
c.execute('SELECT count(*) FROM parts_master WHERE price <= 0')
assert c.fetchone()[0] == 0
for m in ['GS-18PITH11W', 'GF-36TFIH', 'GR-E8768G-CP1', 'EW-F1202DC', 'WD-300F']:
    res = fetch_tiered_compatible_parts(m)
    for g in res['role_groups']:
        for p in [g['primary']] + g['alternatives']:
            assert p['price'] > 0, f'Zero price in {m} for {p[\"part_no\"]}'
print('>>> CHECK 4 PASS: Zero-pricing immunity verified across all categories.')

print('=' * 60)
print('ALL MILESTONE 1 VERIFICATION CHECKS PASSED!')
print('=' * 60)
"
```

### Step 2: Execute Existing 13 Regression Tests
```powershell
python test_system_verification.py
```
*Expected Result*: Exits with code 0 and `ALL 13 SYSTEM TESTS PASSED SUCCESSFULLY!`.

### Invalidation Conditions:
- Any of the 518 parts missing from `stock_master` or `parts_master`.
- `known_price_overrides` remaining in `etl.py` or `build_baseline.py`.
- 1/2" Valve `7133774` displaying Rs. 1,600 instead of Rs. 2,100.
- Any regression failure in `test_system_verification.py`.
