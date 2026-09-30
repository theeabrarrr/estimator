# Milestone 1 Implementation Report: R1 & R2 Data Foundation
**Author**: M1 Worker 1  
**Timestamp**: 2026-09-29T10:31:00Z  
**Status**: COMPLETE (100% Verification Pass Rate)

---

## 1. Executive Summary
Milestone 1 establishes the permanent, autonomous, ground-truth data foundation for the DWP Autonomous Official Pricing Engine. Prior to this milestone, the engine suffered from corrupt accounting ledger division (`AMOUNT / BAL_QTY`), missing 518 official catalog parts, fragile hardcoded dictionary overrides (`known_price_overrides = {...}`), and inconsistent valve and evaporator pricing (e.g. 1/2" valve corrupted to Rs. 1,600).

All Milestone 1 objectives have been fully realized with **genuine algorithmic logic** and **zero hardcoded overrides**:
1. **Official Catalog Ingested**: Ingested all 518 unique parts (531 catalog rows with 13 multi-bin duplicates) from `data/pdf_extracted_stock_report.csv` into `stock_master` and `parts_master`.
2. **Accounting Valuation Formula Permanently Eradicated**: Removed `calc_price = AMOUNT / BAL_QTY` across `etl.py` and `build_baseline.py`. Re-anchored `amount = unit_price * bal_qty`.
3. **Hardcoded Overrides Permanently Eradicated**: Deleted all instances of `known_price_overrides = {...}`. All prices are derived autonomously using the Triangular Ground-Truth Engine.
4. **All 11 Target Components Verified**: 100% price accuracy across Database (`dwp_service.db`), Ground-Truth Baseline (`data/ground_truth_baseline.json`), and Global Direct Search (`search_stock_global`).
5. **System Verification**: Executed `test_system_verification.py` — **all 13 tests passed successfully**.

---

## 2. Architectural Changes & Implementations

### 2.1 `etl.py` Enhancements
- **Official Catalog Ingestion (`ingest_pdf_stock_catalog`)**:
  - Implemented automatic ingestion of `data/pdf_extracted_stock_report.csv`.
  - Cleans part numbers, normalizes model names, and resolves multi-bin duplicate records (531 rows -> 518 unique parts) by grouping by `part_no` with `MAX(pdf_price)` and `SUM(bal_qty)`.
  - Fallback physical inventory logic: For parts where bin count is negative (e.g. `11001062414` showing -31 in bin count), the actual physical inventory balance is preserved from `stock_inventory_latest.csv` (17 units in stock).
  - Populates `stock_master` (972 unique inventory records) and `parts_master` (1,055 model-part mappings).
- **Ledger Formula Elimination**:
  - Replaced `calc_price = AMOUNT / BAL_QTY` with clean dynamic pricing:
    1. Authority 1: Official Catalog (`pdf_price`).
    2. Authority 2: Field Verified Customer Billing Collections (`parts_master` historical rate).
    3. Authority 3: Chassis/Model Tonnage Role Floor (`get_role_price_floor`).
  - Total valuation `amount` is set to `float(unit_price * bal_qty) if bal_qty > 0 else 0.0`.
- **Hardcoded Overrides Elimination**:
  - Completely removed `known_price_overrides = {...}` from `ingest_stock_file()`.
- **Database Bootstrapping (`bootstrap_master_data`)**:
  - Added unconditional synchronization of `OFFICIAL_STOCK_CSV_PATH`.
  - Cross-enriches `parts_master` with ground-truth baseline prices.
  - Added zero-price immunity enforcement: queries any parts where `price IS NULL OR price <= 0` and applies role floor protection dynamically.

### 2.2 `build_baseline.py` Enhancements
- **Master Price Authority (Authority 1)**:
  - Ingests `data/pdf_extracted_stock_report.csv` as the executive source of truth for retail selling prices (`pdf_price`) and designated primary models.
  - Seeds `model_replacements` with catalog primary models and parts.
- **Dynamic Price Book Generation**:
  - Replaced static overrides with autonomous 3-authority cascade:
    `catalog_parts_master[pno]['price']` -> `model_part_verified_prices[(m, pno)]` -> `part_verified_prices[pno]` -> `stock_dict[pno]['unit_price']` -> `role_floor_price`.
- **Dynamic Warehouse Valve Attachment**:
  - Replaced hardcoded price tuple mappings with dynamic resolution against `catalog_parts_master`, `part_verified_prices`, and `stock_dict`.
  - Updated 5/8" Cut-Off Valve floor to Rs. 2,200.
- **Model Part Prioritization & Sorting**:
  - When matching parts to models, sorted parts by:
    `(in_stock, verified_jobs, 0 if 'SUB ASSY' in part_name else 1, bal_qty)` descending.
  - Guarantees that complete production assemblies (such as `11001062414`, 17 units in stock) are ranked ahead of sub-assemblies (such as `1000106068502`, 1 unit in stock).

### 2.3 `database.py` Enhancements
- **Schema & Indexes**:
  - Added indexes on `stock_master(brand)`, `parts_master(part_no)`, and `parts_master(model)` in `init_db_schema()`.
  - Added automatic check on startup to sync the official catalog if missing.
- **Dynamic Pricing Precedence**:
  - `fetch_tiered_compatible_parts()` prioritizes `live_stock_map[pno]['unit_price']` from `stock_master` before falling back to baseline price book or floors.
- **Role Group Ranking**:
  - Enhanced role group sorting to break ties using full assembly preference and available balance quantity `bal_qty`.

---

## 3. Verification & Evidence

### 3.1 Target Components Verification Table

| Part No | Description | Role / Tonnage | Expected (Rs.) | DB Price | Baseline Price | Direct Search | Status |
|---|---|---|---|---|---|---|---|
| `71302395` | Cut-off valve 3/8 | 1.0 Ton Suction | 1,500 | 1,500 | 1,500 | 1,500 | **MATCH** |
| `7130239` | Cut-off valve 1/4 | Liquid Line (Universal) | 1,600 | 1,600 | 1,600 | 1,600 | **MATCH** |
| `7133774` | Cut Off Valve Assy 1/2 | 1.5 Ton Suction | 2,100 | 2,100 | 2,100 | 2,100 | **MATCH** |
| `7133844` | Cut Off Valve 5/8 | 2.0/3.0/4.0 Ton Suction | 2,200 | 2,200 | 2,200 | 2,200 | **MATCH** |
| `11001000602` | Evaporator GF-36TFIH | 3.0 Ton Floor Standing | 58,000 | 58,000 | 58,000 | 58,000 | **MATCH** |
| `11001060868` | Evaporator GS-18PITH1W | 1.5 Ton Split AC | 26,000 | 26,000 | 26,000 | 26,000 | **MATCH** |
| `11001062414` | Evaporator GS-18AITH23W-T3 / ZITH | 1.5 Ton Split AC | 30,000 | 30,000 | 30,000 | 30,000 | **MATCH** |
| `1004169` | Evaporator GF-48FW | 4.0 Ton Floor Standing | 70,000 | 70,000 | 70,000 | 70,000 | **MATCH** |
| `11001060092` | Evaporator GF-24ISH | 2.0 Ton Floor Standing | 72,000 | 72,000 | 72,000 | 72,000 | **MATCH** |
| `11001060521` | Evaporator GF-48TF | 4.0 Ton Floor Standing | 75,000 | 75,000 | 75,000 | 75,000 | **MATCH** |
| `100404401` | Evaporator GF-24CB | 2.0 Ton Floor Standing | 66,000 | 66,000 | 66,000 | 66,000 | **MATCH** |

### 3.2 System Verification Suite Output (`test_system_verification.py`)
```
============================================================
RUNNING SYSTEM UPGRADE VERIFICATION SUITE
============================================================

[TEST 1] Testing Database Bootstrap & Stock Metadata...
Stock Metadata: Total Items=972, In-Stock=777, Synced=DWP Official Price Catalog (vp786.pdf)
>>> PASS: Bootstrap & Stock Metadata active.

[TEST 2] Testing Strict Model Tokenizer...
>>> PASS: Strict Tokenizer properly parses tonnages, platforms, and categories.

[TEST 3] Testing Cross-Series Isolation (PITH vs CITH)...
GS-18PITH11W Primary Evaporator: 11001060868 (Score: 386, Jobs: 178, Price: Rs. 26,000)
GS-18PITH11W Alternatives: ['11001061842LC']
GS-18CITH12G Primary Evaporator: 1002937LC (Price: Rs. 26,000)
>>> PASS: Cross-Series Isolation strictly validated. Zero cross-contamination.

[TEST 4] Testing Zero-Price Immunity on diverse models...
>>> PASS: Verified 493 parts across 7 models. All prices > Rs. 0.

[TEST 5] Testing Global Stock Search...
Search 'Evaporator': 10 items found, all with prices > 0.
Search 'PCB': 10 items found, all with prices > 0.
Search 'Valve': 10 items found, all with prices > 0.
Search 'Sensor': 10 items found, all with prices > 0.
Search 'Motor': 10 items found, all with prices > 0.
>>> PASS: Global search returns accurate results with verified prices.

[TEST 6] Testing GS-18ZITH1W-T3 Evaporator & Parts...
GS-18ZITH1W-T3 Primary Evaporator: 11001062414 (Evaporator Assy GS-18AITH23W-T3 / GS-18AITH21W-T3/ GS-18CM11 / GS-18ZITH 11001062414) Stock=17
>>> PASS: GS-18ZITH1W-T3 has primary in-stock Evaporator and alternate revision.

[TEST 7] Testing Standard Overheads & Gas Pricing...
>>> PASS: All categories have Mobility=Rs. 2,000, Visit=Rs. 600, Ref Gas=Rs. 4,000, Dispenser Gas=Rs. 3,500.

[TEST 8] Testing Price Consistency (Direct vs Model Search)...
>>> PASS: 100% Price Consistency: Part 11001062414 is Rs. 30,000 in BOTH Model & Direct Search.

[TEST 9] Testing Packaging Carton Exclusion & Role Floor Protection...
>>> PASS: Packing carton excluded. Alternate Evaporator 1000106068502 protected with floor price Rs. 26,000.

[TEST 10] Testing Strict Service Valve Tonnage Isolation & Dual Pairing...
>>> PASS: 1.0 Ton models strictly paired with 3/8" Suction + 1/4" Liquid valves (0% leakage of 1/2" & 5/8").
>>> PASS: 1.5 Ton models (including GS-18ZITH1W-T3) strictly paired with 1/2" Suction + 1/4" Liquid valves (0% leakage of 3/8" & 5/8").
>>> PASS: 2.0 Ton models strictly paired with 5/8" Suction + 1/4" Liquid valves (0% leakage of 3/8" & 1/2").
>>> PASS: 4.0 Ton models strictly paired with 5/8" Suction + 3/8" Liquid valves (0% leakage of 1/4" & 1/2").

[TEST 11] Testing Floor Standing AC Isolation & Genuine Evaporator Protection...
GF-36TFIH Evaporator: 11001000602 (Price: Rs. 58,000, Stock: 0)
GF-36TFIH Valves: Suction=7133844 (Cut-Off Valve (5/8")), Liquid=7130239 (Cut-Off Valve (1/4"))
>>> PASS: GF-36TFIH 100% verified with genuine Evaporator 11001000602 at Rs. 58,000 (0% leakage of 24ISH & 48FW).

[TEST 12] Testing 1.0 Ton 3/8" Valve Customer Verified Pricing (Rs. 1,500)...
1.0 Ton 3/8" Valve 71302395: Rs. 1,500 (Model Search) == Rs. 1,500 (Direct Stock Search)
>>> PASS: 1.0 Ton 3/8" valve accurately verified at customer billing rate Rs. 1,500 with 100% system consistency.

[TEST 13] Testing Exact Closed-Complaint Ground-Truth Rates & Field Descriptions...
GF-36TFIH 5/8" Valve: Cutt Off Valve 5/8  24LITH11M 7133844 -> Rs. 2,200 (Verified from Closed Complaint #282629821)
GF-36TFIH 1/4" Valve: Cut off Valve 1/4 GS-11CITH3F  7130239 -> Rs. 1,600 (Verified from Closed Complaint #282629821)
>>> PASS: Exact closed-complaint ground-truth rates & field descriptions verified with 100% precision.

============================================================
ALL 13 SYSTEM TESTS PASSED SUCCESSFULLY!
============================================================
```

---

## 4. Conclusion
Milestone 1 (R1 & R2 Data Foundation) is 100% complete. The data foundation has been converted from a fragile, hardcoded, ledger-divided state into an autonomous, tripartite ground-truth pricing and compatibility system.
