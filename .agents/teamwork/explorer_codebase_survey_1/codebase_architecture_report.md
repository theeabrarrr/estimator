# Comprehensive Codebase Architecture, Test Harness & Multi-Tier Resolution Survey Report

**Author:** Codebase Test Explorer (`explorer_codebase_survey_1`)  
**Date:** 2026-09-29  
**Target Repository:** `c:\Users\PC\Desktop\estimator`  
**Reference Specification:** `.agents/teamwork/ORIGINAL_REQUEST.md`

---

## 1. Executive Summary & Codebase Architecture

The **DWP Service Field Assistant & Estimator Platform** is an enterprise diagnostics, inventory tracking, cost estimation, unit historical audit, and technician KPI management system tailored for **Gree and EcoStar** home appliances.

### High-Level Architecture
- **Application Framework**: Single-page Python application powered by **Streamlit** (`app.py`), configured in multi-tab layout (`tab_estimator`: Cost & Stock Estimator, `tab_history`: Unit & Customer History, `tab_perf`: Technician Performance), with an administrative sidebar for data synchronization. No external REST frameworks (FastAPI, Flask, or Django) are present; all business logic and presentation are integrated in Python.
- **Persistence & Storage Layer**:
  - Embedded local database: **SQLite 3** (`dwp_service.db`) configured with `PRAGMA journal_mode=WAL;` and 30-second connection timeout for concurrency.
  - High-speed pre-computed baseline: **JSON file** (`data/ground_truth_baseline.json`, 2.69 MB) caching 354+ models, 186+ series platforms, global stock metadata, and a verified price book.
  - Authoritative Data Sources:
    1. `data/pdf_extracted_stock_report.csv` (from `vp786.pdf`): Official Karachi Store Stock Report containing 518 unique parts with official retail selling prices (`pdf_price`) and live warehouse stock (`total_stock`).
    2. `quality_feedback_report_28SEP2026_142900.csv`: 13,965 closed service complaint records.
    3. `Detail_Collection_28SEP26_023634PM.xlsx`: 6,150 customer/warranty collection billing transactions.
    4. `data/stock_inventory_latest.csv`: 771 raw accounting warehouse ledger records.
- **Core Pipeline Modules**:
  1. `config.py` (538 lines): Core business rules, category overheads, strict regex model tokenizer, component classification, role price floors, and valve physical pairing constraints.
  2. `database.py` (521 lines): SQLite schema initialization, tiered compatibility matching engine (`fetch_tiered_compatible_parts`), global warehouse stock search (`search_stock_global`), and history queries.
  3. `etl.py` (344 lines): Ingestion pipelines for stock inventory, quality feedback, customer collections, and technician performance tracking.
  4. `build_baseline.py` (484 lines): Offline ETL indexer fusing closed complaints, collection transactions, and stock inventory into `data/ground_truth_baseline.json`.
  5. `test_system_verification.py` (306 lines): End-to-end regression and verification test harness.

---

## 2. Detailed Codebase Component Survey

### 2.1 Database Access Layer & Schema (`database.py` & `etl.py`)
The SQLite database `dwp_service.db` manages four primary tables:

1. **`stock_master`**:
   ```sql
   CREATE TABLE stock_master (
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
   );
   CREATE INDEX idx_stock_pno ON stock_master(part_no);
   CREATE INDEX idx_stock_desc ON stock_master(item_desc);
   CREATE INDEX idx_stock_cat ON stock_master(category);
   ```
   - **Current Flaw Identified**: Currently, `etl.py` (lines 103-106) and `build_baseline.py` (lines 44-45) calculate:
     $$\text{calc\_price} = \text{round}\left(\frac{\text{AMOUNT}}{\text{BAL\_QTY}}\right)$$
     This formula computes accounting inventory book valuations rather than official retail prices approved by management. For example, 3/8" Valve (`71302395`) has ledger ratio Rs. 2,516 (Rs. 2,968 with sales tax), whereas the official retail price is Rs. 1,500. Currently, hardcoded dictionary overrides (`known_price_overrides`) patch these prices. Ingesting `pdf_extracted_stock_report.csv` directly will permanently replace this formula.

2. **`parts_master`**:
   ```sql
   CREATE TABLE parts_master (
       model TEXT,
       part_no TEXT,
       part_name TEXT,
       price INTEGER,
       PRIMARY KEY (model, part_no)
   );
   ```
   Stores model-specific hardware replacement history extracted from closed complaints (`quality_feedback_report`) and baseline ground-truth.

3. **`history_master`**:
   ```sql
   CREATE TABLE history_master (
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
   );
   CREATE INDEX idx_hist_search ON history_master(serial, phone, complaint_no);
   CREATE INDEX idx_hist_model ON history_master(model);
   ```

4. **`tech_performance_master`**:
   ```sql
   CREATE TABLE tech_performance_master (
       complaint_no TEXT PRIMARY KEY,
       technician_name TEXT,
       status TEXT,
       closed_date TEXT
   );
   CREATE INDEX idx_tp ON tech_performance_master(technician_name, status, closed_date);
   ```

### 2.2 Service Overheads & Labor Rules (`config.py`)
- Standard charges configured in `CATEGORY_OVERHEADS`:
  - **Technician Visit Charges**: Fixed at **Rs. 600** across all appliance categories.
  - **Mobility / Labor Charges**: Fixed at **Rs. 2,000** across all appliance categories.
  - **Refrigerant Gas Charging**:
    - Refrigerator: R-600 Gas default = **Rs. 4,000**
    - Water Dispenser: R-134a Gas default = **Rs. 3,500**
    - Floor Standing AC: Commercial Gas default = **Rs. 13,000**
    - Split AC: Dynamic by tonnage:
      - 1.0 Ton: Rs. 5,500
      - 1.5 Ton: Rs. 7,000
      - 2.0 Ton: Rs. 8,500
      - 3.0 Ton: Rs. 10,000
      - 4.0 Ton / 5.0 Ton: Rs. 13,000

### 2.3 Component Classification & Price Floor Protection (`config.py`)
- **Packaging Carton Exclusion**: `classify_component_role` strips packaging (`carton`, `packing`, `tray`, `support`, `foam`, `bracket`, `box`) from cooling and electrical roles, categorizing them as `"Component Hardware"`. This guarantees that items like packing carton `03010102510004` never pollute `"❄️ Evaporator Assemblies"`.
- **Role Price Floors**: `get_role_price_floor(role, ton, cat)` prevents fractional FOB accounting costs from reaching users by enforcing realistic market minimums:
  - 1.5 Ton Evaporator: Rs. 26,000
  - 3.0 Ton Evaporator: Rs. 55,000
  - 4.0 Ton Evaporator: Rs. 70,000
  - Inverter PCBs: Rs. 35,000 – Rs. 55,000
  - Service Valves: Rs. 1,500 – Rs. 3,200

### 2.4 Model Tokenization & Platform Isolation (`config.py`)
`tokenize_appliance_model(model_str)` systematically decomposes appliance model strings into:
- `brand`: `"Gree"` (prefixes `GS-`, `GR-`, `GF-`, `GW-`), `"EcoStar"` (prefixes `ES-`, `EW-`, `CX-`, `EM-`), or `"Other"`.
- `category`: `"Split AC"`, `"Floor Standing AC"`, `"Refrigerator"`, `"Washing Machine"`, `"Water Dispenser"`, `"LED TV"`, or `"Microwave Oven"`.
- `tonnage`: Capacity mapping:
  - Split AC: Regex extraction of `-(10|11|12|16|18|24|26|36|48|60)`.
  - Floor Standing AC: `GF-24...` -> 2.0 Ton; `GF-36...` -> 3.0 Ton; `GF-48...` -> 4.0 Ton; `GF-60...` -> 5.0 Ton.
- `series`: Strict platform token matching from 29 series tokens:
  `['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'FWITH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'ISH', 'FW', 'TF', 'CD', 'CB']`.
- `series_key`: Composite key formatted as `{brand}|{category}|{tonnage}|{series}`.

---

## 3. Test Harness Execution & Verification Results

The automated regression test suite was executed in the workspace terminal:

```bash
python test_system_verification.py
```

### Execution Log & Test Results
```text
============================================================
RUNNING SYSTEM UPGRADE VERIFICATION SUITE
============================================================

[TEST 1] Testing Database Bootstrap & Stock Metadata...
Stock Metadata: Total Items=774, In-Stock=771, Synced=2026-09-26 02:20 PM
>>> PASS: Bootstrap & Stock Metadata active.

[TEST 2] Testing Strict Model Tokenizer...
>>> PASS: Strict Tokenizer properly parses tonnages, platforms, and categories.

[TEST 3] Testing Cross-Series Isolation (PITH vs CITH)...
GS-18PITH11W Primary Evaporator: 11001060868 (Score: 386, Jobs: 178, Price: Rs. 26,000)
GS-18PITH11W Alternatives: ['11001061842LC']
GS-18CITH12G Primary Evaporator: 1002937LC (Price: Rs. 26,000)
>>> PASS: Cross-Series Isolation strictly validated. Zero cross-contamination.

[TEST 4] Testing Zero-Price Immunity on diverse models...
>>> PASS: Verified 464 parts across 7 models. All prices > Rs. 0.

[TEST 5] Testing Global Stock Search...
Search 'Evaporator': 10 items found, all with prices > 0.
Search 'PCB': 10 items found, all with prices > 0.
Search 'Valve': 10 items found, all with prices > 0.
Search 'Sensor': 10 items found, all with prices > 0.
Search 'Motor': 10 items found, all with prices > 0.
>>> PASS: Global search returns accurate results with verified prices.

[TEST 6] Testing GS-18ZITH1W-T3 Evaporator & Parts...
GS-18ZITH1W-T3 Primary Evaporator: 11001062414 (Evaporator Assy GS-18AITH23W-T3 / GS-18AITH21W-T3/ GS-18CM11 / GS-18ZITH  11001062414) Stock=17
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

[TEST 13] Testing Exact Closed Complaint Ground-Truth Rates & Field Descriptions...
GF-36TFIH 5/8" Valve: Cutt Off Valve 5/8  24LITH11M 7133844 -> Rs. 2,200 (Verified from Closed Complaint #282629821)
GF-36TFIH 1/4" Valve: Cut off Valve 1/4 GS-11CITH3F  7130239 -> Rs. 1,600 (Verified from Closed Complaint #282629821)
>>> PASS: Exact closed-complaint ground-truth rates & field descriptions verified with 100% precision.

============================================================
ALL 13 SYSTEM TESTS PASSED SUCCESSFULLY!
============================================================
```

### Test Case Status Summary Table

| Test # | Test Name | Functions Tested | Pass/Fail | Key Assertions / Verifications |
| :--- | :--- | :--- | :--- | :--- |
| **TEST 1** | Bootstrap & Stock Metadata | `bootstrap_master_data`, `get_stock_metadata` | **PASS** | `total_items > 0` (774 loaded, 771 in-stock) |
| **TEST 2** | Strict Model Tokenizer | `tokenize_appliance_model` | **PASS** | Tonnage (`1.5 Ton`), Series (`PITH`, `CITH`), Category (`Refrigerator`, `Washing Machine`) |
| **TEST 3** | Cross-Series Isolation | `fetch_tiered_compatible_parts` | **PASS** | `GS-18PITH11W` primary = `11001060868`; `1002937LC` excluded; `GS-18CITH12G` primary = `1002937LC`; `11001060868` excluded |
| **TEST 4** | Zero-Price Immunity | `fetch_tiered_compatible_parts` | **PASS** | Checked 464 parts across 7 models; all prices > Rs. 0 |
| **TEST 5** | Global Stock Search | `search_stock_global` | **PASS** | Queries (`Evaporator`, `PCB`, `Valve`, `Sensor`, `Motor`) return non-empty, all prices > 0 |
| **TEST 6** | ZITH Evaporator Verification | `fetch_tiered_compatible_parts` | **PASS** | `GS-18ZITH1W-T3` primary = `11001062414` (in stock = 17); alternate = `1000106068502` |
| **TEST 7** | Standard Overheads & Gas | `get_tonnage_specs`, `CATEGORY_OVERHEADS` | **PASS** | Visit = 600, Mobility = 2000, Ref Gas = 4000, Dispenser Gas = 3500 |
| **TEST 8** | Price Parity (Direct vs Model) | `search_stock_global`, `fetch_tiered_compatible_parts` | **PASS** | Part `11001062414` is Rs. 30,000 in both Model Search and Direct Search |
| **TEST 9** | Packaging Carton Exclusion | `fetch_tiered_compatible_parts` | **PASS** | Carton `03010102510004` excluded from Evaporator Assemblies; alternate evaporator `1000106068502` floored at Rs. 26,000 |
| **TEST 10** | Strict Valve Isolation & Pairing | `fetch_tiered_compatible_parts`, `is_valve_tonnage_compatible` | **PASS** | 1.0T (3/8" + 1/4"); 1.5T (1/2" + 1/4"); 2.0T (5/8" + 1/4"); 4.0T (5/8" + 3/8"); 0% cross-leakage |
| **TEST 11** | Floor Standing AC Isolation | `tokenize_appliance_model`, `fetch_tiered_compatible_parts` | **PASS** | `GF-36TFIH` matches genuine Evaporator `11001000602` @ Rs. 58,000 (0% leakage of 24ISH/48FW); valves = 5/8" + 1/4" |
| **TEST 12** | 1.0T 3/8" Valve Customer Rate | `fetch_tiered_compatible_parts`, `search_stock_global` | **PASS** | 3/8" Valve `71302395` = Rs. 1,500 (not ledger Rs. 2,968) in both Model and Direct Search |
| **TEST 13** | Exact Closed Complaint Ground-Truth | `fetch_tiered_compatible_parts`, SQLite `parts_master` | **PASS** | `GF-36TFIH`: 5/8" Valve `7133844` = Rs. 2,200; 1/4" Valve `7130239` = Rs. 1,600; SQLite prices verified |

---

## 4. Multi-Tier Spare Parts Resolution Analysis

### 4.1 Current Implementation State in `database.py`
In `fetch_tiered_compatible_parts(selected_model)`:
1. **Tier 1 (Exact Model Match)**:
   - Queries `baseline['models'][model_name]['parts']`.
   - Checks `is_series_compatible(part_name, series, tonnage, category, role)`.
   - Score formula: `(verified_jobs * 2) + (10 if in_stock else 0) + 20`.
   - Label: `"Tier 1: Exact Model Verified"`.
2. **Tier 2 (Platform Series Match)**:
   - Queries `baseline['series'][series_key]`.
   - Filters out parts already collected in Tier 1.
   - Checks `is_series_compatible(...)` to prevent chassis-sensitive cross-contamination.
   - Score formula: `(verified_jobs * 2) + (10 if in_stock else 0) + 5`.
   - Label: `"Tier 2: {series} Series Platform"`.
3. **Current Direct Stock Model Match (Conflation Issue)**:
   - Lines 228–270 of `database.py` perform a SQL query on `stock_master` matching model prefixes in `item_desc`.
   - Currently, these are labeled `"Tier 1: Stock Inventory ({tok['series']})"`.
   - This conflates warehouse stock fallback with genuine Tier 1 exact model ground-truth.
4. **Current In-Stock Valve Fallback**:
   - Lines 286–375 of `database.py` enforce valve pairing via `warehouse_stock_map`.
   - If suction or liquid valve is missing from candidate parts, standard warehouse active valves are inserted and labeled `"Tier 1: Stock Inventory (Standard Valve)"`.

### 4.2 Gaps and Required Refactoring for Requirement R3
1. **Official Catalog Ingestion into Tier 1**:
   - `pdf_extracted_stock_report.csv` contains explicit model designations for 518 parts (e.g. `GF-36TFIH` -> `11001000602`, `GS-18PITH1W` -> `11001060868`, `GS-12PITH1W` -> `71302395`).
   - Official catalog model mappings must be ingested into `parts_master` and baseline Tier 1 so that catalog-designated parts appear as Tier 1 with 100% field descriptions and official prices.
2. **Distinct Tier 3 Resolution Pipeline**:
   - Separate warehouse stock matches into an explicit **Tier 3 (Store In-Stock Fallback)**.
   - Tier 3 label: `"Tier 3: Store In-Stock Fallback"`.
   - Enforce physical line/capacity constraints across all categories:
     - **Split AC & Floor Standing AC**: Valves must adhere strictly to tonnage pairing (1.0T: 3/8" + 1/4"; 1.5T: 1/2" + 1/4"; 2.0T/3.0T: 5/8" + 1/4"; 4.0T/5.0T: 5/8" + 3/8").
     - **Refrigerators**: In-stock universal/platform items (thermostats, defrost timers, overload protectors, door gaskets) must only fallback within Refrigerator category.
     - **Washing Machines**: In-stock gearboxes, spin motors, drain valves, capacitors must only fallback within Washing Machine category.
     - **Water Dispensers**: In-stock compressors (`QD36LWL`), hot tanks, water taps, thermostats must only fallback within Water Dispenser category.
3. **Clean Tier Representation in User Interface (`app.py`)**:
   - Ensure the UI badge clearly differentiates:
     - 🥇 `Tier 1: Exact Model Verified` / `Tier 1: Official Catalog`
     - 🥈 `Tier 2: Platform Series Compatible`
     - 🥉 `Tier 3: Store In-Stock Fallback`

---

## 5. Valve Physical Line & Capacity Constraints

### 5.1 Authoritative Refrigerant Valve Sizing Rules
Refrigerant service valves must strictly follow physical pipe sizing:

| Appliance Tonnage | Applicable AC Models | Suction Gas Line Valve (Primary #1) | Liquid Line Valve (Alternative #2) | Strictly Rejected Valves (0% Tolerance) |
| :--- | :--- | :--- | :--- | :--- |
| **1.0 Ton** | `GS-10...`, `GS-11...`, `GS-12...`, `ES-12...` | **3/8" Valve** (`71302395`) @ Rs. 1,500 | **1/4" Valve** (`7130239`) @ Rs. 1,600 | 1/2" and 5/8" Valves |
| **1.5 Ton** | `GS-16...`, `GS-18...`, `ES-18...`, `GS-18ZITH...` | **1/2" Valve** (`7133774`) @ Rs. 2,100 | **1/4" Valve** (`7130239`) @ Rs. 1,600 | 3/8" and 5/8" Valves |
| **2.0 Ton** | `GS-24...`, `GS-26...`, `GF-24...`, `ES-24...` | **5/8" Valve** (`7133844`) @ Rs. 2,200 | **1/4" Valve** (`7130239`) @ Rs. 1,600 | 3/8" and 1/2" Valves |
| **3.0 Ton** | `GF-36...` (e.g. `GF-36TFIH`), `GS-36...` | **5/8" Valve** (`7133844`) @ Rs. 2,200 | **1/4" Valve** (`7130239`) @ Rs. 1,600 | 3/8" and 1/2" Valves |
| **4.0 Ton / 5.0 Ton** | `GF-48...`, `GF-60...`, Commercial Floor Units | **5/8" Valve** (`7133844`) @ Rs. 3,200 | **3/8" Valve** (`71302395`) @ Rs. 2,400 | 1/4" and 1/2" Valves |

### 5.2 Canonical Part Number Classification in `config.py`
Closed complaint service history establishes canonical part numbers for valves:
- **1/4" Cut-Off Valves**: `7130239`, `71302392`, `71302393`, `71302391`, `30057000074`, `30057000029`, `030057000029`, `70001060027`.
- **3/8" Cut-Off Valves**: `71302395`, `7133474`.
- **1/2" Cut-Off Valves**: `7133774`, `11225517000085`, `0710307901`.
- **5/8" Cut-Off Valves**: `7133844`, `7135142`.

### 5.3 Group Ordering & Contamination Elimination
In `database.py`:
- All incompatible valve sizes for the selected model's capacity are purged.
- The remaining valves are strictly ordered:
  1. **Primary Item**: Suction Valve (larger diameter).
  2. **Alternative Item**: Liquid Valve (smaller diameter).
- Result: Technicians see a single, clean `"🔩 Cut-off & Service Valves"` group with exactly the two physically matching valves and zero clutter.

---

## 6. Comprehensive Breakdown of Requirements R3 & R4

### 6.1 Requirement R3: Autonomous Multi-Tier Spare Parts Resolution
When any model is input across Split AC, Floor Standing AC, Refrigerator, Washing Machine, or Water Dispenser:

1. **Tier 1 (Exact Model Match)**:
   - **Data Sources**:
     - Closed Complaints (`quality_feedback_report_*.csv`): empirical job frequency `verified_jobs`.
     - Official Master Catalog (`pdf_extracted_stock_report.csv` / `vp786.pdf`): primary model assignment and official price.
   - **Field Descriptions**: Retain 100% field descriptions (e.g. `Cut off Valve 1/4 GS-11CITH3F 7130239`, `Cutt Off Valve 5/8 24LITH11M 7133844`).
   - **Pricing**: Official selling price from vp786.pdf, verified field collection billing mode, or role floor.

2. **Tier 2 (Platform Series Match)**:
   - **Data Sources**: Pre-computed series catalog `baseline['series'][series_key]`.
   - **Platform Series Key**: `Brand|Category|Tonnage|Series`.
   - **Compatibility Guard**: Eliminates chassis-sensitive parts (Evaporators, Inverter PCBs, Indoor Main PCBs, Display Boards) that do not match the target series token or tonnage. Universal parts (`COMMON`, generic fan motors, sensors) pass through.

3. **Tier 3 (Store In-Stock Fallback)**:
   - **Data Sources**: `stock_master` where `bal_qty > 0`.
   - **Strict Physical Constraints**:
     - Air Conditioners: Enforce exact tonnage valve pairing (1.0T, 1.5T, 2.0T/3.0T, 4.0T/5.0T).
     - Non-AC Appliances: Constrain to same appliance category and functional role (e.g., Refrigerator thermostats only to Refrigerators, Water Dispenser taps/compressors only to Water Dispensers).

4. **Ranking & Presentation**:
   - Within each role group:
     $$\text{Rank Score} = (\text{verified\_jobs} \times 2) + (\text{in\_stock\_bonus}) + \text{tier\_weight}$$
   - Primary item = Highest ranked compatible part.
   - Alternatives = Substitutions and revision codes.

### 6.2 Requirement R4: Fully Autonomous Self-Healing & Verification Engine
The automated test harness (`test_system_verification.py`) must be extended into a comprehensive, permanent CI/verification suite validating:

1. **Master Price Authority Verification**:
   - Assert all 518 parts from `vp786.pdf` are present in `stock_master` and indexed with their exact official retail price.
   - Assert key acceptance criteria prices:
     - 3/8" Valve (`71302395`) = Rs. 1,500 across all 1.0T models and direct search.
     - 1/4" Valve (`7130239`) = Rs. 1,600 across all models and direct search.
     - 1/2" Valve (`7133774`) = Rs. 2,100 across all 1.5T models.
     - 5/8" Valve (`7133844`) = Rs. 2,200 across all 2.0T and 3.0T models (including `GF-36TFIH`).
     - Evaporators:
       - `GF-36TFIH` = Rs. 58,000 (genuine Evaporator `11001000602`)
       - `GS-18PITH1W` = Rs. 26,000 (genuine Evaporator `11001060868`)
       - `GS-18AITH23W-T3` = Rs. 30,000 (genuine Evaporator `11001062414`)
       - `GF-48FW` = Rs. 70,000 (genuine Evaporator `1004169`)
       - `GF-24ISH` = Rs. 72,000 (genuine Evaporator `11001060092`)
       - `GF-48TF` = Rs. 75,000 (genuine Evaporator `11001060521`)
       - `GF-24CB` = Rs. 66,000 (genuine Evaporator `100404401`)
2. **Physical Compatibility & Zero Contamination**:
   - `GF-36TFIH` returns ONLY genuine 3.0T Evaporator `11001000602`, 5/8" Suction Valve `7133844` (Rs. 2,200), and 1/4" Liquid Valve `7130239` (Rs. 1,600). Zero leakage of 24ISH (`11001060092`), 48FW (`1004169`), or 48FWITH (`11001060246`).
   - Every AC model displays exactly its physically compatible valve pair with zero clutter of unrelated valve sizes.
3. **Zero-Pricing & Corrupted Ledger Immunity**:
   - Assert 0 parts in the entire system display Rs. 0.
   - Assert zero corrupted accounting ledger ratios (`AMOUNT / BAL_QTY`) leak into user estimates.
4. **Execution Verification**:
   - `python test_system_verification.py` executes all automated test cases and completes with 100% pass rate and 0 errors.

---

## 7. Actionable Recommendations for Implementation Milestones

1. **Milestone 1 (Catalog Ingestion & Schema Update - R1)**:
   - Enhance `etl.py` to ingest `data/pdf_extracted_stock_report.csv` directly into `stock_master` on bootstrap or sync.
   - Replace the `AMOUNT / BAL_QTY` calculation with `pdf_price` as primary authority.
   - Seed `parts_master` with official primary model assignments from `pdf_extracted_stock_report.csv`.
2. **Milestone 2 (Triangular Ground-Truth Engine - R2)**:
   - Update `build_baseline.py` to fuse `pdf_extracted_stock_report.csv` as Master Price Authority before field collection modes, eliminating hardcoded override dictionaries.
3. **Milestone 3 (Multi-Tier Spare Parts Resolution Engine - R3)**:
   - Refactor `database.py:fetch_tiered_compatible_parts`:
     - Clean separation of Tier 1, Tier 2, and Tier 3.
     - Implement structured Tier 3 store in-stock fallback for non-AC appliances (Refrigerators, Washing Machines, Water Dispensers).
     - Standardize tier badge metadata in UI cards (`app.py`).
4. **Milestone 4 (Self-Healing & Verification Suite - R4)**:
   - Expand `test_system_verification.py` to add explicit tests for all 7 named evaporator models and prices from Acceptance Criteria.
   - Add verification for all 518 catalog parts pricing integrity.
   - Run verification suite to guarantee 100% pass with 0 errors.
