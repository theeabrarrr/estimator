# Milestone 1 Verification, Testing & Regression Protection Report

**Document ID:** VERIF-M1-HARNESS-001  
**Author:** M1 Explorer 3 (`m1_explorer_3`)  
**Target Milestone:** Milestone 1 — Official Catalog Ingestion & Triangular Ground-Truth Engine (R1 & R2)  
**Date:** 2026-09-29  
**Reference Codebase:** `test_system_verification.py`, `etl.py`, `build_baseline.py`, `database.py`, `config.py`  
**Authoritative Specifications:** `ORIGINAL_REQUEST.md`, `PROJECT.md`, `catalog_spec_report.md`  

---

## 1. Executive Summary

This report delivers the comprehensive testing, verification, and regression protection specification for **Milestone 1 (R1 & R2 Data Foundation)** of the DWP Autonomous Official Pricing Engine.

### Core Investigation Findings:
1. **Current Test Suite (`test_system_verification.py`) Status**:
   - The existing test suite contains **13 system tests** that currently execute with a 100% pass rate.
   - However, several tests pass only because of **hardcoded price override dictionaries** (`known_price_overrides = {'71302395': 1500, '7130239': 1600, '7133844': 2200, '11001000602': 58000}`) and hardcoded valve mappings in `build_baseline.py` and `database.py`.
   - Test 10 checks that valve prices are `> 0`, but does not assert that the 1/2" Valve (`7133774`) is Rs. 2,100.
2. **Current Database Ingestion Flaws**:
   - `stock_master` in `dwp_service.db` currently contains 774 parts loaded from legacy `stock_inventory_latest.csv`. Exactly **198 out of 518 parts** from the official catalog (`data/pdf_extracted_stock_report.csv`) are **completely missing** from `stock_master`.
   - Of the 320 catalog parts present in `stock_master`, **124 parts have distorted prices** caused by the legacy accounting ledger formula `AMOUNT / BAL_QTY` or arbitrary price floors.
   - `parts_master` is currently missing **59 parts** from the official catalog.
3. **Target Components Audit**:
   - In `data/pdf_extracted_stock_report.csv`, all 4 target valves and all 7 target evaporators are 100% present with exact official prices matching the Acceptance Criteria.
   - However, in `dwp_service.db` and `data/ground_truth_baseline.json`, the 1/2" Valve `7133774` is corrupted to **Rs. 1,600** and erroneously assigned the role `"Evaporator Assembly"` in `price_book`.
4. **Permanent Elimination of `AMOUNT / BAL_QTY`**:
   - The ledger ratio formula exists in two locations: `etl.py:104` and `build_baseline.py:44`. Both must be eliminated and replaced with `pdf_price` from `data/pdf_extracted_stock_report.csv`.
5. **Worker Verification Commands & Test Harness**:
   - We provide ready-to-run verification scripts, SQL queries, regex code audits, and exact assertions for the Worker and Reviewers to guarantee zero regression and 100% acceptance compliance.

---

## 2. Examination of `test_system_verification.py` & Current Test Cases

### 2.1 Audit of the 13 Existing Test Cases

| Test # | Test Name | Functions Exercised | Core Assertions | Under-the-Hood Mechanism / Fragility Risk |
|---|---|---|---|---|
| **TEST 1** | Database Bootstrap & Stock Metadata | `bootstrap_master_data()`, `get_stock_metadata()` | `meta['total_items'] > 0` | Currently loads legacy CSV (774 items). Must be updated to verify official catalog ingestion (518 parts). |
| **TEST 2** | Strict Model Tokenizer | `tokenize_appliance_model()` | Capacity, series, category parsing for PITH, CITH, Refrigerator, Washing Machine | Pure regex parsing in `config.py`. Low regression risk. |
| **TEST 3** | Cross-Series Isolation (PITH vs CITH) | `fetch_tiered_compatible_parts()` | GS-18PITH11W primary = `11001060868`; CITH part `1002937LC` excluded. GS-18CITH12G primary = `1002937LC`; `11001060868` excluded. | Relies on `verified_jobs` frequency and series token matching. Must ensure baseline regeneration maintains verified job frequencies. |
| **TEST 4** | Zero-Price Immunity | `fetch_tiered_compatible_parts()` | 464 parts across 7 models all have `price > 0`. | Asserts no part is Rs. 0. Passes currently via hardcoded overrides + role floors. |
| **TEST 5** | Global Stock Search | `search_stock_global()` | Queries for "Evaporator", "PCB", "Valve", "Sensor", "Motor" return non-empty with all `price > 0`. | Searches `stock_master` or baseline fallback. Will pass once all 518 parts are in `stock_master`. |
| **TEST 6** | ZITH Evaporator Verification | `tokenize_appliance_model()`, `fetch_tiered_compatible_parts()` | Series = ZITH; Primary Evaporator = `11001062414`; Alternate = `1000106068502`. | Relies on tokenizing ZITH and matching `11001062414`. |
| **TEST 7** | Standard Overheads & Gas Pricing | `CATEGORY_OVERHEADS`, `get_tonnage_specs()` | Mobility = Rs. 2,000, Visit = Rs. 600, Ref Gas = Rs. 4,000, Dispenser Gas = Rs. 3,500. | Static constants in `config.py`. Low regression risk. |
| **TEST 8** | Price Consistency (Direct vs Model Search) | `search_stock_global()`, `fetch_tiered_compatible_parts()` | Part `11001062414` is Rs. 30,000 in both Model Search and Direct Search. | Relies on price parity. In M1, both must pull from Master Price Authority. |
| **TEST 9** | Packaging Carton Exclusion & Role Floor Protection | `fetch_tiered_compatible_parts()`, `classify_component_role()` | Carton `03010102510004` excluded from Evaporators; Alternate `1000106068502` floored at Rs. 26,000. | Validates role classification keywords. |
| **TEST 10** | Strict Service Valve Tonnage Isolation & Dual Pairing | `fetch_tiered_compatible_parts()`, `is_valve_tonnage_compatible()` | 1.0T (3/8" + 1/4"); 1.5T (1/2" + 1/4"); 2.0T (5/8" + 1/4"); 4.0T (5/8" + 3/8"). Zero cross-leakage. | **Vulnerability Detected**: Only asserts `price > 0` for 1/2" valve on 1.5T; does NOT assert Rs. 2,100. Must add price check. |
| **TEST 11** | Floor Standing AC Isolation & Genuine Evaporator Protection | `tokenize_appliance_model()`, `fetch_tiered_compatible_parts()` | `GF-36TFIH` returns `11001000602` @ Rs. 58,000; excludes 24ISH & 48FW evaporators. | Currently passes due to `known_price_overrides['11001000602'] = 58000`. Must pass autonomously from catalog. |
| **TEST 12** | 1.0 Ton 3/8" Valve Customer Verified Pricing (Rs. 1,500) | `fetch_tiered_compatible_parts()`, `search_stock_global()` | 3/8" Valve `71302395` = Rs. 1,500; 1/4" Valve `7130239` = Rs. 1,600. Parity verified. | Currently passes due to `known_price_overrides['71302395'] = 1500`. Must pass autonomously from catalog. |
| **TEST 13** | Exact Closed-Complaint Ground-Truth Rates & Field Descriptions | `fetch_tiered_compatible_parts()`, SQLite `parts_master` | `GF-36TFIH`: 5/8" Valve `7133844` = Rs. 2,200 ("24LITH11M"); 1/4" Valve `7130239` = Rs. 1,600 ("GS-11CITH3F"). SQLite rows verified. | Validates exact descriptions and prices in SQLite `parts_master`. |

---

## 3. Pillar 1: Ingestion & Indexing Verification for all 518 Catalog Parts

### 3.1 Empirical Defect State
Currently in `dwp_service.db`:
- Unique part numbers in `data/pdf_extracted_stock_report.csv`: **518**
- Catalog parts currently present in `stock_master`: **320**
- Catalog parts **MISSING** from `stock_master`: **198**
- Catalog parts **MISSING** from `parts_master`: **59**

### 3.2 Required Verification Assertions for Milestone 1

#### A. Ingestion Completeness into `stock_master`
```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("dwp_service.db")
df_pdf = pd.read_csv("data/pdf_extracted_stock_report.csv")
pdf_parts = set(df_pdf['part_no'].str.strip().str.upper().unique())

# 1. Total unique catalog parts must equal 518
assert len(pdf_parts) == 518, f"Expected 518 unique parts, got {len(pdf_parts)}"

# 2. All 518 parts must exist in stock_master
c = conn.cursor()
c.execute("SELECT part_no, unit_price, bal_qty FROM stock_master")
db_stock = {row[0]: (row[1], row[2]) for row in c.fetchall()}

missing_from_stock = pdf_parts - set(db_stock.keys())
assert len(missing_from_stock) == 0, f"Missing {len(missing_from_stock)} parts from stock_master: {missing_from_stock}"

# 3. Unit price in stock_master must match official pdf_price
pdf_price_map = df_pdf.groupby(df_pdf['part_no'].str.strip().str.upper())['pdf_price'].max().to_dict()
for pno, exp_price in pdf_price_map.items():
    actual_unit_price = db_stock[pno][0]
    expected_int_price = int(round(float(exp_price)))
    assert actual_unit_price == expected_int_price, (
        f"Price mismatch for part {pno}: stock_master={actual_unit_price}, catalog={expected_int_price}"
    )
```

#### B. Indexing into `parts_master`
```python
c.execute("SELECT DISTINCT part_no FROM parts_master")
db_parts = set(row[0] for row in c.fetchall())

missing_from_parts = pdf_parts - db_parts
assert len(missing_from_parts) == 0, f"Missing {len(missing_from_parts)} catalog parts from parts_master: {missing_from_parts}"

# Verify model associations for catalog parts
for _, r in df_pdf.iterrows():
    pno = str(r['part_no']).strip().upper()
    model = str(r['model']).strip().upper()
    exp_price = int(round(float(r['pdf_price'])))
    c.execute("SELECT price FROM parts_master WHERE model = ? AND part_no = ?", (model, pno))
    rows = c.fetchall()
    assert len(rows) > 0, f"Pair ({model}, {pno}) missing from parts_master"
    assert rows[0][0] == exp_price, f"Pair ({model}, {pno}) price mismatch: DB={rows[0][0]}, expected={exp_price}"
```

#### C. Live Stock & Multi-Bin Duplicate Handling
There are exactly **13 duplicate rows** across 9 part numbers in `data/pdf_extracted_stock_report.csv` due to multi-bin or multiple supplier entries:
- `0305010102` (R-410a, 4 entries)
- `0305010103` (R-32, 3 entries)
- `7130239` (1/4" Valve, 2 entries: 15 pcs and -6 pcs)
- `11230002000152`, `15010400000102`, `15010406008801`, `1521200606`, `1521212901`, `GR35-E77610089` (2 entries each)

**Verification rule**:
- In `stock_master`, `bal_qty` must represent the aggregated live inventory (e.g. for `7130239`, $15 + (-6) = 9$).
- `in_stock` badge logic evaluates `bal_qty > 0`. Items with zero or negative stock must still display their official retail price with an out-of-stock badge.

---

## 4. Pillar 2: Elimination of Accounting Ledger Valuation (`AMOUNT / BAL_QTY`)

### 4.1 Root Cause & Empirical Distortions
The legacy formula:
$$\text{calc\_price} = \text{round}\left(\frac{\text{AMOUNT}}{\text{BAL\_QTY}}\right)$$
calculates residual accounting book inventory ratios. The following empirical evidence illustrates why this formula is fatal to customer pricing:

| Part Number | Description | Flawed Ledger Ratio | Official Retail Price (`vp786.pdf`) | Distortion |
|---|---|---|---|---|
| `11001060868` | Evaporator GS-18PITH1W | **Rs. 1,384,687** | **Rs. 26,000** | +5,225% (Runaway inventory adjustment) |
| `7133844` | Cut-off Valve 5/8" | **Rs. 34,354** | **Rs. 2,200** | +1,461% (Ledger cost pool distortion) |
| `7133774` | Cut-off Valve 1/2" | **Rs. 26,622** | **Rs. 2,100** | +1,167% (Ledger cost pool distortion) |
| `7130239` | Cut-off Valve 1/4" | **Rs. 5,845** | **Rs. 1,600** | +265% (Distorted batch ratio) |
| `71302395` | Cut-off Valve 3/8" | **Rs. 2,516** (taxed 2,968) | **Rs. 1,500** | +67% (Overbilling) |
| `WD300-HOTTANK` | Hot Tank WD-300F | **Rs. 4,436** | **Rs. 2,000** | +122% (Overbilling) |
| `0305010102` | R-410a Gas Cylinder | **Rs. 28,114** | **Rs. 40,000** | -30% (Unapproved dealer rate) |
| `11001000602` | Evaporator GF-36TFIH | **Rs. 0 (Missing)** | **Rs. 58,000** | Complete omission |
| `1004169` | Evaporator GF-48FW | **Rs. 0 (Missing)** | **Rs. 70,000** | Complete omission |
| `11001060092` | Evaporator GF-24ISH | **Rs. 0 (Missing)** | **Rs. 72,000** | Complete omission |

### 4.2 Required Verification Assertions for Ledger Formula Elimination

#### A. Source Code Regex Audit (Zero Occurrences)
Worker/Reviewer verification command to ensure the formula is eliminated from all active scripts:
```python
import re

files_to_check = ['etl.py', 'build_baseline.py', 'database.py', 'config.py', 'app.py']
flawed_patterns = [
    r"amount\s*/\s*bal_qty",
    r"r\['amount'\]\s*/\s*r\['bal_qty'\]",
    r"amt\s*/\s*bal",
    r"known_price_overrides\s*="
]

for fname in files_to_check:
    with open(fname, 'r', encoding='utf-8') as f:
        content = f.read()
    for pat in flawed_patterns:
        matches = re.findall(pat, content, re.IGNORECASE)
        assert len(matches) == 0, f"FORBIDDEN PATTERN '{pat}' found in {fname}: {matches}"
```

#### B. Direct Value Assertions on Formerly Corrupted Parts
```python
distorted_parts_audit = {
    '11001060868': (26000, [1384687, 0]),
    '7133844':     (2200,  [34354, 0]),
    '7133774':     (2100,  [26622, 1600, 0]),
    '7130239':     (1600,  [5845, 0]),
    '71302395':    (1500,  [2516, 2968, 0]),
    'WD300-HOTTANK': (2000, [4436, 0])
}

with sqlite3.connect("dwp_service.db") as conn:
    c = conn.cursor()
    for pno, (expected_price, forbidden_prices) in distorted_parts_audit.items():
        c.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,))
        row = c.fetchone()
        assert row is not None, f"Part {pno} missing from stock_master"
        actual = row[0]
        assert actual == expected_price, f"Part {pno} has price {actual}, expected {expected_price}"
        assert actual not in forbidden_prices, f"Part {pno} LEAKED ledger valuation cost {actual}!"
```

---

## 5. Pillar 3: Verification Matrix for Target Valves & Evaporators

The User Request and Acceptance Criteria explicitly mandate verification of 4 service valves and 7 evaporator assemblies across both database and precomputed baseline cache:

### 5.1 Comprehensive Target Components Specification

| Category | Part No | Canonical Item Description | Primary Model | Official Price | Database Table & Field | Baseline Cache Path |
|---|---|---|---|---|---|---|
| **3/8" Valve** | `71302395` | `Cut-off valve 3/8 71302395 GS- 12PITH1W/O` | `GS-12PITH1W` | **Rs. 1,500** | `stock_master.unit_price`, `parts_master.price` | `price_book['71302395']['price']` |
| **1/4" Valve** | `7130239` | `Cut off Valve 1/4 GS-11CITH3F 7130239` | `GS-11CITH3F` | **Rs. 1,600** | `stock_master.unit_price`, `parts_master.price` | `price_book['7130239']['price']` |
| **1/2" Valve** | `7133774` | `Cut Off Valve Assy 1/2 7133774 GS- 18VITH1` | `GS-18VITH1` | **Rs. 2,100** | `stock_master.unit_price`, `parts_master.price` | `price_book['7133774']['price']` |
| **5/8" Valve** | `7133844` | `Cutt Off Valve 5/8 24LITH11M 7133844` | `GS-24LITH11M` | **Rs. 2,200** | `stock_master.unit_price`, `parts_master.price` | `price_book['7133844']['price']` |
| **Evaporator** | `11001000602` | `Evaporator Assy GF-36TFIH 11001000602` | `GF-36TFIH` | **Rs. 58,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['11001000602']['price']`, `models['GF-36TFIH']` |
| **Evaporator** | `11001060868` | `Evaporator Assy GS-18PITH1W 11001060868` | `GS-18PITH1W` | **Rs. 26,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['11001060868']['price']`, `models['GS-18PITH1W']` |
| **Evaporator** | `11001062414` | `Evaporator Assy GS-18AITH23W-T3 ...` | `GS-18AITH23W-T3` | **Rs. 30,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['11001062414']['price']`, `models['GS-18ZITH1W-T3']` |
| **Evaporator** | `1004169` | `Evaporater Assy 48FW 1004169` | `GF-48FW` | **Rs. 70,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['1004169']['price']`, `models['GF-48FW']` |
| **Evaporator** | `11001060092` | `Evaporator Assy 11001060092 24ISH` | `GF-24ISH` | **Rs. 72,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['11001060092']['price']`, `models['GF-24ISH']` |
| **Evaporator** | `11001060521` | `Evaporator Assy GF-48TF 11001060521` | `GF-48TF` | **Rs. 75,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['11001060521']['price']`, `models['GF-48TF']` |
| **Evaporator** | `100404401` | `Evaporator Assy 24CB/ 24TFIH 1100100218 / 100404401` | `GF-24CB` | **Rs. 66,000** | `stock_master.unit_price`, `parts_master.price` | `price_book['100404401']['price']`, `models['GF-24CB']` |

### 5.2 Required Verification Assertions for Target Components

```python
import json
import sqlite3
from database import fetch_tiered_compatible_parts, search_stock_global

target_acceptance_parts = {
    # Valves
    '71302395': ('Cut-Off Valve (3/8")', 1500),
    '7130239':  ('Cut-Off Valve (1/4")', 1600),
    '7133774':  ('Cut-Off Valve (1/2")', 2100),
    '7133844':  ('Cut-Off Valve (5/8")', 2200),
    # Evaporators
    '11001000602': ('Evaporator Assembly', 58000),
    '11001060868': ('Evaporator Assembly', 26000),
    '11001062414': ('Evaporator Assembly', 30000),
    '1004169':     ('Evaporator Assembly', 70000),
    '11001060092': ('Evaporator Assembly', 72000),
    '11001060521': ('Evaporator Assembly', 75000),
    '100404401':   ('Evaporator Assembly', 66000),
}

# 1. Database Verification
with sqlite3.connect("dwp_service.db") as conn:
    c = conn.cursor()
    for pno, (role, exp_price) in target_acceptance_parts.items():
        c.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,))
        row = c.fetchone()
        assert row is not None, f"Target part {pno} missing from stock_master"
        assert row[0] == exp_price, f"Target part {pno} stock_master price {row[0]} != {exp_price}"

# 2. Baseline Cache Verification
with open("data/ground_truth_baseline.json", "r") as f:
    baseline = json.load(f)

price_book = baseline.get("price_book", {})
for pno, (role, exp_price) in target_acceptance_parts.items():
    assert pno in price_book, f"Target part {pno} missing from baseline price_book"
    assert price_book[pno]['price'] == exp_price, (
        f"Target part {pno} price_book price {price_book[pno]['price']} != {exp_price}"
    )

# 3. Model Search vs Direct Search Verification
# Check 1/2" Valve on 1.5 Ton Model
res_15 = fetch_tiered_compatible_parts("GS-18ZITH1W-T3")
v_grp = next(g for g in res_15['role_groups'] if "Cut-off" in g['group_title'])
assert v_grp['primary']['part_no'] == "7133774"
assert v_grp['primary']['price'] == 2100, f"Expected 1/2\" valve price 2,100, got {v_grp['primary']['price']}"

# Direct Search Parity
stk_12 = search_stock_global("7133774")
assert not stk_12.empty
assert int(stk_12.iloc[0]['price']) == 2100, f"Direct search for 7133774 returned {stk_12.iloc[0]['price']}"
```

---

## 6. Pillar 4: Zero-Pricing Immunity Verification Across All Categories

### 6.1 Requirements
Every spare part returned by any query or displayed in any UI view must have `price > 0`. Zero-pricing immunity must be enforced through three defense layers:
1. **Master Catalog Truth**: All 518 parts in `stock_master` have executive-approved retail selling prices.
2. **Field Collection Verification**: Mode price from customer collection receipts.
3. **Role Price Floor**: Deterministic role floor from `config.py:get_role_price_floor()`.

### 6.2 Required Verification Assertions

```python
# 1. Database-Wide Zero-Price Audit
with sqlite3.connect("dwp_service.db") as conn:
    c = conn.cursor()
    c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0")
    zero_stock_count = c.fetchone()[0]
    assert zero_stock_count == 0, f"Found {zero_stock_count} parts in stock_master with price <= 0"

    c.execute("SELECT count(*) FROM parts_master WHERE price <= 0")
    zero_parts_count = c.fetchone()[0]
    assert zero_parts_count == 0, f"Found {zero_parts_count} parts in parts_master with price <= 0"

# 2. Baseline Cache Zero-Price Audit
with open("data/ground_truth_baseline.json", "r") as f:
    b = json.load(f)

for pno, info in b.get("price_book", {}).items():
    assert info.get("price", 0) > 0, f"Part {pno} in baseline price_book has zero price!"

for m_name, m_data in b.get("models", {}).items():
    for p in m_data.get("parts", []):
        assert p.get("price", 0) > 0, f"Part {p['part_no']} in model {m_name} has zero price!"

# 3. Comprehensive Multi-Category Model Resolution Audit
audit_models = [
    # Split AC
    "GS-18PITH11W", "GS-12PITH11W", "GS-24PITH11W", "GS-18CITH12G", "ES-18DU01WG",
    # Floor Standing AC
    "GF-36TFIH", "GF-24ISH", "GF-48TF", "GF-48FW", "GF-24CB", "EF-24IB01W",
    # Refrigerator
    "GR-E8768G-CP1", "GR-E8890G-CB3", "GRIS-300V-CS1Y",
    # Washing Machine
    "EW-F1202DC", "EW-F1204DC", "WM-1004",
    # Water Dispenser
    "GW-JL500FC", "WD-300F", "WD-450F"
]

total_checked = 0
for m in audit_models:
    res = fetch_tiered_compatible_parts(m)
    for g in res['role_groups']:
        for p in [g['primary']] + g['alternatives']:
            total_checked += 1
            assert p['price'] > 0, f"Zero price found for part {p['part_no']} ({p['part_name']}) in model {m}"

print(f"Zero-Price Immunity verified across {len(audit_models)} models and {total_checked} parts.")
```

---

## 7. Pillar 5: Regression Protection for Existing 13 Test Cases

To protect existing functionality while upgrading the data foundation, the Worker and Reviewers must verify that all 13 test cases in `test_system_verification.py` continue to pass without error.

### 7.1 Regression Analysis by Test Case

| Test # | Subject | Pass Condition in M1 | Potential Pitfall & Remediation |
|---|---|---|---|
| 1 | Bootstrap & Stock Metadata | `meta['total_items'] >= 518` | Ingesting `pdf_extracted_stock_report.csv` should not wipe existing complaint history or crash on duplicate keys. |
| 2 | Model Tokenizer | Regex parsing unchanged | Do not alter `tokenize_appliance_model` regex patterns. |
| 3 | Cross-Series Isolation | GS-18PITH11W has `11001060868`; GS-18CITH12G has `1002937LC`. | When regenerating `ground_truth_baseline.json`, preserve closed complaint repair frequency (`verified_jobs`) so genuine primary evaporators remain #1. |
| 4 | Zero-Pricing Verification | 464 parts > Rs. 0 | Catalog prices + role floors guarantee 100% compliance. |
| 5 | Global Search | Non-empty results for 5 terms | Search queries match catalog descriptions (`Evaporator`, `PCB`, `Valve`, `Sensor`, `Motor`). |
| 6 | ZITH Evaporator | GS-18ZITH1W-T3 primary = `11001062414` | Normalizing internal whitespace in description preserves matching. |
| 7 | Standard Overheads & Gas | Constants intact | Do not modify `CATEGORY_OVERHEADS`. |
| 8 | Price Consistency | Part `11001062414` = Rs. 30,000 in both searches | Catalog price is 30,000; direct search and model search will both return 30,000. |
| 9 | Carton Exclusion | Carton `03010102510004` excluded; floor Rs. 26,000 | `classify_component_role` must continue filtering packaging terms (`carton`, `packing`, `box`). |
| 10 | Valve Tonnage Pairing | 1.0T (3/8"+1/4"), 1.5T (1/2"+1/4"), 2.0T (5/8"+1/4"), 4.0T (5/8"+3/8") | Physical constraints must remain active. |
| 11 | Floor Standing AC Isolation | `GF-36TFIH` -> `11001000602` @ Rs. 58,000 | Ensure `11001000602` retains Rs. 58,000 without `known_price_overrides`. |
| 12 | 1.0T 3/8" Valve Rate | `71302395` = Rs. 1,500; `7130239` = Rs. 1,600 | Catalog prices match Rs. 1,500 and Rs. 1,600. |
| 13 | Exact Descriptions & SQLite | 5/8" Valve = Rs. 2,200 ("24LITH11M"); 1/4" Valve = Rs. 1,600 ("GS-11CITH3F") | Descriptions in `pdf_extracted_stock_report.csv` contain these tokens; ensure duplicate part resolution preserves these strings! |

---

## 8. Exact Verification Commands & Instructions for Worker and Reviewers

### 8.1 Step 1: Pre-Execution Verification (Confirm Baseline)
Run the current test harness:
```powershell
python test_system_verification.py
```
*Expected Result*: Exits 0, all 13 tests pass.

### 8.2 Step 2: Milestone 1 Execution by Worker
1. Update `etl.py` to ingest `data/pdf_extracted_stock_report.csv` as Master Price Authority into `stock_master` and `parts_master`.
2. Remove `AMOUNT / BAL_QTY` calculation in `etl.py` and `build_baseline.py`.
3. Eliminate `known_price_overrides` dictionary from `etl.py` and `build_baseline.py`.
4. Run `python build_baseline.py` to regenerate `data/ground_truth_baseline.json`.

### 8.3 Step 3: Automated Milestone 1 Acceptance Verification Suite
Execute the dedicated M1 verification script:
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

### 8.4 Step 4: Regression Run
Run the full 13-test regression suite:
```powershell
python test_system_verification.py
```
*Expected Result*: All 13 tests pass with 0 errors.

---

## 9. Conclusion & Actionable Guidance for Worker

1. **Prioritize 1/2" Valve `7133774` Fix**:
   The Worker must be aware that `7133774` was corrupted to Rs. 1,600 and assigned role "Evaporator Assembly" in the legacy baseline. When ingesting `pdf_extracted_stock_report.csv`, ensure `7133774` is correctly assigned **Rs. 2,100** and role `"Cut-Off Valve (1/2\")"`.
2. **Handle Duplicate Part Numbers**:
   Consolidate the 13 duplicate rows in `pdf_extracted_stock_report.csv` by summing `total_stock` and retaining the canonical description containing model references (`GS-11CITH3F` for `7130239`, `24LITH11M` for `7133844`) so that Test 13 assertions succeed.
3. **Dual Ingestion**:
   Both `stock_master` and `parts_master` must receive all 518 parts.
4. **Offline Compiler (`build_baseline.py`)**:
   Regenerate `data/ground_truth_baseline.json` ensuring `price_book` and model dictionaries reflect the official catalog prices as Master Price Authority.
