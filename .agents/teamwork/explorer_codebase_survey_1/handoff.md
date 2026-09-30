# Hard Handoff Report — Codebase Architecture & Test Harness Survey

**Agent**: `explorer_codebase_survey_1`  
**Role**: Codebase Test Explorer  
**Task**: Survey codebase architecture, database access layer, pricing and estimator engines, multi-tier resolution logic, valve line constraints, test harness execution, and requirements R3/R4.  
**Deliverable Document**: `c:\Users\PC\Desktop\estimator\.agents\teamwork\explorer_codebase_survey_1\codebase_architecture_report.md`

---

## 1. Observation

1. **Codebase Architecture & Technologies**:
   - `app.py`: Streamlit frontend application with 3 primary tabs (`tab_estimator`, `tab_history`, `tab_perf`) and administrative sidebar for syncing live stock, technician KPIs, and feedback archives. No FastAPI, Flask, or Django frameworks are used.
   - `dwp_service.db`: Local SQLite database operated in WAL mode (`PRAGMA journal_mode=WAL;`). Contains tables `stock_master`, `parts_master`, `history_master`, and `tech_performance_master`.
   - `data/ground_truth_baseline.json`: 2.69 MB pre-computed JSON baseline storing ground-truth models, series platform indices, global stock, price book, and role floor defaults.
   - `config.py`: 538 lines defining business rules, overhead rates (`CATEGORY_OVERHEADS`), 29 platform series tokens, regex tokenizer `tokenize_appliance_model`, component classifier `classify_component_role`, role price floors `get_role_price_floor`, and valve compatibility functions `is_valve_tonnage_compatible` and `get_tonnage_valve_pairing`.
   - `database.py`: 521 lines containing `fetch_tiered_compatible_parts`, `search_stock_global`, `get_stock_metadata`, `search_history_records`, and `fetch_performance_data`.
   - `etl.py`: Ingestion logic for stock, quality feedback, customer collections, and technician performance.
   - `build_baseline.py`: Ground-truth matrix generator that processes ERP reports into `data/ground_truth_baseline.json`.

2. **Automated Test Suite Execution**:
   - Command executed: `python test_system_verification.py`.
   - Output verbatim:
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
     >>> PASS: Cross-Series Isolation strictly validated. Zero cross-contamination.
     [TEST 4] Testing Zero-Price Immunity on diverse models...
     >>> PASS: Verified 464 parts across 7 models. All prices > Rs. 0.
     [TEST 5] Testing Global Stock Search...
     >>> PASS: Global search returns accurate results with verified prices.
     [TEST 6] Testing GS-18ZITH1W-T3 Evaporator & Parts...
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
     >>> PASS: GF-36TFIH 100% verified with genuine Evaporator 11001000602 at Rs. 58,000 (0% leakage of 24ISH & 48FW).
     [TEST 12] Testing 1.0 Ton 3/8" Valve Customer Verified Pricing (Rs. 1,500)...
     >>> PASS: 1.0 Ton 3/8" valve accurately verified at customer billing rate Rs. 1,500 with 100% system consistency.
     [TEST 13] Testing Exact Closed Complaint Ground-Truth Rates & Field Descriptions...
     >>> PASS: Exact closed-complaint ground-truth rates & field descriptions verified with 100% precision.
     ============================================================
     ALL 13 SYSTEM TESTS PASSED SUCCESSFULLY!
     ============================================================
     ```
   - Exit code: 0 (13 passed, 0 failed, 0 errors).

3. **Multi-Tier Resolution & Valve Sizing Observations**:
   - `database.py` implements Tier 1 (exact model from baseline), Tier 2 (platform series key `Brand|Category|Tonnage|Series`), and direct stock text matches.
   - Direct stock text matches are currently assigned `"Tier 1: Stock Inventory ({tok['series']})"`, conflating Tier 1 and Tier 3.
   - Valve physical pairing is implemented in `database.py` (lines 286-375) using `warehouse_stock_map` fallback for suction and liquid valves, strictly filtering out incompatible sizes and ordering suction as Primary (#1) and liquid as Alternative (#2).
   - In `etl.py` and `build_baseline.py`, `stock_master.unit_price` is still computed via `amount / bal_qty` with hardcoded dictionary overrides (`known_price_overrides`), rather than ingesting official catalog prices from `pdf_extracted_stock_report.csv` (which has 518 unique parts and official retail prices).

---

## 2. Logic Chain

1. **From Observation 1 to System Boundaries**:
   - The application does not use microservices or REST API wrappers; Streamlit directly imports `database.py`, `etl.py`, and `config.py`.
   - Any architectural enhancements (such as multi-tier resolution or catalog ingestion) must directly interface through `database.py`, `etl.py`, and `build_baseline.py`.

2. **From Observation 2 to Baseline Quality**:
   - The existing 13 test cases establish that the foundational business rules (tokenizer, series isolation, role floors, valve pairing, overhead rates) are currently intact and passing.
   - However, the current test suite does not yet assert the full set of 518 parts from `vp786.pdf`, nor does it verify all 7 evaporator models explicitly named in Acceptance Criteria (e.g. `GF-48FW` = Rs. 70,000, `GF-24ISH` = Rs. 72,000, `GF-48TF` = Rs. 75,000, `GF-24CB` = Rs. 66,000).

3. **From Observation 3 to R3 Implementation Gaps**:
   - Tier 1 must be extended to include catalog-designated primary models from `pdf_extracted_stock_report.csv` alongside closed-complaint history.
   - Tier 3 is currently only implemented for AC valves via `warehouse_stock_map`. A systematic Tier 3 store in-stock fallback must be added for other functional roles (fan motors, capacitors, PCBs) and across non-AC categories (Refrigerators, Washing Machines, Water Dispensers) with strict category/capacity guards.

4. **From Observation 3 to R1 & Master Price Catalog Replacement**:
   - Ingesting `pdf_extracted_stock_report.csv` directly into `stock_master` and `parts_master` will eliminate the flawed `AMOUNT / BAL_QTY` ledger ratio permanently and remove the need for hardcoded `known_price_overrides`.

---

## 3. Caveats

1. **Ad-hoc shell command restriction**: Shell commands requiring interactive user elevation (e.g. `python -c "..."`) time out waiting for user confirmation; however, standalone script commands (e.g. `python test_system_verification.py`) run cleanly and deterministically.
2. **Read-Only Scope**: In accordance with the Explorer archetype, no source files outside `.agents/teamwork/explorer_codebase_survey_1` were modified. Implementation proposals are strictly documented for Phase 1 & 2 implementers.
3. No other caveats.

---

## 4. Conclusion

1. **Codebase Health**: The codebase architecture is solid, modular, and currently passes all 13 existing verification tests with 0 errors.
2. **Requirement R1 Priority**: Replace the flawed accounting valuation `AMOUNT / BAL_QTY` in `etl.py` and `build_baseline.py` with `pdf_price` from `pdf_extracted_stock_report.csv` (518 unique parts).
3. **Requirement R3 Priority**: Refactor `database.py:fetch_tiered_compatible_parts` to cleanly separate Tier 1 (Exact Model Ground-Truth + Official Catalog), Tier 2 (Platform Series Match), and Tier 3 (Store In-Stock Fallback with strict capacity and category guards).
4. **Requirement R4 Priority**: Expand `test_system_verification.py` to assert official pricing across all 518 catalog parts, all 7 acceptance-criteria evaporators, and multi-tier resolution across Split AC, Floor Standing AC, Refrigerator, Washing Machine, and Water Dispenser categories.

---

## 5. Verification Method

To independently verify all findings:
1. Run the test harness:
   ```bash
   python test_system_verification.py
   ```
   Verify 13 tests execute and pass with exit code 0.
2. Inspect the survey report at:
   `c:\Users\PC\Desktop\estimator\.agents\teamwork\explorer_codebase_survey_1\codebase_architecture_report.md`
3. Inspect `config.py` (lines 457-536) for valve compatibility logic.
4. Inspect `database.py` (lines 111-401) for current tiered matching logic.
5. Inspect `data/pdf_extracted_stock_report.csv` for the 518 unique parts and official retail prices.
