# Adversarial Challenge Report — Milestone 2 (Challenger 2)

**Evaluator**: M2 Challenger 2 (Empirical Challenger)  
**Target Milestone**: Milestone 2 (Autonomous Multi-Tier Resolution & Physical Pairing Engine)  
**Date**: 2026-09-29T18:47:00+05:00  
**Overall Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**  

---

## 1. Executive Summary

Milestone 2 was subjected to comprehensive adversarial stress testing focusing on:
1. **GF-36TFIH Multi-Tier Output & Zero Contamination**: Asserting genuine 3.0T Evaporator `11001000602`, 5/8" Suction Valve `7133844` (Rs. 2,200), and 1/4" Liquid Valve `7130239` (Rs. 1,600) with 0% contamination.
2. **Boundary Conditions & Robustness**: Evaluating empty search query strings, whitespace padding, malformed models, SQL injection vectors, and nonexistent part numbers.
3. **Direct Search Fallbacks & Official Price Consistency**: Confirming price fidelity across `stock_master`, `parts_master`, and direct global search.
4. **Execution of Automated Verification Suite**: Executing `python test_system_verification.py` (16 of 16 tests passed).
5. **Execution of Adversarial Regression Suite**: Executing `python test_adversarial_m1_challenger_2.py` (6 of 6 challenges passed across 16 models and 2,133 audited parts).

All empirical stress tests passed with **zero defects, zero price leaks, zero cross-contamination, and zero unhandled exceptions**.

---

## 2. Adversarial Challenges & Stress Testing

### [Low] Challenge 1: GF-36TFIH Multi-Tier Resolution & Cross-Series Contamination Audit
- **Assumption Challenged**: That GF-36TFIH might leak foreign evaporators from other floor-standing or split AC series (such as 2.0T 24ISH `11001060092`, 4.0T 48FW `1004169`, 4.0T 48FWITH `11001060246`, or 1.5T PITH/CITH/AITH) or display invalid valve sizes (3/8", 1/2").
- **Attack Scenario**: Query `fetch_tiered_compatible_parts("GF-36TFIH")` under normalized, lowercase, whitespace-padded, and stripped variations (`gf-36tfih`, `=GF-36TFIH=`, `  GF-36TFIH  `), inspect all candidate parts across `tier1`, `tier2`, `tier3`, and inspect `role_groups`.
- **Observed Behavior**:
  - `metadata.category`: `Floor Standing AC`
  - `metadata.tonnage`: `3.0 Ton`
  - `metadata.series`: `TFIH`
  - Evaporator group contains **ONLY** genuine 3.0T Evaporator `11001000602` priced at Rs. 58,000 (0% leakage of 24ISH, 48FW, 48FWITH, or 48TF).
  - Cut-off & Service Valves group contains **strictly 2 items**:
    - Primary (#1): 5/8" Suction Valve `7133844` at Rs. 2,200 with closed-complaint field description `Cutt Off Valve 5/8  24LITH11M 7133844`.
    - Alternative (#2): 1/4" Liquid Valve `7130239` at Rs. 1,600 with closed-complaint field description `Cut off Valve 1/4 GS-11CITH3F  7130239`.
  - Zero leakage of 3/8" or 1/2" valves.
  - Zero non-functional packaging cartons/boxes in Evaporator or cooling roles.
- **Blast Radius**: None. Contamination rate is strictly 0.0%.
- **Verdict**: **PASS (ROBUST)**

---

### [Low] Challenge 2: Boundary Conditions (Empty Query, Invalid Models, Direct Search Fallbacks)
- **Assumption Challenged**: Hostile strings, empty queries, or invalid model codes could cause unhandled key errors, SQL syntax exceptions, or zero-price fallbacks.
- **Attack Scenario**:
  1. Pass empty strings `""`, whitespace `"   "`, SQL injection patterns (`"'; DROP TABLE stock_master; --"`, `"%OR%1=1%"`), and script tags into `search_stock_global` and `fetch_tiered_compatible_parts`.
  2. Query completely nonexistent models (`"UNKNOWN-MODEL-999"`, `"INVALID-ABC"`, `"---"`).
  3. Query nonexistent part numbers (`"NON_EXISTENT_PNO_XYZ"`).
- **Observed Behavior**:
  - `fetch_tiered_compatible_parts("")` and `fetch_tiered_compatible_parts("UNKNOWN-MODEL-999")` return valid dictionary structures with complete contract keys (`tier1`, `tier2`, `tier3`, `metadata`, `role_groups`, `compatible_parts`).
  - Zero-price immunity maintained 100%: all returned parts across hostile queries maintain `price > 0`.
  - `search_stock_global("")` and `search_stock_global("   ")` gracefully return non-empty default stock listings with verified prices.
  - Parameterized SQLite queries completely neutralize SQL injection vectors without exceptions.
  - Nonexistent searches return clean empty collections without crashing.
- **Blast Radius**: None. System is resilient to hostile inputs.
- **Verdict**: **PASS (ROBUST)**

---

### [Low] Challenge 3: Physical Valve Line Pairing Across AC Tonnages (1.0T to 4.0T)
- **Assumption Challenged**: That generic valve parts could leak across different tonnage capacities in Tier 1, Tier 2, or Tier 3 store fallbacks.
- **Attack Scenario**: Audited 22 AC models across 5 distinct tonnage brackets:
  - 1.0 Ton (`GS-12PITH11W`, `GS-12CITH11W`, `GS-11CITH3F`, `GS-10PITH1`, `ES-12`)
  - 1.5 Ton (`GS-18ZITH1W-T3`, `GS-18PITH11W`, `GS-18CITH12G`, `GS-18AITH23W-T3`, `GS-18VITH1`, `ES-18`)
  - 2.0 Ton (`GS-24PITH11W`, `GS-24CITH1`, `GS-24LITH11M`, `GF-24ISH`, `GF-24CB`)
  - 3.0 Ton (`GF-36TFIH`, `GF-36TF`, `GF-36`)
  - 4.0 Ton (`GF-48TF`, `GF-48FW`, `GF-48FWITH`)
- **Observed Behavior**:
  - 1.0 Ton: strictly pairs 3/8" Suction `71302395` (Rs. 1,500) + 1/4" Liquid `7130239` (Rs. 1,600). Prohibited 1/2" and 5/8" valves: 0% leakage.
  - 1.5 Ton: strictly pairs 1/2" Suction `7133774` (Rs. 2,100) + 1/4" Liquid `7130239` (Rs. 1,600). Prohibited 3/8" and 5/8" valves: 0% leakage.
  - 2.0 Ton & 3.0 Ton: strictly pairs 5/8" Suction `7133844` (Rs. 2,200) + 1/4" Liquid `7130239` (Rs. 1,600). Prohibited 3/8" and 1/2" valves: 0% leakage.
  - 4.0 Ton: strictly pairs 5/8" Suction `7133844` (Rs. 2,200) + 3/8" Liquid `71302395` (Rs. 1,500). Prohibited 1/4" and 1/2" valves: 0% leakage.
- **Blast Radius**: None. Valve pairing adheres 100% to physical refrigeration engineering specifications.
- **Verdict**: **PASS (ROBUST)**

---

### [Low] Challenge 4: Non-AC Category Isolation (Refrigerators, Washing Machines, Water Dispensers)
- **Assumption Challenged**: That AC components (cut-off valves, AC evaporators) could leak into Refrigerator, Washing Machine, or Water Dispenser estimates via Tier 3 store stock fallbacks.
- **Attack Scenario**: Audited `GR-E8768G-CP1` (Refrigerator), `EW-F1202DC` (Washing Machine), and `WD-E500` (Water Dispenser).
- **Observed Behavior**:
  - Refrigerator `GR-E8768G-CP1`: 0% AC valve leakage, 0 cut-off valve groups returned.
  - Washing Machine `EW-F1202DC`: 0% AC valve leakage, 0% AC evaporator leakage, 0 cut-off valve groups returned.
  - Water Dispenser `WD-E500`: 0% AC valve leakage, 0 cut-off valve groups returned.
- **Blast Radius**: None. Category chassis isolation is strictly enforced.
- **Verdict**: **PASS (ROBUST)**

---

### [Low] Challenge 5: Database Ledger Hygiene Audit
- **Assumption Challenged**: Residual accounting valuation discrepancies (`amount != round(unit_price * bal_qty, 2)`) could persist in `dwp_service.db`.
- **Attack Scenario**: Executed exact SQL query:
  ```sql
  SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND abs(amount - (unit_price * bal_qty)) > 0.01;
  ```
- **Observed Behavior**:
  - Exact count returned: `0` discrepancies across all 972 inventory records in `stock_master`.
  - Zero-price items in `stock_master`: `0`.
  - Zero-price items in `parts_master`: `0`.
- **Blast Radius**: None. Accounting ledger leakage has been permanently eliminated.
- **Verdict**: **PASS (ROBUST)**

---

## 3. Stress Test Results Summary

| Test Scenario | Expected Behavior | Actual Behavior | Pass / Fail |
|---|---|---|---|
| GF-36TFIH Evaporator Isolation | Return ONLY genuine 3.0T Evaporator `11001000602` @ Rs. 58,000 | Returned `11001000602` @ Rs. 58,000; 0% 24ISH/48FW leakage | **PASS** |
| GF-36TFIH Valve Pairing | Primary 5/8" `7133844` @ Rs. 2,200; Alt 1/4" `7130239` @ Rs. 1,600 | Exactly 5/8" and 1/4" returned with closed-complaint descriptions | **PASS** |
| Empty Search Query (`""` / `"   "`) | Graceful full candidate listing, no crash | Complete unconstrained candidate listing returned | **PASS** |
| SQL Injection Queries in Global Search | Sanitized parameterized execution, no crash | Valid DataFrames returned with verified prices | **PASS** |
| Unknown / Invalid Model Codes | Fallback to safe defaults, no zero-price parts | Structured response with all contract keys, all prices > 0 | **PASS** |
| Direct Search Fallbacks for Key Parts | Match official catalog prices (Rs. 1,500, 1,600, 2,100, 2,200, 58,000) | 100% price consistency between Direct Search and Model Search | **PASS** |
| 1.0 Ton Valve Pairing | Strictly 3/8" + 1/4", zero 1/2" or 5/8" | 100% compliant across GS-12PITH, GS-12CITH, GS-11CITH, ES-12 | **PASS** |
| 1.5 Ton Valve Pairing | Strictly 1/2" + 1/4", zero 3/8" or 5/8" | 100% compliant across GS-18ZITH, GS-18PITH, GS-18CITH, ES-18 | **PASS** |
| 2.0T & 3.0T Valve Pairing | Strictly 5/8" + 1/4", zero 3/8" or 1/2" | 100% compliant across GS-24PITH, GF-24ISH, GF-36TFIH, GF-36TF | **PASS** |
| 4.0 Ton Valve Pairing | Strictly 5/8" + 3/8", zero 1/4" or 1/2" | 100% compliant across GF-48TF, GF-48FW, GF-48FWITH | **PASS** |
| Non-AC Chassis Isolation | Zero AC refrigerant valves in Ref, WM, WD | 0% leakage of AC valves or evaporators | **PASS** |
| Packaging Carton Exclusion | Exclude packaging cartons from cooling roles | Cartons strictly classified under Component Hardware | **PASS** |
| Database Ledger Discrepancy Audit | 0 rows with `amount != unit_price * bal_qty` | Exactly 0 discrepancies found across 972 rows | **PASS** |
| Full System Verification Suite | All 16 automated tests pass with 0 errors | 16 of 16 tests passed | **PASS** |
| Empirical Adversarial Suite | All 6 adversarial challenges pass | 6 of 6 challenges passed (0 failures) | **PASS** |

---

## 4. Unchallenged Areas

- **Antigravity Skill Paths**: None provided by the orchestrator.
- **Live Streamlit Browser Rendering**: Evaluated at unit/module level through headless verification of `database.py` and `app.py` UI logic.

---

## 5. Final Binary Verdict

**VERDICT: APPROVE**

The multi-tier spare parts resolution engine and database hygiene implemented in Milestone 2 fully satisfy all requirements:
1. GF-36TFIH isolation is 100% verified with 0% contamination.
2. Boundary conditions and edge cases survive without exceptions or price leaks.
3. All 16 tests in `test_system_verification.py` pass cleanly.
4. Database ledger discrepancies are confirmed at 0.
