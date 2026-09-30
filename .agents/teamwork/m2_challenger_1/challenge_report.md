# Empirical Adversarial Challenge Report — Milestone 2 (Challenger 1)

**Agent**: M2 Challenger 1  
**Working Directory**: `c:\Users\PC\Desktop\estimator\.agents\teamwork\m2_challenger_1`  
**Date**: 2026-09-29T18:46:00+05:00  
**Target Under Review**: Milestone 2 Implementation (`database.py`, `config.py`, `dwp_service.db`, `test_system_verification.py`)  
**Verdict**: **APPROVE**  

---

## Challenge Summary

**Overall risk assessment**: **LOW**

The Milestone 2 autonomous multi-tier resolution engine and physical valve line pairing subsystem were subjected to rigorous empirical adversarial testing. The architecture was challenged across boundary conditions, category contamination vectors, physical valve pairing standards, ledger valuation leakage, and zero-price vulnerabilities. 

All 16 automated tests in `test_system_verification.py` passed with 100% success and zero regressions. Database hygiene checks confirmed 0 obsolete ledger formula residues in `dwp_service.db`. Physical valve line pairing across 1.0 Ton, 1.5 Ton, 2.0 Ton, 3.0 Ton, and 4.0 Ton strictly isolates suction and liquid lines with 0% cross-contamination.

---

## Challenges

### [Low Risk] Challenge 1: Multi-Tier Partitioning & Contract Integrity Across Appliance Categories
- **Assumption challenged**: That `database.py:fetch_tiered_compatible_parts` reliably outputs the exact required multi-tier dictionary schema (`tier1`, `tier2`, `tier3`, `metadata`, `meta`, `role_groups`, `compatible_parts`, `total_parts_found`) with strictly mutually exclusive part assignments across Split AC, Floor Standing AC, Refrigerator, Washing Machine, and Water Dispenser.
- **Attack scenario**: Hostile inputs (whitespace-padded strings, mixed cases, missing models, non-AC models) might cause empty responses, key errors in UI consumers, or duplicate parts appearing in multiple tiers simultaneously.
- **Blast radius**: Streamlit frontend UI crashes, duplicate component listings, or invalid parts counts on customer estimates.
- **Empirical Observation & Result**:
  - Tested across 5 categories: Split AC (`GS-18PITH11W`, `GS-12PITH11W`), Floor Standing AC (`GF-36TFIH`, `GF-48TF`), Refrigerator (`GR-E8768G-CP1`), Washing Machine (`EW-F1202DC`), and Water Dispenser (`WD-E500`), plus hostile queries (`"  GS-18ZITH1W-T3  "`, `"=GF-36TFIH="`, `""`, `"   "`, `"' OR 1=1; --"`).
  - Schema integrity: 100% compliant. All dictionary keys present.
  - Tier codes: Every item in `tier1` has `tier_code == 1`; every item in `tier2` has `tier_code == 2`; every item in `tier3` has `tier_code == 3`, `bal_qty > 0`, and `in_stock is True`.
  - Count consistency: `len(tier1) + len(tier2) + len(tier3) == total_parts_found == len(compatible_parts)`.
  - Mutual exclusivity: Verified part numbers across tiers are strictly disjoint; `seen_part_nos` prevents duplication between exact model matches, series platform matches, and store fallbacks.
- **Mitigation Status**: Fully mitigated and verified in Test 15 of `test_system_verification.py`.

---

### [Low Risk] Challenge 2: Physical Valve Line Pairing Strictness & Capacity Isolation
- **Assumption challenged**: That Tier 3 fallback and `role_groups` under `"🔩 Cut-off & Service Valves"` strictly enforce physical line capacity pairing without leaking incompatible valve sizes:
  - 1.0 Ton: Strictly 3/8" Suction (71302395) + 1/4" Liquid (7130239)
  - 1.5 Ton: Strictly 1/2" Suction (7133774) + 1/4" Liquid (7130239)
  - 2.0 Ton & 3.0 Ton: Strictly 5/8" Suction (7133844) + 1/4" Liquid (7130239)
  - 4.0 Ton & 5.0 Ton: Strictly 5/8" Suction (7133844) + 3/8" Liquid (71302395)
- **Attack scenario**: In-stock store items with non-matching valve diameters leaking into Tier 3 or competing in role groups, resulting in technicians receiving physically incompatible service valves for field repairs.
- **Blast radius**: Technician arrives at repair site with mismatched valve diameters (e.g. 5/8" valve on a 1.0 Ton AC), causing aborted repairs and customer dissatisfaction.
- **Empirical Observation & Result**:
  - 1.0 Ton models (`GS-12PITH11W`): Leaks 0% 1/2" or 5/8" valves. Primary is 3/8" (71302395, Rs. 1,500), Alternative is 1/4" (7130239, Rs. 1,600).
  - 1.5 Ton models (`GS-18PITH11W`, `GS-18ZITH1W-T3`): Leaks 0% 3/8" or 5/8" valves. Primary is 1/2" (7133774, Rs. 2,100), Alternative is 1/4" (7130239, Rs. 1,600).
  - 2.0 Ton models (`GS-24PITH11W`): Leaks 0% 3/8" or 1/2" valves. Primary is 5/8" (7133844, Rs. 2,200), Alternative is 1/4" (7130239, Rs. 1,600).
  - 3.0 Ton Floor Standing (`GF-36TFIH`): Leaks 0% 3/8" or 1/2" valves. Primary is 5/8" (7133844, Rs. 2,200), Alternative is 1/4" (7130239, Rs. 1,600).
  - 4.0 Ton Floor Standing (`GF-48TF`): Leaks 0% 1/4" or 1/2" valves. Primary is 5/8" (7133844, Rs. 2,200), Alternative is 3/8" (71302395, Rs. 1,500).
  - Non-AC models (`GR-E8768G-CP1`, `EW-F1202DC`, `WD-E500`): Zero AC cut-off valves leak into any tier or role group.
- **Mitigation Status**: Fully mitigated and verified in Test 10 and Test 16 of `test_system_verification.py`.

---

### [Low Risk] Challenge 3: Zero-Price Immunity & Ledger Book Cost Hygiene
- **Assumption challenged**: That no part in any tier displays Rs. 0, and no obsolete accounting ledger formula (`AMOUNT / BAL_QTY`) valuation residues remain in `dwp_service.db`.
- **Attack scenario**: Obsolete warehouse accounting balances corrupting unit prices to Rs. 0 or displaying internal book costs instead of executive retail selling prices.
- **Blast radius**: Revenue loss from billing parts at Rs. 0 or accounting cost; underpricing on customer invoices.
- **Empirical Observation & Result**:
  - Over 1,030 parts audited across diverse models: 100% have price > Rs. 0.
  - Database query `SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND abs(amount - (unit_price * bal_qty)) > 0.01` returned exactly `0` discrepancies across all 972 rows.
  - All 518 official catalog parts verified in `stock_master`, `parts_master`, and `price_book`.
  - Master catalog prices confirmed:
    - 3/8" Valve (71302395): Rs. 1,500
    - 1/4" Valve (7130239): Rs. 1,600
    - 1/2" Valve (7133774): Rs. 2,100
    - 5/8" Valve (7133844): Rs. 2,200
    - GF-36TFIH Evaporator (11001000602): Rs. 58,000
    - GS-18AITH23W-T3 Evaporator (11001062414): Rs. 30,000
    - GF-48FW Evaporator (1004169): Rs. 70,000
    - GF-24ISH Evaporator (11001060092): Rs. 72,000
    - GF-48TF Evaporator (11001060521): Rs. 75,000
    - GF-24CB Evaporator (100404401): Rs. 66,000
- **Mitigation Status**: Fully mitigated and verified in Test 4, 8, 12, 13, 14, 16 of `test_system_verification.py`.

---

### [Low Risk] Challenge 4: Packaging and Non-Functional Material Exclusion
- **Assumption challenged**: That cardboard cartons, packaging boxes, packing foam, and shipping materials are excluded from cooling and electrical roles.
- **Attack scenario**: In-stock cartons matching model prefixes (e.g. "CARTON GS-18PITH") leaking into Evaporator, PCB, or Tier 3 fallback.
- **Blast radius**: Customers quoted for packing cardboard instead of actual cooling coils or circuit boards.
- **Empirical Observation & Result**:
  - `classify_component_role` strictly categorizes packing materials (`carton`, `packing`, `tray`, `foam`, `box`) as `Component Hardware`.
  - Tier 3 store in-stock filter explicitly drops all packing and carton items: `if any(k in p_desc.lower() for k in ['carton', 'caton', 'packing', 'tray', 'box', 'foam']): continue`.
  - Tested in Test 9 of `test_system_verification.py`. Zero packaging leaks detected.
- **Mitigation Status**: Fully mitigated.

---

### [Low Risk] Challenge 5: GF-36TFIH Floor Standing AC Isolation & Cross-Contamination Stress Test
- **Assumption challenged**: That 3.0 Ton Floor Standing AC `GF-36TFIH` returns ONLY genuine Evaporator 11001000602, 5/8" Suction Valve 7133844, and 1/4" Liquid Valve 7130239, with zero leakage of 24ISH or 48FW evaporators.
- **Attack scenario**: Cross-series leakage from other floor standing models (24ISH, 48FW, 48TF) or split AC evaporators into GF-36TFIH estimates.
- **Blast radius**: Misdiagnosis and quoting wrong evaporator assemblies for high-value commercial floor standing units.
- **Empirical Observation & Result**:
  - Tested in Test 11 of `test_system_verification.py`.
  - `GF-36TFIH` Evaporator group contains ONLY genuine 11001000602 (Rs. 58,000).
  - 0% leakage of 24ISH (11001060092), 48FW (1004169), 48TF (11001060521), or 24CB (100404401).
  - Service valves strictly paired as Suction 7133844 (5/8", Rs. 2,200) + Liquid 7130239 (1/4", Rs. 1,600).
- **Mitigation Status**: Fully mitigated.

---

## Stress Test Results

| Test ID | Scenario | Expected Behavior | Actual Behavior | Verdict |
|:-------:|:---------|:------------------|:----------------|:-------:|
| ST-01 | Bootstrap & Stock Metadata | Total > 0, Synced = Official vp786 catalog | 972 items, 777 in-stock, synced official | **PASS** |
| ST-02 | Strict Tokenizer Multi-Category | Correct Category, Tonnage, Series parsed | GS-18PITH (1.5T Split), GR-E (Ref), EW-F (WM) | **PASS** |
| ST-03 | Cross-Series Isolation (PITH vs CITH) | 11001060868 in PITH, 1002937LC in CITH, 0 leakage | Disjoint evaporator assignments, 0 cross-leakage | **PASS** |
| ST-04 | Zero-Pricing Immunity (1,030 parts) | 100% parts have price > Rs. 0 | 1,030 parts checked across 7 models; 0 zero prices | **PASS** |
| ST-05 | Global Stock Search (Evap, PCB, Valve) | Returns results with prices > Rs. 0 | 10 items found per keyword, all prices > 0 | **PASS** |
| ST-06 | GS-18ZITH1W-T3 Evaporator Resolution | In-stock 11001062414 (Stock=17, Rs. 30,000) | Genuine primary in-stock evaporator resolved | **PASS** |
| ST-07 | Service Overheads & Gas Pricing | Mobility=2000, Visit=600, Ref Gas=4000, Disp=3500 | Exact matching standard business overheads | **PASS** |
| ST-08 | Price Consistency (Direct vs Model) | Part 11001062414 is Rs. 30,000 in both | 100% price consistency verified | **PASS** |
| ST-09 | Packaging Carton Exclusion | Carton excluded; floor price Rs. 26,000 active | Functional roles carton-free; floor protected | **PASS** |
| ST-10 | Dual Valve Pairing (1.0T, 1.5T, 2.0T, 4.0T) | 1.0T: 3/8"+1/4"; 1.5T: 1/2"+1/4"; 2.0T: 5/8"+1/4"; 4.0T: 5/8"+3/8" | 100% strict physical line pairing, 0% leakage | **PASS** |
| ST-11 | GF-36TFIH Floor Standing Isolation | Evaporator 11001000602 (Rs. 58,000), Valves 5/8"+1/4" | Genuine 3.0T Evaporator isolated, 0% leakage | **PASS** |
| ST-12 | 1.0 Ton 3/8" Valve Customer Rate | Part 71302395 = Rs. 1,500 in Model & Direct Search | Exact customer billing ground truth verified | **PASS** |
| ST-13 | Closed-Complaint Ground-Truth Rates | 7133844 = Rs. 2,200, 7130239 = Rs. 1,600 | Closed complaint #282629821 ground truth verified | **PASS** |
| ST-14 | M1 Challenger Stress & Hygiene | 518 catalog parts, 0 ledger discrepancies, hostile robustness | 0 ledger discrepancies across 972 rows, SQL injection immune | **PASS** |
| ST-15 | Multi-Tier Schema & Contract Validation | tier1, tier2, tier3 lists + metadata counts | Validated on AC, Ref, Washing Machine, Dispenser | **PASS** |
| ST-16 | Tier 3 Physical Pairing & Ledger Hygiene | 0 ledger discrepancies, strict valve constraints in Tier 3 | 0 discrepancies, strict suction/liquid constraints | **PASS** |

---

## Unchallenged Areas

- **UI CSS Aesthetics Rendering in Headless Mode**: Visual styling of `.badge-tier-1`, `.badge-tier-2`, `.badge-tier-3` and metric containers in `app.py` was inspected via code review; dynamic visual browser rendering was not challenged in headless mode as it is an interface presentation layer rather than core pricing engine logic.

---

## Binary Verdict

**VERDICT**: **APPROVE**  
The Milestone 2 autonomous multi-tier resolution engine and physical valve line pairing subsystem satisfy all functional, structural, physical, and pricing integrity requirements. Zero failures or regressions detected.
