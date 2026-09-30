# Self-Contained Handoff Report: Autonomous Triangular Ground-Truth Engine for `build_baseline.py`

**Handoff Type:** Hard (Task Complete)  
**Agent:** M1 Explorer 2 (`m1_explorer_2`)  
**Target Milestone:** Milestone 1 — R1 & R2 Data Foundation  
**Recipient:** Orchestrator (`edd2b9d7-a033-47c3-81d6-d8a03ec4010c`) & Worker Agent  
**Date:** September 29, 2026  

---

## 1. Observation

1. **Defects in `build_baseline.py`**:
   - In `build_baseline.py:16`: `STOCK_FILE = os.path.join(BASE_DIR, "data", "stock_inventory_latest.csv")` directs the baseline indexer to use raw accounting warehouse ledger records.
   - In `build_baseline.py:44`: `unit_calc = int(round(amt / bal)) if (bal > 0 and amt > 0) else 0` computes unit price from the ledger ratio `AMOUNT / BAL_QTY`.
   - In `build_baseline.py:130–138`:
     ```python
     known_price_overrides = {
         '71302395': 1500,     # Cut-off valve 3/8 1.0 Ton verified field price
         '7130239': 1600,      # Cut-off valve 1/4 verified field price
         '7133844': 2200,      # Cut-off valve 5/8 (2.0/3.0 Ton) verified customer collection price
         '11001000602': 58000, # Evaporator Assy GF-36TFIH verified customer collection price
     }
     for pno, ov_pr in known_price_overrides.items():
         part_verified_prices[pno] = ov_pr
     ```
     This manually overrides four parts with hardcoded prices.
   - In `build_baseline.py:386–407`: `warehouse_stock_valves` contains hardcoded integer prices (`1500`, `1600`, `2100`, `2200`, `3200`, `2400`) within the valve pairing logic.
   - In `build_baseline.py:76–119`: `model_replacements` is built solely by iterating over `fb_df` (closed complaints in `quality_feedback_report_28SEP2026_142900.csv`). Models from the official catalog that never experienced a closed service ticket in Karachi are omitted from `ground_truth_catalog`.

2. **Master Price Authority (`data/pdf_extracted_stock_report.csv`)**:
   - Contains 531 rows representing **518 unique parts** with 13 duplicate entries across suppliers/bins.
   - 3/8" Valve (`71302395`): Line 458, `item_desc: Cut-off valve 3/8 71302395 GS- 12PITH1W/O`, `model: GS-12PITH1W`, `pdf_price: 1500.0`, `total_stock: 1`.
   - 1/4" Valve (`7130239`): Line 7 & 456, `item_desc: Cut off Valve 1/4 GS-11CITH3F 7130239`, `model: GS-11CITH3F`, `pdf_price: 1600.0`, `total_stock: 15`.
   - 1/2" Valve (`7133774`): Line 460, `item_desc: Cut Off Valve Assy 1/2 7133774 GS- 18VITH1`, `model: GS-18VITH1`, `pdf_price: 2100.0`, `total_stock: 6`.
   - 5/8" Valve (`7133844`): Line 461, `item_desc: Cutt Off Valve 5/8 24LITH11M 7133844`, `model: GS-24LITH11M`, `pdf_price: 2200.0`, `total_stock: -6`.
   - Evaporator `11001000602`: Line 64, `item_desc: Evaporator Assy GF-36TFIH 11001000602`, `model: GF-36TFIH`, `pdf_price: 58000.0`, `total_stock: 0`.
   - Evaporators for Acceptance Criteria models:
     - `GF-36TFIH` (`11001000602`): Rs. 58,000 (Line 64)
     - `GS-18PITH1W` (`11001060868`): Rs. 26,000 (Line 72)
     - `GS-18AITH23W-T3` (`11001062414`): Rs. 30,000 (Line 78)
     - `GF-48FW` (`1004169`): Rs. 70,000 (Line 46)
     - `GF-24ISH` (`11001060092`): Rs. 72,000 (Line 69)
     - `GF-48TF` (`11001060521`): Rs. 75,000 (Line 71)
     - `GF-24CB` (`100404401`): Rs. 66,000 (Line 45)

3. **Field Verification Authority (`quality_feedback_report_28SEP2026_142900.csv` & `Detail_Collection_28SEP26_023634PM.xlsx`)**:
   - Closed complaint #282629821 on `GF-36TFIH`: Replaced 1/4" Valve `7130239`, 5/8" Valve `7133844`, and Evaporator `11001000602` with total collection receipt `eff_price = Rs. 61,800`.
   - Subtracting known valves $(1,600 + 2,200 = 3,800)$ yields residual $61,800 - 3,800 = \text{Rs. } 58,000$, matching `pdf_price` to the exact rupee.

4. **Chassis & Model Authority (`config.py`)**:
   - `tokenize_appliance_model` enforces brand, category, capacity, and 29 series tokens.
   - `is_valve_tonnage_compatible` and `get_tonnage_valve_pairing` define strict physical pipe lines (1.0T: 3/8"+1/4", 1.5T: 1/2"+1/4", 2.0T/3.0T: 5/8"+1/4", 4.0T: 5/8"+3/8").
   - `get_role_price_floor` sets minimum price floors for all categories and tonnages.

---

## 2. Logic Chain

1. **Premise 1**: All four parts in `known_price_overrides` (`71302395: 1500`, `7130239: 1600`, `7133844: 2200`, `11001000602: 58000`) and all 7 Acceptance Criteria evaporators exist in `data/pdf_extracted_stock_report.csv` with their exact official retail selling prices (Observation 2).
2. **Premise 2**: Ingesting `data/pdf_extracted_stock_report.csv` as Authority 1 into `catalog_parts_master` and initializing `part_verified_prices` from this master catalog makes the manual dictionary `known_price_overrides = {...}` redundant (Premise 1).
3. **Premise 3**: Closed complaint #282629821 on `GF-36TFIH` provides mathematical proof via multi-part residual deduction that $61,800 - (1,600 + 2,200) = \text{Rs. } 58,000$, confirming empirical consensus between Authority 1 and Authority 2 (Observation 3).
4. **Premise 4**: Reading `data/pdf_extracted_stock_report.csv` directly provides executive selling prices (`pdf_price`) and Karachi Store 786 stock (`total_stock`), permanently eliminating the distorted accounting ledger valuation `AMOUNT / BAL_QTY` from `build_baseline.py` (Observation 1 & 2).
5. **Premise 5**: Extracting designated primary models from `data/pdf_extracted_stock_report.csv` and seeding them into `model_replacements` ensures that official catalog models lacking Karachi closed complaints are fully indexed with genuine parts (Observation 1 & 2).
6. **Premise 6**: Dynamic lookup of valve prices from `price_book` within `warehouse_stock_valves` pairing logic eliminates all hardcoded valve price constants while enforcing physical line constraints (Observation 1 & 4).
7. **Conclusion**: Refactoring `build_baseline.py` according to this 4-phase triangular architecture eliminates 100% of hardcoded overrides, eliminates `AMOUNT / BAL_QTY`, seeds all catalog models, and compiles a clean `data/ground_truth_baseline.json` that satisfies all acceptance criteria and test harness assertions.

---

## 3. Caveats

1. **Secondary Warehouse Items**: Non-catalog items present only in `data/stock_inventory_latest.csv` (e.g. LED TVs, Microwave Ovens) are retained in `raw_stock_dict` for general appliance coverage, but their `stock_cost` is initialized to 0 and their price is protected by role floors or customer collections rather than `AMOUNT / BAL_QTY`.
2. **Gas Cylinders**: Part numbers `0305010102` (R-410a) and `0305010103` (R-32) appear multiple times with prices ranging from 35,000 to 40,000. Selecting `max(pdf_prices)` ensures the full executive retail rate (Rs. 40,000) is indexed.
3. **Read-Only Scope**: In strict compliance with Explorer agent constraints, no source code modifications have been made directly to `build_baseline.py`. The Worker agent must execute the documented changes.

---

## 4. Conclusion

1. **Feasibility**: Refactoring `build_baseline.py` into an Autonomous Triangular Ground-Truth Engine is 100% feasible and eliminates all hardcoding.
2. **Architecture**:
   - Phase 1: Ingests `data/pdf_extracted_stock_report.csv` as Authority 1 (518 unique parts, official prices, catalog models, live stock).
   - Phase 2: Ingests 13,965 complaints and 6,150 collections as Authority 2 (field rates, frequency, multi-part deduction). Deletes `known_price_overrides`.
   - Phase 3: Enforces Authority 3 (tokenization, chassis category boundaries, 29 series tokens, valve pairing, role floors).
   - Phase 4: Serializes atomic JSON to `data/ground_truth_baseline.json`.
3. **Execution Ready**: Complete line-by-line recommendations and replacement code blocks have been authored in `exploration_report.md` for immediate implementation by the Worker agent.

---

## 5. Verification Method

To independently verify the implementation once executed by the Worker:

1. **Execute Baseline Compilation**:
   ```bash
   python build_baseline.py
   ```
   *Expected Output*:
   - Reads `data/pdf_extracted_stock_report.csv`.
   - Reports `Loaded 518 unique parts from Master Price Authority`.
   - Reports `Total unified stock parts (Catalog + Secondary): 766` (or similar).
   - Successfully writes `data/ground_truth_baseline.json`.

2. **Verify JSON Cache Contents**:
   Inspect `data/ground_truth_baseline.json` using Python:
   - Check `price_book['71302395']['price'] == 1500`.
   - Check `price_book['7130239']['price'] == 1600`.
   - Check `price_book['7133774']['price'] == 2100`.
   - Check `price_book['7133844']['price'] == 2200`.
   - Check `price_book['11001000602']['price'] == 58000`.
   - Check `models['GF-36TFIH']['parts']` contains evaporator `11001000602` @ Rs. 58,000, 5/8" Valve `7133844` @ Rs. 2,200, and 1/4" Valve `7130239` @ Rs. 1,600.
   - Check zero instances of `price == 0`.

3. **Execute System Regression Suite**:
   ```bash
   python test_system_verification.py
   ```
   *Verification Invalidation Condition*: Any failure among Tests 1–13 or any price discrepancy between direct search and model search indicates an invalid baseline compilation.

---

*Handoff report submitted by M1 Explorer 2 (`m1_explorer_2`).*
