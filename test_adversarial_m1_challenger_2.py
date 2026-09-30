# test_adversarial_m1_challenger_2.py
"""
Adversarial Empirical Challenge Suite for Milestone 1 (Challenger 2)
Targeting:
1. database.py:fetch_tiered_compatible_parts
2. GF-36TFIH Floor Standing AC Isolation & Cross-Series Contamination
3. Valve physical pairings across all AC tonnages:
   - 1.0T -> 3/8" + 1/4"
   - 1.5T -> 1/2" + 1/4"
   - 2.0T/3.0T -> 5/8" + 1/4"
   - 4.0T -> 5/8" + 3/8"
4. Cross-series isolation (PITH, CITH, ZITH, TFIH, FWITH, ISH, CB, FW, TF)
5. Non-AC Category Isolation (Ref, WM, WD)
6. Zero-price immunity & robust fallback under hostile / boundary inputs
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

def run_challenger_2_tests():
    failures = []

    def record_failure(category, message):
        clean_msg = clean_ascii(message)
        print(f"[FAIL] [{category}]: {clean_msg}")
        failures.append((category, clean_msg))

    def record_pass(category, message):
        clean_msg = clean_ascii(message)
        print(f"[PASS] [{category}]: {clean_msg}")

    print("\n" + "=" * 80)
    print("RUNNING ADVERSARIAL EMPIRICAL CHALLENGE SUITE (M1 CHALLENGER 2)")
    print("=" * 80)

    # ==============================================================================
    # CHALLENGE SECTION 1: GF-36TFIH Stress Testing & Isolation
    # ==============================================================================
    print("\n[CHALLENGE 1] GF-36TFIH Isolation, Genuine Parts & Contamination Audit...")

    test_36_models = [
        "GF-36TFIH",
        "gf-36tfih",
        "  GF-36TFIH  ",
        "=GF-36TFIH="
    ]

    for raw_m in test_36_models:
        res = fetch_tiered_compatible_parts(raw_m)
        assert isinstance(res, dict), f"Resolution for '{raw_m}' must return a dict"
        meta = res.get('meta', {})
        
        if meta.get('category') != "Floor Standing AC":
            record_failure("GF-36TFIH Meta", f"'{raw_m}': Category must be 'Floor Standing AC', got '{meta.get('category')}'")
        if meta.get('tonnage') != "3.0 Ton":
            record_failure("GF-36TFIH Meta", f"'{raw_m}': Tonnage must be '3.0 Ton', got '{meta.get('tonnage')}'")
        if meta.get('series') != "TFIH":
            record_failure("GF-36TFIH Meta", f"'{raw_m}': Series must be 'TFIH', got '{meta.get('series')}'")

        # 1. Evaporator verification
        evap_grp = next((g for g in res.get('role_groups', []) if "Evaporator" in g.get('group_title', '')), None)
        if not evap_grp:
            record_failure("GF-36TFIH Evaporator", f"'{raw_m}': Missing Evaporator Assemblies group")
        else:
            pri = evap_grp.get('primary', {})
            if pri.get('part_no') != "11001000602":
                record_failure("GF-36TFIH Evaporator", f"'{raw_m}': Primary evaporator must be 11001000602, got '{pri.get('part_no')}'")
            if pri.get('price') != 58000:
                record_failure("GF-36TFIH Evaporator Price", f"'{raw_m}': Evaporator price must be Rs. 58,000, got {pri.get('price')}")
                
            all_evap_pnos = [pri.get('part_no')] + [a.get('part_no') for a in evap_grp.get('alternatives', [])]
            
            # Forbidden evaporators from other series/tonnages
            forbidden_evaps = {
                '11001060092': "2.0T GF-24ISH (Rs. 72,000)",
                '1004169':     "4.0T GF-48FW (Rs. 70,000)",
                '11001060246': "4.0T GF-48FWITH",
                '11001060521': "4.0T GF-48TF (Rs. 75,000)",
                '100404401':   "2.0T GF-24CB (Rs. 66,000)",
                '11001060868': "1.5T GS-18PITH1W (Rs. 26,000)",
                '11001062414': "1.5T GS-18AITH23W-T3 (Rs. 30,000)",
                '1002937LC':   "1.5T GS-18CITH12G (Rs. 26,000)"
            }
            
            for f_pno, f_desc in forbidden_evaps.items():
                if f_pno in all_evap_pnos:
                    record_failure("GF-36TFIH Contamination", f"CRITICAL: Foreign evaporator {f_pno} ({f_desc}) leaked into '{raw_m}'!")

        # 2. Valve verification
        valve_grp = next((g for g in res.get('role_groups', []) if "Cut-off & Service Valves" in g.get('group_title', '')), None)
        if not valve_grp:
            record_failure("GF-36TFIH Valve", f"'{raw_m}': Missing Cut-off & Service Valves group")
        else:
            v_pri = valve_grp.get('primary', {})
            v_alts = valve_grp.get('alternatives', [])
            
            # Suction valve must be 5/8" (7133844) @ Rs. 2,200
            if v_pri.get('part_no') != "7133844":
                record_failure("GF-36TFIH Suction Valve", f"'{raw_m}': Primary valve must be 7133844 (5/8\"), got '{v_pri.get('part_no')}'")
            if v_pri.get('price') != 2200:
                record_failure("GF-36TFIH Suction Valve Price", f"'{raw_m}': 5/8\" valve price must be Rs. 2,200, got {v_pri.get('price')}")
            if v_pri.get('role') != "Cut-Off Valve (5/8\")":
                record_failure("GF-36TFIH Suction Valve Role", f"'{raw_m}': Primary valve role must be Cut-Off Valve (5/8\"), got '{v_pri.get('role')}'")
                
            # Liquid valve must be 1/4" (7130239) @ Rs. 1,600
            if not v_alts or v_alts[0].get('part_no') != "7130239":
                record_failure("GF-36TFIH Liquid Valve", f"'{raw_m}': Alt valve must be 7130239 (1/4\"), got '{v_alts[0].get('part_no') if v_alts else 'None'}'")
            if v_alts and v_alts[0].get('price') != 1600:
                record_failure("GF-36TFIH Liquid Valve Price", f"'{raw_m}': 1/4\" valve price must be Rs. 1,600, got {v_alts[0].get('price')}")
            if v_alts and v_alts[0].get('role') != "Cut-Off Valve (1/4\")":
                record_failure("GF-36TFIH Liquid Valve Role", f"'{raw_m}': Alt valve role must be Cut-Off Valve (1/4\"), got '{v_alts[0].get('role')}'")

            # Incompatible valve contamination
            all_valves = [v_pri] + v_alts
            all_valve_roles = [v.get('role') for v in all_valves]
            if "Cut-Off Valve (3/8\")" in all_valve_roles:
                record_failure("GF-36TFIH Valve Contamination", f"3/8\" valve leaked into 3.0T model '{raw_m}'")
            if "Cut-Off Valve (1/2\")" in all_valve_roles:
                record_failure("GF-36TFIH Valve Contamination", f"1/2\" valve leaked into 3.0T model '{raw_m}'")

    record_pass("GF-36TFIH Isolation", "GF-36TFIH returns genuine 3.0T Evaporator 11001000602 (Rs. 58,000), 5/8\" Suction Valve 7133844 (Rs. 2,200), and 1/4\" Liquid Valve 7130239 (Rs. 1,600) with 0% contamination.")

    # ==============================================================================
    # CHALLENGE SECTION 2: Comprehensive Valve Physical Pairings Across AC Tonnages
    # ==============================================================================
    print("\n[CHALLENGE 2] Physical Valve Pairing Across All AC Tonnages...")

    valve_tonnage_matrix = [
        # 1.0 Ton Models: 3/8" Suction (#1) + 1/4" Liquid (#2)
        {
            'tonnage': '1.0 Ton',
            'models': ['GS-12PITH11W', 'GS-12CITH11W', 'GS-11CITH3F', 'GS-10PITH1', 'ES-12'],
            'exp_suction_pno': '71302395',
            'exp_suction_role': 'Cut-Off Valve (3/8")',
            'exp_suction_price': 1500,
            'exp_liquid_pno': '7130239',
            'exp_liquid_role': 'Cut-Off Valve (1/4")',
            'exp_liquid_price': 1600,
            'forbidden_roles': ["Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")"]
        },
        # 1.5 Ton Models: 1/2" Suction (#1) + 1/4" Liquid (#2)
        {
            'tonnage': '1.5 Ton',
            'models': ['GS-18ZITH1W-T3', 'GS-18PITH11W', 'GS-18CITH12G', 'GS-18AITH23W-T3', 'GS-18VITH1', 'ES-18'],
            'exp_suction_pno': '7133774',
            'exp_suction_role': 'Cut-Off Valve (1/2")',
            'exp_suction_price': 2100,
            'exp_liquid_pno': '7130239',
            'exp_liquid_role': 'Cut-Off Valve (1/4")',
            'exp_liquid_price': 1600,
            'forbidden_roles': ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"]
        },
        # 2.0 Ton Models: 5/8" Suction (#1) + 1/4" Liquid (#2)
        {
            'tonnage': '2.0 Ton',
            'models': ['GS-24PITH11W', 'GS-24CITH1', 'GS-24LITH11M', 'GF-24ISH', 'GF-24CB'],
            'exp_suction_pno': '7133844',
            'exp_suction_role': 'Cut-Off Valve (5/8")',
            'exp_suction_price': 2200,
            'exp_liquid_pno': '7130239',
            'exp_liquid_role': 'Cut-Off Valve (1/4")',
            'exp_liquid_price': 1600,
            'forbidden_roles': ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]
        },
        # 3.0 Ton Models: 5/8" Suction (#1) + 1/4" Liquid (#2)
        {
            'tonnage': '3.0 Ton',
            'models': ['GF-36TFIH', 'GF-36TF', 'GF-36'],
            'exp_suction_pno': '7133844',
            'exp_suction_role': 'Cut-Off Valve (5/8")',
            'exp_suction_price': 2200,
            'exp_liquid_pno': '7130239',
            'exp_liquid_role': 'Cut-Off Valve (1/4")',
            'exp_liquid_price': 1600,
            'forbidden_roles': ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"]
        },
        # 4.0 Ton Models: 5/8" Suction (#1) + 3/8" Liquid (#2)
        {
            'tonnage': '4.0 Ton',
            'models': ['GF-48TF', 'GF-48FW', 'GF-48FWITH'],
            'exp_suction_pno': '7133844',
            'exp_suction_role': 'Cut-Off Valve (5/8")',
            'exp_suction_price': 2200,  # Official Catalog Price in stock_master/parts_master
            'exp_liquid_pno': '71302395',
            'exp_liquid_role': 'Cut-Off Valve (3/8")',
            'exp_liquid_price': 1500,  # Official Catalog Price in stock_master/parts_master
            'forbidden_roles': ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"]
        }
    ]

    for tier_spec in valve_tonnage_matrix:
        ton = tier_spec['tonnage']
        print(f"\n--- Testing Tonnage Bracket: {ton} ---")
        for m in tier_spec['models']:
            res = fetch_tiered_compatible_parts(m)
            vg = next((g for g in res.get('role_groups', []) if "Cut-off & Service Valves" in g.get('group_title', '')), None)
            if not vg:
                record_failure("Valve Pairing Missing", f"Model '{m}' ({ton}) has no Cut-off & Service Valves group!")
                continue
                
            pri = vg.get('primary', {})
            alts = vg.get('alternatives', [])
            
            # Verify Suction Valve (Rank #1)
            if pri.get('part_no') != tier_spec['exp_suction_pno']:
                record_failure("Suction Valve Part Mismatch", f"Model '{m}' ({ton}): Primary valve expected {tier_spec['exp_suction_pno']}, got {pri.get('part_no')}")
            if pri.get('role') != tier_spec['exp_suction_role']:
                record_failure("Suction Valve Role Mismatch", f"Model '{m}' ({ton}): Primary valve role expected {tier_spec['exp_suction_role']}, got {pri.get('role')}")
            if pri.get('price') != tier_spec['exp_suction_price']:
                record_failure("Suction Valve Price Mismatch", f"Model '{m}' ({ton}): Primary valve price expected Rs. {tier_spec['exp_suction_price']}, got Rs. {pri.get('price')}")
                
            # Verify Liquid Valve (Rank #2)
            if not alts or alts[0].get('part_no') != tier_spec['exp_liquid_pno']:
                record_failure("Liquid Valve Part Mismatch", f"Model '{m}' ({ton}): Alt valve expected {tier_spec['exp_liquid_pno']}, got {alts[0].get('part_no') if alts else 'None'}")
            if alts and alts[0].get('role') != tier_spec['exp_liquid_role']:
                record_failure("Liquid Valve Role Mismatch", f"Model '{m}' ({ton}): Alt valve role expected {tier_spec['exp_liquid_role']}, got {alts[0].get('role')}")
            if alts and alts[0].get('price') != tier_spec['exp_liquid_price']:
                record_failure("Liquid Valve Price Mismatch", f"Model '{m}' ({ton}): Alt valve price expected Rs. {tier_spec['exp_liquid_price']}, got Rs. {alts[0].get('price')}")
                
            # Verify Strict Tonnage Exclusion of Incompatible Sizes
            all_roles = [pri.get('role')] + [a.get('role') for a in alts]
            for f_role in tier_spec['forbidden_roles']:
                if f_role in all_roles:
                    record_failure("Valve Tonnage Leakage", f"Model '{m}' ({ton}) contaminated by forbidden valve role '{f_role}'!")
                    
            print(f"Model {m:16s} ({ton}): Suction={pri.get('part_no')} ({pri.get('role')}, Rs.{pri.get('price')}) | Liquid={alts[0].get('part_no')} ({alts[0].get('role')}, Rs.{alts[0].get('price')}) [OK]")

    record_pass("Valve Physical Pairings", "All AC tonnages (1.0T, 1.5T, 2.0T, 3.0T, 4.0T) strictly pair correct suction and liquid valves with 0% contamination.")

    # ==============================================================================
    # CHALLENGE SECTION 3: Cross-Series & Cross-Platform Contamination Stress Test
    # ==============================================================================
    print("\n[CHALLENGE 3] Cross-Series Platform Isolation Stress Test...")

    # 3.1 PITH vs CITH
    res_pith = fetch_tiered_compatible_parts("GS-18PITH11W")
    res_cith = fetch_tiered_compatible_parts("GS-18CITH12G")

    pith_evaps = [p['part_no'] for g in res_pith['role_groups'] if "Evaporator" in g['group_title'] for p in [g['primary']] + g['alternatives']]
    cith_evaps = [p['part_no'] for g in res_cith['role_groups'] if "Evaporator" in g['group_title'] for p in [g['primary']] + g['alternatives']]

    if "1002937LC" in pith_evaps:
        record_failure("Cross-Series PITH", "CITH evaporator 1002937LC leaked into PITH model!")
    if "11001060868" in cith_evaps:
        record_failure("Cross-Series CITH", "PITH evaporator 11001060868 leaked into CITH model!")
    record_pass("PITH vs CITH Isolation", "Clean separation: PITH (11001060868) and CITH (1002937LC) do not cross-contaminate.")

    # 3.2 ZITH Evaporator Assembly Prioritization
    res_zith = fetch_tiered_compatible_parts("GS-18ZITH1W-T3")
    z_evap_grp = next((g for g in res_zith['role_groups'] if "Evaporator" in g['group_title']), None)
    if not z_evap_grp:
        record_failure("ZITH Evaporator", "GS-18ZITH1W-T3 missing Evaporator group")
    else:
        if z_evap_grp['primary']['part_no'] != "11001062414":
            record_failure("ZITH Assembly Priority", f"Expected full assembly 11001062414 as primary, got {z_evap_grp['primary']['part_no']}")
        if z_evap_grp['primary']['price'] != 30000:
            record_failure("ZITH Assembly Price", f"Expected Rs. 30,000 for 11001062414, got {z_evap_grp['primary']['price']}")
        z_alts = [a['part_no'] for a in z_evap_grp['alternatives']]
        if "1000106068502" not in z_alts:
            record_failure("ZITH Sub-Assembly Alt", "Expected sub-assembly 1000106068502 in alternatives!")
        else:
            alt_item = next(a for a in z_evap_grp['alternatives'] if a['part_no'] == "1000106068502")
            if alt_item['price'] != 26000:
                record_failure("ZITH Sub-Assembly Price Floor", f"Expected floor price 26,000, got {alt_item['price']}")
    record_pass("ZITH Assembly Priority", "GS-18ZITH1W-T3 properly ranks full assembly 11001062414 (Rs. 30,000) above sub-assembly 1000106068502 (Rs. 26,000).")

    # 3.3 Floor Standing Series Isolation (GF-48FW vs GF-48TF vs GF-24ISH vs GF-24CB)
    fs_evap_map = {
        'GF-48FW': ('1004169', 70000),
        'GF-48TF': ('11001060521', 75000),
        'GF-24ISH': ('11001060092', 72000),
        'GF-24CB': ('100404401', 66000),
    }

    for fs_model, (exp_pno, exp_price) in fs_evap_map.items():
        res = fetch_tiered_compatible_parts(fs_model)
        grp = next((g for g in res['role_groups'] if "Evaporator" in g['group_title']), None)
        if not grp:
            record_failure(f"{fs_model} Evap", f"Missing Evaporator group for {fs_model}")
            continue
        pri = grp['primary']
        if pri['part_no'] != exp_pno:
            record_failure(f"{fs_model} Primary Evap", f"Expected {exp_pno}, got {pri['part_no']}")
        if pri['price'] != exp_price:
            record_failure(f"{fs_model} Evap Price", f"Expected Rs. {exp_price}, got Rs. {pri['price']}")
        print(f"Floor Standing {fs_model:10s} -> Primary Evaporator: {pri['part_no']} @ Rs. {pri['price']:,} [OK]")

    record_pass("Floor Standing Series Isolation", "All Floor Standing series (48FW, 48TF, 24ISH, 24CB) isolated to genuine components.")

    # ==============================================================================
    # CHALLENGE SECTION 4: Non-AC Category Isolation (Chassis Separation)
    # ==============================================================================
    print("\n[CHALLENGE 4] Non-AC Category Isolation (Chassis Separation)...")

    # 4.1 Refrigerator
    res_ref = fetch_tiered_compatible_parts("GR-E8768G-CP1")
    for g in res_ref['role_groups']:
        clean_title = clean_ascii(g['group_title'])
        if "Cut-off & Service Valves" in clean_title:
            record_failure("Ref AC Valve Contamination", f"Refrigerator returned valve group: {clean_title}")
        for p in [g['primary']] + g['alternatives']:
            if "7130239" in p['part_no'] or "7133774" in p['part_no'] or "7133844" in p['part_no']:
                record_failure("Ref AC Part Contamination", f"AC valve {p['part_no']} leaked into Refrigerator!")
    record_pass("Refrigerator Isolation", "Refrigerator GR-E8768G-CP1 has 0% AC valve leakage.")

    # 4.2 Washing Machine
    res_wm = fetch_tiered_compatible_parts("EW-F1202DC")
    for g in res_wm['role_groups']:
        clean_title = clean_ascii(g['group_title'])
        # Assert no AC refrigerant cut-off valves leak into Washing Machine
        for p in [g['primary']] + g['alternatives']:
            pno = p['part_no']
            if pno in ['7130239', '71302395', '7133774', '7133844']:
                record_failure("WM AC Valve Leakage", f"AC Refrigerant Valve {pno} leaked into Washing Machine!")
            if "Evaporator" in p.get('role', ''):
                record_failure("WM AC Evaporator Leakage", f"Evaporator {pno} leaked into Washing Machine!")
    record_pass("Washing Machine Isolation", "Washing Machine EW-F1202DC: 0% AC refrigerant valve or evaporator leakage.")

    # 4.3 Water Dispenser
    res_wd = fetch_tiered_compatible_parts("WD-E500")
    for g in res_wd['role_groups']:
        clean_title = clean_ascii(g['group_title'])
        for p in [g['primary']] + g['alternatives']:
            pno = p['part_no']
            if pno in ['7130239', '71302395', '7133774', '7133844']:
                record_failure("WD AC Valve Leakage", f"AC Refrigerant Valve {pno} leaked into Water Dispenser!")
    record_pass("Water Dispenser Isolation", "Water Dispenser WD-E500 has 0% AC valve leakage.")

    # ==============================================================================
    # CHALLENGE SECTION 5: Zero-Pricing Immunity & Packaging Carton Exclusion
    # ==============================================================================
    print("\n[CHALLENGE 5] Zero-Price Immunity & Non-Functional Carton Exclusion...")

    all_test_models = [
        "GS-12PITH11W", "GS-12CITH11W", "GS-18PITH11W", "GS-18CITH12G", "GS-18CITH13W",
        "GS-18ZITH1W-T3", "GS-24PITH11W", "GF-36TFIH", "GF-48TF", "GF-48FW",
        "GF-24ISH", "GF-24CB", "GR-E8768G-CP1", "EW-F1202DC", "WD-E500", "UNKNOWN_MODEL_TEST"
    ]

    total_audited_parts = 0
    zero_price_violations = []
    carton_leaks = []

    for m in all_test_models:
        res = fetch_tiered_compatible_parts(m)
        for g in res.get('role_groups', []):
            parts = [g['primary']] + g.get('alternatives', [])
            for p in parts:
                total_audited_parts += 1
                pr = p.get('price', 0)
                if pr <= 0:
                    zero_price_violations.append((m, p.get('part_no'), pr))
                # Check for cartons leaking into functional assemblies
                if "03010102510004" == p.get('part_no') and "Evaporator" in g.get('group_title', ''):
                    carton_leaks.append((m, p.get('part_no')))

    if zero_price_violations:
        record_failure("Zero-Price Immunity", f"Found {len(zero_price_violations)} zero-price parts across models: {zero_price_violations[:5]}")
    else:
        record_pass("Zero-Price Immunity", f"Audited {total_audited_parts} parts across {len(all_test_models)} models. 100% have price > Rs. 0.")

    if carton_leaks:
        record_failure("Carton Leakage", f"Packaging carton leaked into Evaporator Assemblies: {carton_leaks}")
    else:
        record_pass("Carton Exclusion", "Packaging cartons strictly excluded from cooling and functional roles.")

    # ==============================================================================
    # CHALLENGE SECTION 6: Hostile / Boundary Inputs & Global Search Robustness
    # ==============================================================================
    print("\n[CHALLENGE 6] Hostile / Boundary Inputs & Global Search Robustness...")

    hostile_searches = [
        "   7133844   ",
        "7130239",
        "71302395",
        "11001000602",
        "1/4\" valve",
        "5/8\" valve",
        "3/8\" valve",
        "1/2\" valve",
        "'; DROP TABLE stock_master; --",
        "%OR%1=1%",
        "",
        "   ",
        "NON_EXISTENT_PNO_XYZ"
    ]

    for q in hostile_searches:
        try:
            df = search_stock_global(q, limit=10)
            assert isinstance(df, pd.DataFrame), "Search must return DataFrame"
            if not df.empty:
                zeros = (df['price'] <= 0).sum()
                if zeros > 0:
                    record_failure("Search Zero Price", f"Query '{q}' returned {zeros} zero-price items")
        except Exception as e:
            record_failure("Search Crash", f"Query '{q}' crashed search_stock_global with: {e}")

    record_pass("Hostile Inputs Robustness", "Global search is resilient to whitespace, quotes, SQL patterns, and empty strings.")

    # ==============================================================================
    # FINAL VERDICT SYNTHESIS
    # ==============================================================================
    print("\n" + "=" * 80)
    print("FINAL CHALLENGE VERDICT:")
    if failures:
        print(f"VERDICT: REJECT - {len(failures)} EMPIRICAL CHALLENGE FAILURES DETECTED!")
        for cat, msg in failures:
            print(f"  [FAIL] [{cat}]: {msg}")
        print("=" * 80)
        assert False, f"Challenger 2 suite detected {len(failures)} failures"
    else:
        print("VERDICT: APPROVE - ALL EMPIRICAL ADVERSARIAL CHALLENGES PASSED (0 FAILURES)!")
        print("=" * 80)
        return True

if __name__ == "__main__":
    run_challenger_2_tests()
