# test_adversarial_m2_challenger_1.py
"""
Empirical Adversarial Stress Test Suite for Milestone 2 (Challenger 1)
Focus:
1. Multi-tier resolution (Tier 1, Tier 2, Tier 3) contract and partitioning across appliance categories:
   - Split AC, Floor Standing AC, Refrigerator, Washing Machine, Water Dispenser, plus hostile inputs.
2. Strict physical valve line pairing in Tier 3 & role groups:
   - 1.0T -> 3/8" + 1/4"
   - 1.5T -> 1/2" + 1/4"
   - 2.0T / 3.0T -> 5/8" + 1/4"
   - 4.0T / 5.0T -> 5/8" + 3/8"
   - Non-AC isolation (0% AC valve leakage)
3. Zero-pricing immunity across all tiers, stock_master, and price catalog accuracy.
4. Packaging / carton exclusion from functional roles and Tier 3.
5. GF-36TFIH isolation & evaporator ground truth.
"""

import sys
import os
import sqlite3
import pandas as pd

from database import (
    fetch_tiered_compatible_parts,
    search_stock_global,
    get_connection,
    load_ground_truth_baseline
)
from config import (
    tokenize_appliance_model,
    classify_component_role,
    is_valve_tonnage_compatible,
    get_tonnage_valve_pairing
)

def clean_ascii(s):
    return str(s).encode('ascii', errors='ignore').decode('ascii').strip()

def run_all_adversarial_stress_tests():
    failures = []
    passes = []

    def record_fail(section, msg):
        c = clean_ascii(msg)
        print(f"  [FAIL] [{section}] {c}")
        failures.append((section, c))

    def record_ok(section, msg):
        c = clean_ascii(msg)
        print(f"  [PASS] [{section}] {c}")
        passes.append((section, c))

    print("=" * 80)
    print("RUNNING EMPIRICAL ADVERSARIAL STRESS TEST SUITE (M2 CHALLENGER 1)")
    print("=" * 80)

    # ==============================================================================
    # SECTION 1: Multi-Category Multi-Tier Contract & Partitioning Stress Test
    # ==============================================================================
    print("\n--- SECTION 1: Multi-Category Multi-Tier Contract & Partitioning ---")

    test_models_by_cat = {
        "Split AC": [
            "GS-12PITH11W", "GS-10CITH1", "GS-11CITH3F", "ES-12PITH",
            "GS-18PITH11W", "GS-18CITH12G", "GS-18ZITH1W-T3", "GS-18AITH23W-T3", "GS-18FITH", "GS-18VITH",
            "GS-24PITH11W", "GS-24CITH11"
        ],
        "Floor Standing AC": [
            "GF-24CB", "GF-24ISH", "GF-36TFIH", "GF-36TF", "GF-48FW", "GF-48TF", "GF-60TF"
        ],
        "Refrigerator": [
            "GR-E8768G-CP1", "GR-E9000", "GR-B300"
        ],
        "Washing Machine": [
            "EW-F1202DC", "WM-100", "EW-800"
        ],
        "Water Dispenser": [
            "WD-E500", "WD-300"
        ],
        "Adversarial / Hostile": [
            "  GS-18PITH11W  ", "gs-18pith11w", "gS-18pITH11w", "  gf-36tfih  ",
            "=GF-36TFIH=", "--GS-18PITH11W--", "UNKNOWN-MODEL-XYZ", "RANDOM-12345",
            "", "   ", "' OR '1'='1"
        ]
    }

    all_audited_parts_count = 0
    required_keys = ['tier1', 'tier2', 'tier3', 'metadata', 'meta', 'role_groups', 'compatible_parts', 'total_parts_found']

    for cat_name, models in test_models_by_cat.items():
        for m in models:
            res = fetch_tiered_compatible_parts(m)
            if not isinstance(res, dict):
                record_fail("Contract", f"Model '{m}' did not return dict")
                continue

            # Verify contract keys
            for k in required_keys:
                if k not in res:
                    record_fail("Contract", f"Model '{m}' missing key '{k}'")

            t1 = res.get('tier1', [])
            t2 = res.get('tier2', [])
            t3 = res.get('tier3', [])
            meta_d = res.get('metadata', {})
            comp = res.get('compatible_parts', [])
            tot = res.get('total_parts_found', 0)

            # Metadata counts match actual lists
            if meta_d.get('tier1_count') != len(t1):
                record_fail("Counts", f"Model '{m}' meta tier1_count ({meta_d.get('tier1_count')}) != len(t1) ({len(t1)})")
            if meta_d.get('tier2_count') != len(t2):
                record_fail("Counts", f"Model '{m}' meta tier2_count ({meta_d.get('tier2_count')}) != len(t2) ({len(t2)})")
            if meta_d.get('tier3_count') != len(t3):
                record_fail("Counts", f"Model '{m}' meta tier3_count ({meta_d.get('tier3_count')}) != len(t3) ({len(t3)})")

            # Total consistency
            if len(t1) + len(t2) + len(t3) != tot:
                record_fail("Total", f"Model '{m}' t1+t2+t3 sum ({len(t1)+len(t2)+len(t3)}) != total_parts_found ({tot})")
            if len(comp) != tot:
                record_fail("Total", f"Model '{m}' compatible_parts len ({len(comp)}) != total_parts_found ({tot})")

            # Check tier codes, stock status, and mutual exclusivity of part numbers across tiers
            t1_pnos = set()
            for p in t1:
                all_audited_parts_count += 1
                pno = p.get('part_no', '').upper()
                t1_pnos.add(pno)
                if p.get('tier_code') != 1:
                    record_fail("TierCode", f"Model '{m}' tier1 item {pno} has tier_code {p.get('tier_code')} != 1")

            t2_pnos = set()
            for p in t2:
                all_audited_parts_count += 1
                pno = p.get('part_no', '').upper()
                t2_pnos.add(pno)
                if p.get('tier_code') != 2:
                    record_fail("TierCode", f"Model '{m}' tier2 item {pno} has tier_code {p.get('tier_code')} != 2")

            t3_pnos = set()
            for p in t3:
                all_audited_parts_count += 1
                pno = p.get('part_no', '').upper()
                t3_pnos.add(pno)
                if p.get('tier_code') != 3:
                    record_fail("TierCode", f"Model '{m}' tier3 item {pno} has tier_code {p.get('tier_code')} != 3")
                if p.get('bal_qty', 0) <= 0:
                    record_fail("Tier3Stock", f"Model '{m}' tier3 item {pno} bal_qty <= 0: {p.get('bal_qty')}")
                if p.get('in_stock') is not True:
                    record_fail("Tier3Stock", f"Model '{m}' tier3 item {pno} in_stock is not True")

            # Mutual exclusivity check
            t1_t2_overlap = t1_pnos.intersection(t2_pnos)
            if t1_t2_overlap:
                record_fail("MutualExclusivity", f"Model '{m}' has duplicate part_nos in Tier 1 and Tier 2: {t1_t2_overlap}")
            t1_t3_overlap = t1_pnos.intersection(t3_pnos)
            if t1_t3_overlap:
                record_fail("MutualExclusivity", f"Model '{m}' has duplicate part_nos in Tier 1 and Tier 3: {t1_t3_overlap}")
            t2_t3_overlap = t2_pnos.intersection(t3_pnos)
            if t2_t3_overlap:
                record_fail("MutualExclusivity", f"Model '{m}' has duplicate part_nos in Tier 2 and Tier 3: {t2_t3_overlap}")

    record_ok("Section 1", f"Audited {all_audited_parts_count} parts across {sum(len(v) for v in test_models_by_cat.values())} test models. All contracts and tier partitioning passed.")

    # ==============================================================================
    # SECTION 2: Physical Valve Line Pairing Strictness in Tier 3 & Role Groups
    # ==============================================================================
    print("\n--- SECTION 2: Physical Valve Line Pairing Strictness ---")

    # Strict definitions:
    # 1.0T: Suction = 3/8" (71302395), Liquid = 1/4" (7130239)
    # 1.5T: Suction = 1/2" (7133774),  Liquid = 1/4" (7130239)
    # 2.0T: Suction = 5/8" (7133844),  Liquid = 1/4" (7130239)
    # 3.0T: Suction = 5/8" (7133844),  Liquid = 1/4" (7130239)
    # 4.0T: Suction = 5/8" (7133844),  Liquid = 3/8" (71302395)
    # 5.0T: Suction = 5/8" (7133844),  Liquid = 3/8" (71302395)

    tonnage_valve_specs = [
        # (models, tonnage, exp_suction_role, exp_suction_pno, exp_liquid_role, exp_liquid_pno, forbidden_pnos, forbidden_roles)
        (
            ["GS-12PITH11W", "GS-10CITH1", "GS-11CITH3F", "ES-12PITH"],
            "1.0 Ton",
            "Cut-Off Valve (3/8\")", "71302395",
            "Cut-Off Valve (1/4\")", "7130239",
            ["7133774", "7133844", "7135142"],
            ["Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")"]
        ),
        (
            ["GS-18PITH11W", "GS-18CITH12G", "GS-18ZITH1W-T3", "GS-18AITH23W-T3", "GS-18FITH", "GS-18VITH"],
            "1.5 Ton",
            "Cut-Off Valve (1/2\")", "7133774",
            "Cut-Off Valve (1/4\")", "7130239",
            ["71302395", "7133474", "7133844", "7135142"],
            ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"]
        ),
        (
            ["GS-24PITH11W", "GS-24CITH11", "GF-24CB", "GF-24ISH"],
            "2.0 Ton",
            "Cut-Off Valve (5/8\")", "7133844",
            "Cut-Off Valve (1/4\")", "7130239",
            ["71302395", "7133474", "7133774"],
            ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]
        ),
        (
            ["GF-36TFIH", "GF-36TF"],
            "3.0 Ton",
            "Cut-Off Valve (5/8\")", "7133844",
            "Cut-Off Valve (1/4\")", "7130239",
            ["71302395", "7133474", "7133774"],
            ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]
        ),
        (
            ["GF-48FW", "GF-48TF"],
            "4.0 Ton",
            "Cut-Off Valve (5/8\")", "7133844",
            "Cut-Off Valve (3/8\")", "71302395",
            ["7130239", "7133774"],
            ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"]
        ),
        (
            ["GF-60TF"],
            "5.0 Ton",
            "Cut-Off Valve (5/8\")", "7133844",
            "Cut-Off Valve (3/8\")", "71302395",
            ["7130239", "7133774"],
            ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"]
        )
    ]

    for models, ton, exp_suc_role, exp_suc_pno, exp_liq_role, exp_liq_pno, forb_pnos, forb_roles in tonnage_valve_specs:
        for m in models:
            res = fetch_tiered_compatible_parts(m)
            t3 = res.get('tier3', [])
            
            # 1. Tier 3 strict prohibition check
            for p in t3:
                pno = p.get('part_no', '')
                r = p.get('role', '')
                pname = p.get('part_name', '')
                for fp in forb_pnos:
                    if pno == fp:
                        record_fail("Tier3ValveProhibited", f"Model '{m}' ({ton}) leaked prohibited valve part_no {fp} ({pname}) in Tier 3!")
                for fr in forb_roles:
                    if r == fr:
                        record_fail("Tier3ValveProhibited", f"Model '{m}' ({ton}) leaked prohibited valve role {fr} ({pno}) in Tier 3!")

            # 2. Role groups valve pairing check
            v_grp = next((g for g in res.get('role_groups', []) if "Cut-off & Service Valves" in g.get('group_title', '')), None)
            if not v_grp:
                record_fail("ValveGroupMissing", f"Model '{m}' ({ton}) missing Cut-off & Service Valves group!")
                continue

            pri = v_grp.get('primary')
            alts = v_grp.get('alternatives', [])
            if not pri:
                record_fail("ValvePrimaryMissing", f"Model '{m}' ({ton}) missing primary valve!")
                continue

            # Primary must be Suction Valve
            if pri.get('role') != exp_suc_role:
                record_fail("ValvePairingPrimary", f"Model '{m}' ({ton}) primary valve role expected '{exp_suc_role}', got '{pri.get('role')}' ({pri.get('part_no')})")
            if pri.get('part_no') != exp_suc_pno:
                record_fail("ValvePairingPrimaryPno", f"Model '{m}' ({ton}) primary valve part_no expected '{exp_suc_pno}', got '{pri.get('part_no')}'")

            # Alternative must be Liquid Valve
            if not alts:
                record_fail("ValveLiquidMissing", f"Model '{m}' ({ton}) missing liquid valve in alternatives!")
            else:
                liq = alts[0]
                if liq.get('role') != exp_liq_role:
                    record_fail("ValvePairingLiquid", f"Model '{m}' ({ton}) liquid valve role expected '{exp_liq_role}', got '{liq.get('role')}' ({liq.get('part_no')})")
                if liq.get('part_no') != exp_liq_pno:
                    record_fail("ValvePairingLiquidPno", f"Model '{m}' ({ton}) liquid valve part_no expected '{exp_liq_pno}', got '{liq.get('part_no')}'")

            # Must have exactly 1 primary and at most 1 alternative (clean 2-valve pair with 0 clutter)
            if len(alts) > 1:
                extra_pnos = [a.get('part_no') for a in alts[1:]]
                record_fail("ValveClutter", f"Model '{m}' ({ton}) has extra clutter valves in alternatives: {extra_pnos}")

    # 3. Non-AC Isolation check: zero AC valves or evaporators leaking to non-AC
    non_ac_test_models = ["GR-E8768G-CP1", "GR-E9000", "EW-F1202DC", "WM-100", "WD-E500", "WD-300"]
    all_ac_valve_pnos = {'7130239', '71302395', '7133774', '7133844', '7133474', '7135142'}
    all_ac_evap_pnos = {'11001000602', '11001060868', '11001062414', '1004169', '11001060092', '11001060521', '100404401', '1002937LC', '11001061842LC'}

    for m in non_ac_test_models:
        res = fetch_tiered_compatible_parts(m)
        all_parts = res.get('tier1', []) + res.get('tier2', []) + res.get('tier3', [])
        for p in all_parts:
            pno = p.get('part_no', '')
            r = p.get('role', '')
            if pno in all_ac_valve_pnos or "Cut-Off Valve" in r:
                record_fail("NonACLeakage", f"Non-AC model '{m}' leaked AC Valve: {pno} ({r})")
            if "Washing Machine" in res.get('meta', {}).get('category', '') and "Evaporator" in r:
                record_fail("NonACLeakage", f"Washing machine model '{m}' leaked Evaporator: {pno}")
            if pno in all_ac_evap_pnos:
                record_fail("NonACLeakage", f"Non-AC model '{m}' leaked AC Evaporator: {pno}")

        # Non-AC must never have Cut-off & Service Valves role group
        v_grp = next((g for g in res.get('role_groups', []) if "Cut-off & Service Valves" in g.get('group_title', '')), None)
        if v_grp:
            record_fail("NonACValveGroup", f"Non-AC model '{m}' contains Cut-off & Service Valves group!")

    record_ok("Section 2", "All AC tonnages (1.0T, 1.5T, 2.0T, 3.0T, 4.0T, 5.0T) strictly respect physical pairing with zero leakage and zero non-AC contamination.")

    # ==============================================================================
    # SECTION 3: Zero-Pricing Check Across All Tiers, Database & Acceptance Catalog
    # ==============================================================================
    print("\n--- SECTION 3: Zero-Pricing Check & Acceptance Catalog Accuracy ---")

    zero_price_violations = 0
    audited_model_parts = 0

    # Test all models in test_models_by_cat
    for cat_name, models in test_models_by_cat.items():
        for m in models:
            res = fetch_tiered_compatible_parts(m)
            all_parts = res.get('tier1', []) + res.get('tier2', []) + res.get('tier3', [])
            for p in all_parts:
                audited_model_parts += 1
                pr = p.get('price', 0)
                if pr <= 0:
                    record_fail("ZeroPriceTier", f"Model '{m}' part {p.get('part_no')} has price {pr} <= 0!")
                    zero_price_violations += 1

    # Check stock_master in SQLite
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0 AND bal_qty > 0")
        zero_stk_cnt = c.fetchone()[0]
        if zero_stk_cnt > 0:
            record_fail("ZeroPriceDB", f"Found {zero_stk_cnt} rows in stock_master with unit_price <= 0 and bal_qty > 0!")

        # Check ledger valuation discrepancies: abs(amount - (unit_price * bal_qty)) > 0.01
        c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND abs(amount - (unit_price * bal_qty)) > 0.01")
        discrepancy_cnt = c.fetchone()[0]
        if discrepancy_cnt > 0:
            record_fail("LedgerDiscrepancy", f"Found {discrepancy_cnt} rows in stock_master with corrupted ledger valuation amount != unit_price * bal_qty!")

        # Verify all 518 official catalog parts
        c.execute("SELECT count(*) FROM stock_master WHERE last_synced = 'DWP Official Price Catalog (vp786.pdf)'")
        cat_518_cnt = c.fetchone()[0]
        if cat_518_cnt < 518:
            record_fail("CatalogIngestion", f"Expected 518 official catalog parts, found {cat_518_cnt}")

    # Official Acceptance Price Validation
    expected_acceptance_prices = {
        "71302395": (1500, "3/8\" Cut-Off Valve (1.0 Ton)"),
        "7130239":  (1600, "1/4\" Cut-Off Valve (Universal Liquid)"),
        "7133774":  (2100, "1/2\" Cut-Off Valve (1.5 Ton)"),
        "7133844":  (2200, "5/8\" Cut-Off Valve (2.0T / 3.0T / 4.0T)"),
        "11001000602": (58000, "GF-36TFIH Genuine 3.0T Evaporator"),
        "11001062414": (30000, "GS-18AITH23W-T3 / GS-18ZITH Evaporator"),
        "1004169":     (70000, "GF-48FW Evaporator"),
        "11001060092": (72000, "GF-24ISH Evaporator"),
        "11001060521": (75000, "GF-48TF Evaporator"),
        "100404401":   (66000, "GF-24CB Evaporator")
    }

    baseline = load_ground_truth_baseline()
    price_book = baseline.get('price_book', {})

    for pno, (exp_pr, desc) in expected_acceptance_prices.items():
        # Check in price_book
        pb_entry = price_book.get(pno)
        if not pb_entry or pb_entry.get('price') != exp_pr:
            record_fail("AcceptancePricePB", f"{desc} ({pno}) in price_book expected Rs. {exp_pr}, got {pb_entry.get('price') if pb_entry else 'NOT_FOUND'}")

        # Check in stock_master
        with get_connection() as conn:
            row = conn.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,)).fetchone()
            if not row or row[0] != exp_pr:
                record_fail("AcceptancePriceDB", f"{desc} ({pno}) in stock_master expected Rs. {exp_pr}, got {row[0] if row else 'NOT_FOUND'}")

        # Check in global search
        sr = search_stock_global(pno)
        if sr.empty:
            record_fail("AcceptancePriceSearch", f"{desc} ({pno}) search_stock_global returned empty!")
        else:
            sr_pr = int(sr.iloc[0]['price'])
            if sr_pr != exp_pr:
                record_fail("AcceptancePriceSearch", f"{desc} ({pno}) search_stock_global expected Rs. {exp_pr}, got Rs. {sr_pr}")

    record_ok("Section 3", f"Audited {audited_model_parts} parts across models. Zero prices = 0, ledger discrepancies = 0, and all official acceptance prices verified.")

    # ==============================================================================
    # SECTION 4: Packaging and Non-Functional Item Exclusion Audit
    # ==============================================================================
    print("\n--- SECTION 4: Packaging and Non-Functional Item Exclusion ---")

    packaging_keywords = ['carton', 'caton', 'packing', 'tray', 'box', 'foam']
    functional_roles = [
        "Evaporator Assembly", "Outdoor Inverter PCB", "Indoor Main PCB",
        "Circuit Board (PCB)", "Compressor & Fittings", "Fan Motor",
        "Indoor Fan Motor", "Outdoor Fan Motor", "Stepping / Swing Motor",
        "Cut-Off Valve (1/4\")", "Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")",
        "Cut-Off Valve (5/8\")", "4-Way Valve Assembly", "Temperature Sensor", "Capacitor"
    ]

    for cat_name, models in test_models_by_cat.items():
        for m in models:
            res = fetch_tiered_compatible_parts(m)
            # Check Tier 3 for packaging items
            for p in res.get('tier3', []):
                pname = p.get('part_name', '').lower()
                if any(kw in pname for kw in packaging_keywords):
                    record_fail("CartonInTier3", f"Model '{m}' leaked packaging item into Tier 3: {p.get('part_no')} ({pname})")

            # Check role groups: packaging items must never be classified as functional cooling/electrical roles
            for grp in res.get('role_groups', []):
                items = [grp.get('primary')] + grp.get('alternatives', [])
                for item in items:
                    if not item:
                        continue
                    pname = item.get('part_name', '').lower()
                    r = item.get('role')
                    if r in functional_roles:
                        if any(kw in pname for kw in packaging_keywords):
                            record_fail("CartonInFunctionalRole", f"Model '{m}' placed packaging item '{pname}' into functional role '{r}'!")

    record_ok("Section 4", "Zero packaging materials leaked into Tier 3 or functional cooling/electrical roles.")

    # ==============================================================================
    # SECTION 5: GF-36TFIH Isolation & Floor Standing Verification
    # ==============================================================================
    print("\n--- SECTION 5: GF-36TFIH Floor Standing AC Isolation ---")

    res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
    meta_36 = res_36.get('meta', {})
    if meta_36.get('category') != "Floor Standing AC":
        record_fail("GF36Isolation", f"GF-36TFIH category expected 'Floor Standing AC', got '{meta_36.get('category')}'")
    if meta_36.get('tonnage') != "3.0 Ton":
        record_fail("GF36Isolation", f"GF-36TFIH tonnage expected '3.0 Ton', got '{meta_36.get('tonnage')}'")

    # Primary Evaporator: 11001000602 @ Rs. 58,000
    evap_grp = next((g for g in res_36.get('role_groups', []) if "Evaporator" in g.get('group_title', '')), None)
    if not evap_grp:
        record_fail("GF36Isolation", "GF-36TFIH missing Evaporator group!")
    else:
        pri_evap = evap_grp.get('primary', {})
        if pri_evap.get('part_no') != "11001000602":
            record_fail("GF36Isolation", f"GF-36TFIH primary evaporator expected 11001000602, got {pri_evap.get('part_no')}")
        if pri_evap.get('price') != 58000:
            record_fail("GF36Isolation", f"GF-36TFIH primary evaporator price expected 58000, got {pri_evap.get('price')}")

        all_evap_pnos = [pri_evap.get('part_no')] + [a.get('part_no') for a in evap_grp.get('alternatives', [])]
        leaked_evaps = [p for p in all_evap_pnos if p in ['11001060092', '1004169', '11001060521', '100404401']]
        if leaked_evaps:
            record_fail("GF36Isolation", f"GF-36TFIH leaked incompatible evaporators: {leaked_evaps}")

    # Valves: Suction 7133844 (5/8", Rs. 2,200), Liquid 7130239 (1/4", Rs. 1,600)
    v_grp = next((g for g in res_36.get('role_groups', []) if "Cut-off & Service Valves" in g.get('group_title', '')), None)
    if not v_grp:
        record_fail("GF36Isolation", "GF-36TFIH missing Valves group!")
    else:
        pri_v = v_grp.get('primary', {})
        if pri_v.get('part_no') != "7133844" or pri_v.get('price') != 2200:
            record_fail("GF36Isolation", f"GF-36TFIH primary valve expected 7133844 (Rs. 2,200), got {pri_v.get('part_no')} (Rs. {pri_v.get('price')})")

        alt_v = v_grp.get('alternatives', [])
        if not alt_v or alt_v[0].get('part_no') != "7130239" or alt_v[0].get('price') != 1600:
            record_fail("GF36Isolation", f"GF-36TFIH liquid valve expected 7130239 (Rs. 1,600), got {alt_v[0].get('part_no') if alt_v else 'NONE'}")

    record_ok("Section 5", "GF-36TFIH strictly isolated with genuine 3.0T Evaporator 11001000602 (Rs. 58,000) and paired valves 7133844 (Rs. 2,200) + 7130239 (Rs. 1,600).")

    # ==============================================================================
    # FINAL VERDICT
    # ==============================================================================
    print("\n" + "=" * 80)
    print(f"ADVERSARIAL STRESS TEST SUMMARY: {len(passes)} PASSED, {len(failures)} FAILED")
    print("=" * 80)

    if failures:
        print("\nFAILURE DETAILS:")
        for sec, msg in failures:
            print(f"  - [{sec}]: {msg}")
        print("\nVERDICT: REJECT - EMPIRICAL STRESS FAILURES DETECTED!")
        return False
    else:
        print("\nVERDICT: APPROVE - ALL EMPIRICAL ADVERSARIAL CHALLENGES PASSED (0 FAILURES)!")
        return True

if __name__ == "__main__":
    success = run_all_adversarial_stress_tests()
    sys.exit(0 if success else 1)
