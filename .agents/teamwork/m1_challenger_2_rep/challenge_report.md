# Adversarial Challenge Report — Milestone 1
**Author**: M1 Challenger 2  
**Role**: Empirical Challenger (Critic & Specialist)  
**Timestamp**: 2026-09-29T13:07:00Z  
**Target Codebase**: `database.py:fetch_tiered_compatible_parts`, `config.py`, `test_system_verification.py`  
**Binary Verdict**: **APPROVE**

---

## Challenge Summary

- **Overall Risk Assessment**: **LOW**
- **Test Harness**: `test_adversarial_m1_challenger_2.py` (6 Challenge Suites, 709 audited parts across 16 models)
- **Official Verification**: `test_system_verification.py` (13/13 Passed with 0 errors)
- **Core Verification Highlights**:
  1. `GF-36TFIH` strictly isolates to genuine 3.0T Evaporator `11001000602` (Rs. 58,000), 5/8" Suction Valve `7133844` (Rs. 2,200), and 1/4" Liquid Valve `7130239` (Rs. 1,600). Zero leakage of `24ISH` (`11001060092`), `48FW` (`1004169`), or `48FWITH` (`11001060246`).
  2. Physical valve pairings across 1.0T, 1.5T, 2.0T/3.0T, and 4.0T strictly adhere to manufacturer thermodynamic line standards with 0% contamination of incompatible valve sizes.
  3. Evaporator complete assembly prioritization (e.g. `GS-18ZITH1W-T3` returning `11001062414` over sub-assembly `1000106068502`) is empirically verified.
  4. 0% zero-price leakage across 709 evaluated parts in diverse appliance categories.

---

## Adversarial Challenges & Findings

### [Low] Challenge 1: GF-36TFIH Floor Standing Chassis Isolation & Cross-Series Leakage
- **Assumption Challenged**: Floor Standing model `GF-36TFIH` could inherit evaporators or valve sizes from sibling 2.0T (`GF-24ISH`), 4.0T (`GF-48FW`, `GF-48TF`), or split AC units through fuzzy model tokenization or stock fallback.
- **Attack Scenario**: Evaluated `fetch_tiered_compatible_parts` with casing variations (`GF-36TFIH`, `gf-36tfih`, `  GF-36TFIH  `, `=GF-36TFIH=`). Scanned all returned primary and alternative evaporators for foreign part numbers: `11001060092` (24ISH), `1004169` (48FW), `11001060246` (48FWITH), `11001060521` (48TF), `100404401` (24CB).
- **Empirical Observation**: 
  - Tokenizer parsed `GF-36TFIH` as: Category = `Floor Standing AC`, Tonnage = `3.0 Ton`, Series = `TFIH`.
  - Primary Evaporator returned: `11001000602` (Rs. 58,000).
  - Alternative Evaporators returned: none.
  - Foreign evaporators detected: **0 (0.0% leakage)**.
  - Primary Valve: `7133844` (Cut-Off Valve (5/8"), Rs. 2,200).
  - Alt Valve: `7130239` (Cut-Off Valve (1/4"), Rs. 1,600).
  - Foreign valve sizes (3/8", 1/2") detected: **0 (0.0% leakage)**.
- **Status**: **PASS (Robust Isolation)**.

---

### [Low] Challenge 2: Thermodynamic Valve Physical Pairing Across AC Tonnages
- **Assumption Challenged**: Service and cut-off valves could mix sizes or invert Suction vs Liquid roles, especially when resolving models from different platform series or generic capacity strings.
- **Attack Scenario**: Stress-tested 20 AC models across 5 tonnage brackets (1.0T, 1.5T, 2.0T, 3.0T, 4.0T):
  - 1.0T (`GS-12PITH11W`, `GS-12CITH11W`, `GS-11CITH3F`, `GS-10PITH1`, `ES-12`)
  - 1.5T (`GS-18ZITH1W-T3`, `GS-18PITH11W`, `GS-18CITH12G`, `GS-18AITH23W-T3`, `GS-18VITH1`, `ES-18`)
  - 2.0T (`GS-24PITH11W`, `GS-24CITH1`, `GS-24LITH11M`, `GF-24ISH`, `GF-24CB`)
  - 3.0T (`GF-36TFIH`, `GF-36TF`, `GF-36`)
  - 4.0T (`GF-48TF`, `GF-48FW`, `GF-48FWITH`)
- **Empirical Observation**:
  - **1.0 Ton**: Primary = 3/8" `71302395` (Rs. 1,500), Alt = 1/4" `7130239` (Rs. 1,600). Forbidden (1/2", 5/8") = 0%.
  - **1.5 Ton**: Primary = 1/2" `7133774` (Rs. 2,100), Alt = 1/4" `7130239` (Rs. 1,600). Forbidden (3/8", 5/8") = 0%.
  - **2.0 Ton**: Primary = 5/8" `7133844` (Rs. 2,200), Alt = 1/4" `7130239` (Rs. 1,600). Forbidden (3/8", 1/2") = 0%.
  - **3.0 Ton**: Primary = 5/8" `7133844` (Rs. 2,200), Alt = 1/4" `7130239` (Rs. 1,600). Forbidden (3/8", 1/2") = 0%.
  - **4.0 Ton**: Primary = 5/8" `7133844` (Rs. 2,200), Alt = 3/8" `71302395` (Rs. 1,500). Forbidden (1/4", 1/2") = 0%.
  - All Suction valves are strictly assigned Rank #1 (Primary) and Liquid valves Rank #2 (Alternative).
- **Status**: **PASS (100% Strict Pairing)**.

---

### [Low] Challenge 3: Cross-Series Contamination & Assembly Ranking
- **Assumption Challenged**: Components from sister series (PITH vs CITH) or sub-assemblies might displace full assemblies or leak into alternate chassis.
- **Attack Scenario**:
  - Queried `GS-18PITH11W` and asserted CITH evaporator `1002937LC` is absent.
  - Queried `GS-18CITH12G` and asserted PITH evaporator `11001060868` is absent.
  - Queried `GS-18ZITH1W-T3` and verified full assembly `11001062414` (stock=17, Rs. 30,000) ranks as primary over sub-assembly `1000106068502` (stock=1, floor Rs. 26,000).
- **Empirical Observation**:
  - `GS-18PITH11W` returned `11001060868` (primary) + `11001061842LC` (alt). Zero CITH leakage.
  - `GS-18CITH12G` returned `1002937LC` (primary). Zero PITH leakage.
  - `GS-18ZITH1W-T3` ranked `11001062414` primary with score tie-breaking favoring full assembly over `SUB ASSY`.
- **Status**: **PASS (Verified Hierarchy)**.

---

### [Low] Challenge 4: Non-AC Appliance Chassis Isolation (Ref, WM, WD)
- **Assumption Challenged**: Non-cooling appliances (Washing Machines, Refrigerators, Water Dispensers) could inherit AC refrigeration components (service cut-off valves, AC evaporators).
- **Attack Scenario**: Queried `GR-E8768G-CP1` (Ref), `EW-F1202DC` (WM), and `WD-E500` (WD), inspecting all returned parts.
- **Empirical Observation**:
  - Refrigerator returned genuine Ref parts (e.g. `GR-E8768G` PCB, sensors); 0 AC refrigerant valves.
  - Water Dispenser returned genuine dispenser components; 0 AC refrigerant valves.
  - Washing Machine returned genuine parts: Soft Press PCB `3A.HK680-P`, Spin Motor `03020203100003`, Water Inlet Valve `3D.PEL003`, Water Level Sensor `3D.HM007`, Capacitor `3D.HF132`.
  - Zero AC refrigerant valves (`7130239`, `71302395`, `7133774`, `7133844`) or AC evaporators leaked into any non-AC appliance.
  - *Architectural Note for M2*: `3D.PEL003` is a genuine washing machine water inlet valve that is classified under role `"Service Valve"` because `classify_component_role` maps unclassified `'valve'` substrings to `"Service Valve"`. While it is a genuine washing machine component, Milestone 2 should refine `COMPONENT_ROLE_GROUPS` or valve classification to assign `"Water Inlet Valve"` rather than `"Service Valve"` for Washing Machines.
- **Status**: **PASS (0% Cross-Category AC Component Leakage)**.

---

### [Low] Challenge 5: Zero-Pricing Immunity & Non-Functional Hardware Protection
- **Assumption Challenged**: Missing prices or placeholder items could produce Rs. 0 estimates, or packaging cartons (e.g. `03010102510004`) could leak into cooling role groups.
- **Attack Scenario**: Audited 709 parts across 16 appliance models in `test_adversarial_m1_challenger_2.py` and 493 parts across 7 models in `test_system_verification.py`.
- **Empirical Observation**:
  - Exactly 0 parts had price <= 0.
  - Packaging carton `03010102510004` is classified as `Component Hardware` and strictly excluded from `Evaporator Assemblies`.
  - In direct global search, all results have verified non-zero prices backed by `stock_master`, `price_book`, or role floor protection.
- **Status**: **PASS (Zero-Price Immune)**.

---

## Stress Test Results Matrix

| # | Test Scenario | Target Model / Query | Expected Output | Actual Output | Status |
|---|---|---|---|---|---|
| 1 | GF-36TFIH Isolation | `GF-36TFIH` | Evaporator `11001000602` (Rs. 58k) | `11001000602` (Rs. 58,000) | **PASS** |
| 2 | GF-36TFIH Valve Pairing | `GF-36TFIH` | 5/8" `7133844` + 1/4" `7130239` | 5/8" (Rs. 2,200) + 1/4" (Rs. 1,600) | **PASS** |
| 3 | GF-36TFIH Contamination | `GF-36TFIH` | 0% 24ISH / 48FW evaporators | 0 foreign evaporators found | **PASS** |
| 4 | 1.0 Ton Valve Pairing | `GS-12PITH11W` | 3/8" `71302395` + 1/4" `7130239` | 3/8" (Rs. 1,500) + 1/4" (Rs. 1,600) | **PASS** |
| 5 | 1.5 Ton Valve Pairing | `GS-18ZITH1W-T3` | 1/2" `7133774` + 1/4" `7130239` | 1/2" (Rs. 2,100) + 1/4" (Rs. 1,600) | **PASS** |
| 6 | 2.0 Ton Valve Pairing | `GS-24PITH11W` | 5/8" `7133844` + 1/4" `7130239` | 5/8" (Rs. 2,200) + 1/4" (Rs. 1,600) | **PASS** |
| 7 | 3.0 Ton Valve Pairing | `GF-36TF` | 5/8" `7133844` + 1/4" `7130239` | 5/8" (Rs. 2,200) + 1/4" (Rs. 1,600) | **PASS** |
| 8 | 4.0 Ton Valve Pairing | `GF-48TF`, `GF-48FW` | 5/8" `7133844` + 3/8" `71302395` | 5/8" (Rs. 2,200) + 3/8" (Rs. 1,500) | **PASS** |
| 9 | Cross-Series Isolation | `GS-18PITH11W` vs `GS-18CITH12G` | Zero evaporator interchange | 0 cross-contamination | **PASS** |
| 10 | Evaporator Assembly Priority | `GS-18ZITH1W-T3` | Assy `11001062414` ranks #1 | `11001062414` #1 (Stock 17) | **PASS** |
| 11 | Non-AC Appliance Isolation | `GR-E8768G-CP1`, `EW-F1202DC` | 0 AC refrigerant valves | 0 AC valves leaked | **PASS** |
| 12 | Zero-Price Immunity | 16 Diverse Appliance Models | 0 parts with price <= Rs. 0 | 709 parts audited, 0 with price <= 0 | **PASS** |
| 13 | Hostile Input Injection | SQL chars, whitespace, empty str | No crash, valid DataFrames | Graceful fallback, 0 crashes | **PASS** |
| 14 | System Verification Suite | `test_system_verification.py` | 13/13 tests pass | 13/13 tests pass (Exit code 0) | **PASS** |

---

## Unchallenged Areas
- **Streamlit UI rendering performance under high concurrent user load**: Streamlit session state and frontend widget interactions were not load-tested under multi-worker HTTP traffic (out of scope for M1 data layer).
- **Physical stock replenishment ETL sync jobs**: Automated scheduling of daily stock delta updates was not evaluated beyond the master catalog ingestion test.

---

## Conclusion & Verdict
Based on rigorous empirical execution of `test_adversarial_m1_challenger_2.py` and `test_system_verification.py`:
- All 13 core system verification tests execute cleanly and pass with 0 errors.
- `GF-36TFIH` isolation is 100% verified with 0% contamination.
- Valve pairings across all AC tonnages (1.0T, 1.5T, 2.0T, 3.0T, 4.0T) strictly conform to thermodynamic line sizing specifications and official retail prices.
- **FINAL VERDICT: APPROVE**.
