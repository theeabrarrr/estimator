"""
Adversarial Empirical Stress Harness - Milestone 2 Challenger 2
=============================================================
This test harness stress-tests:
1. GF-36TFIH isolation, genuine components, and zero contamination
2. Boundary conditions: empty search query, invalid models, SQL injection strings, whitespace
3. Direct search fallbacks and price consistency (Stock Search vs Model Search)
4. Multi-tier isolation and contract validation across categories
5. Strict valve pairing and capacity constraint enforcement
6. Zero-price immunity and database ledger hygiene
"""

import sys
import sqlite3
import pandas as pd
from database import (
    fetch_tiered_compatible_parts, 
    search_stock_global, 
    get_stock_metadata, 
    get_connection,
    init_db_schema
)
from config import (
    tokenize_appliance_model,
    classify_component_role,
    get_tonnage_valve_pairing,
    is_valve_tonnage_compatible,
    BASELINE_JSON_PATH
)
import json

passed_count = 0
failed_count = 0

def check(condition, message):
    global passed_count, failed_count
    if condition:
        print(f"  [PASS] {message}")
        passed_count += 1
    else:
        print(f"  [FAIL] {message}")
        failed_count += 1
        raise AssertionError(message)

def test_gf36tfih_isolation():
    print("\n" + "="*70)
    print("CHALLENGE 1: GF-36TFIH Multi-Tier Output, Genuine Parts & Zero Contamination")
    print("="*70)
    
    res = fetch_tiered_compatible_parts("GF-36TFIH")
    
    # Verify metadata
    tok = res.get('metadata', {})
    check(tok.get('category') == "Floor Standing AC", f"Category is Floor Standing AC (got {tok.get('category')})")
    check(tok.get('tonnage') == "3.0 Ton", f"Tonnage is 3.0 Ton (got {tok.get('tonnage')})")
    check(tok.get('series') == "TFIH", f"Series is TFIH (got {tok.get('series')})")
    
    # 1. Evaporator verification
    evap_group = next((g for g in res['role_groups'] if "Evaporator" in g['group_title']), None)
    check(evap_group is not None, "GF-36TFIH has Evaporator group")
    primary_evap = evap_group['primary']
    check(primary_evap['part_no'] == "11001000602", f"GF-36TFIH primary evaporator is 11001000602 (got {primary_evap['part_no']})")
    check(primary_evap['price'] == 58000, f"GF-36TFIH evaporator price is Rs. 58,000 (got {primary_evap['price']})")
    
    # Contamination check on Evaporator role
    all_evap_pnos = [g['part_no'] for g in [evap_group['primary']] + evap_group['alternatives']]
    forbidden_evaps = [
        "11001060092", # 2.0 Ton 24ISH
        "1004169",     # 4.0 Ton 48FW
        "11001060246", # 4.0 Ton 48FWITH
        "11001060868", # 1.5 Ton PITH
        "1002937LC",   # 1.5 Ton CITH
        "11001062414", # 1.5 Ton AITH/ZITH
        "11001060869"  # 1.0 Ton PITH
    ]
    for fe in forbidden_evaps:
        check(fe not in all_evap_pnos, f"Forbidden evaporator {fe} NOT present in GF-36TFIH evaporator group")
    
    # Check that in ALL tiers, no leaked incompatible evaporators exist
    all_parts = res['compatible_parts']
    for p in all_parts:
        if p.get('role') == 'Evaporator Assembly':
            check(p['part_no'] == '11001000602', f"Only genuine evaporator 11001000602 allowed, found {p['part_no']}")

    # 2. Valve verification
    valve_group = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    check(valve_group is not None, "GF-36TFIH has Cut-off & Service Valves group")
    
    primary_valve = valve_group['primary']
    check(primary_valve['part_no'] == "7133844", f"Primary valve is 5/8\" valve 7133844 (got {primary_valve['part_no']})")
    check(primary_valve['role'] == "Cut-Off Valve (5/8\")", f"Primary valve role is Cut-Off Valve (5/8\") (got {primary_valve['role']})")
    check(primary_valve['price'] == 2200, f"Primary valve price is Rs. 2,200 (got {primary_valve['price']})")
    check("24LITH11M" in primary_valve['part_name'], f"Primary valve description matches closed complaint ground truth: {primary_valve['part_name']}")
    
    check(len(valve_group['alternatives']) >= 1, "GF-36TFIH has secondary valve")
    sec_valve = valve_group['alternatives'][0]
    check(sec_valve['part_no'] == "7130239", f"Alternative valve is 1/4\" valve 7130239 (got {sec_valve['part_no']})")
    check(sec_valve['role'] == "Cut-Off Valve (1/4\")", f"Alternative valve role is Cut-Off Valve (1/4\") (got {sec_valve['role']})")
    check(sec_valve['price'] == 1600, f"Alternative valve price is Rs. 1,600 (got {sec_valve['price']})")
    check("GS-11CITH3F" in sec_valve['part_name'], f"Alternative valve description matches closed complaint ground truth: {sec_valve['part_name']}")
    
    # Assert zero clutter of unrelated valve sizes in valve group
    total_valves = [valve_group['primary']] + valve_group['alternatives']
    check(len(total_valves) == 2, f"GF-36TFIH displays exactly 2 valves (5/8\" and 1/4\"), got {len(total_valves)}")
    for v in total_valves:
        check(v['role'] in ["Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")"], f"Valve role {v['role']} is valid for 3.0 Ton")
        check(v['role'] not in ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"], f"Valve role {v['role']} is NOT leaked into 3.0 Ton")

    # Check all valves in compatible_parts
    for p in all_parts:
        if 'valve' in p.get('part_name', '').lower() and 'cut' in p.get('part_name', '').lower():
            check(p['part_no'] in ['7133844', '7130239'], f"All cut-off valves for GF-36TFIH must be 7133844 or 7130239 (found {p['part_no']})")

    # Assert zero packaging cartons/foam/trays in cooling/electrical roles
    for p in all_parts:
        nl = (str(p.get('part_name', '')) + " " + str(p.get('part_no', ''))).lower()
        if any(k in nl for k in ['carton', 'caton', 'packing', 'tray', 'box']):
            check(p.get('role') == 'Component Hardware', f"Packaging item {p['part_name']} must be classified as Component Hardware, got {p.get('role')}")

def test_boundary_conditions():
    print("\n" + "="*70)
    print("CHALLENGE 2: Boundary Conditions & Edge Cases")
    print("="*70)
    
    # 2.1 Empty search query in fetch_tiered_compatible_parts
    print("\n--- Subtest 2.1: Empty Search Query in fetch_tiered_compatible_parts ---")
    res_empty_1 = fetch_tiered_compatible_parts("GF-36TFIH", search_query="")
    check(len(res_empty_1['tier1']) > 0, "Empty query '' returns full tier1 parts")
    res_empty_2 = fetch_tiered_compatible_parts("GF-36TFIH", search_query="   ")
    check(len(res_empty_2['tier1']) == len(res_empty_1['tier1']), "Whitespace query '   ' handled identically to empty query")

    # 2.2 Filtered search query in fetch_tiered_compatible_parts
    print("\n--- Subtest 2.2: Specific Search Queries in fetch_tiered_compatible_parts ---")
    res_evap = fetch_tiered_compatible_parts("GF-36TFIH", search_query="11001000602")
    check(len(res_evap['compatible_parts']) >= 1, "Search by exact part_no '11001000602' finds evaporator")
    check(all('11001000602' in p['part_no'] for p in res_evap['compatible_parts']), "All returned parts match '11001000602'")

    res_valve = fetch_tiered_compatible_parts("GF-36TFIH", search_query="Valve")
    check(len(res_valve['compatible_parts']) >= 1, "Search by 'Valve' finds valve components")
    check(all('VALVE' in (p['part_name'] + p['role']).upper() for p in res_valve['compatible_parts']), "All returned parts match 'Valve'")

    res_none = fetch_tiered_compatible_parts("GF-36TFIH", search_query="NONEXISTENT_PART_XYZ_99999")
    check(len(res_none['compatible_parts']) == 0, "Nonexistent query returns 0 parts gracefully")
    check(len(res_none['role_groups']) == 0, "Nonexistent query returns 0 role groups gracefully")

    # 2.3 Invalid, Empty, and Malformed Models
    print("\n--- Subtest 2.3: Invalid and Adversarial Models ---")
    adversarial_models = [
        "",
        "   ",
        "UNKNOWN-MODEL-XYZ",
        "INVALID-999-ABC",
        "SELECT * FROM stock_master",
        "'; DROP TABLE stock_master; --",
        "<script>alert(1)</script>",
        "12345",
        "---",
        "GS-",
        "GF-"
    ]
    for m in adversarial_models:
        try:
            res_adv = fetch_tiered_compatible_parts(m)
            check('tier1' in res_adv, f"Model '{m}' returns 'tier1' key")
            check('tier2' in res_adv, f"Model '{m}' returns 'tier2' key")
            check('tier3' in res_adv, f"Model '{m}' returns 'tier3' key")
            check('metadata' in res_adv, f"Model '{m}' returns 'metadata' key")
            check('role_groups' in res_adv, f"Model '{m}' returns 'role_groups' key")
            # Verify zero-price immunity on any parts returned
            for p in res_adv['compatible_parts']:
                check(p.get('price', 0) > 0, f"Model '{m}' part {p.get('part_no')} has price > 0 (got {p.get('price')})")
        except Exception as e:
            check(False, f"Model '{m}' caused unhandled exception: {str(e)}")

    # 2.4 Boundary conditions for search_stock_global
    print("\n--- Subtest 2.4: search_stock_global Boundary Conditions ---")
    df_empty = search_stock_global("")
    check(not df_empty.empty, "search_stock_global('') returns non-empty default stock list")
    check(all(df_empty['price'] > 0), "All prices in search_stock_global('') are > 0")

    df_ws = search_stock_global("    ")
    check(not df_ws.empty, "search_stock_global('   ') returns non-empty default stock list")
    check(all(df_ws['price'] > 0), "All prices in search_stock_global('   ') are > 0")

    df_sql = search_stock_global("' OR '1'='1")
    check(isinstance(df_sql, pd.DataFrame), "SQL injection query returns a valid DataFrame without error")

    df_fake = search_stock_global("TOTALLY_BOGUS_PART_NAME_NEVER_EXISTS_99999")
    check(df_fake.empty, "Bogus query returns empty DataFrame without error")

def test_direct_search_fallbacks():
    print("\n" + "="*70)
    print("CHALLENGE 3: Direct Search Fallbacks & Official Price Consistency")
    print("="*70)
    
    target_parts = [
        ("11001000602", 58000, "GF-36TFIH Evaporator"),
        ("7133844",     2200,  "5/8\" Suction Valve"),
        ("7130239",     1600,  "1/4\" Liquid Valve"),
        ("71302395",    1500,  "3/8\" Valve 1.0 Ton"),
        ("7133774",     2100,  "1/2\" Valve 1.5 Ton"),
        ("11001060868", 26000, "GS-18PITH11W Evaporator"),
        ("11001062414", 30000, "GS-18AITH23W-T3 Evaporator"),
        ("1004169",     70000, "GF-48FW Evaporator"),
        ("11001060092", 72000, "GF-24ISH Evaporator"),
        ("1000106068502", 26000, "Floor Protected Evaporator")
    ]
    
    for pno, exp_price, desc in target_parts:
        df = search_stock_global(pno)
        check(not df.empty, f"Direct stock search for {pno} ({desc}) returns result")
        match_row = df[df['part_no'].str.upper() == pno.upper()]
        check(not match_row.empty, f"Exact part {pno} found in direct stock search")
        actual_price = int(match_row.iloc[0]['price'])
        check(actual_price == exp_price, f"Direct search {pno} ({desc}) price is Rs. {exp_price:,} (got Rs. {actual_price:,})")

def test_multi_tier_cross_category_isolation():
    print("\n" + "="*70)
    print("CHALLENGE 4: Multi-Tier Structure & Cross-Category Isolation")
    print("="*70)
    
    models_to_test = [
        ("GS-18PITH11W", "Split AC", "1.5 Ton", ("Cut-Off Valve (1/2\")", "Cut-Off Valve (1/4\")")),
        ("GS-12PITH11W", "Split AC", "1.0 Ton", ("Cut-Off Valve (3/8\")", "Cut-Off Valve (1/4\")")),
        ("GS-24PITH11W", "Split AC", "2.0 Ton", ("Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")")),
        ("GF-36TFIH",    "Floor Standing AC", "3.0 Ton", ("Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")")),
        ("GF-48FW",      "Floor Standing AC", "4.0 Ton", ("Cut-Off Valve (5/8\")", "Cut-Off Valve (3/8\")")),
        ("GR-E8768G-CP1", "Refrigerator", "Domestic Ref", None),
        ("EW-F1202DC",   "Washing Machine", "Standard Unit", None),
        ("WD-E500",      "Water Dispenser", "Dispenser", None)
    ]
    
    for model_name, expected_cat, expected_ton, expected_valves in models_to_test:
        res = fetch_tiered_compatible_parts(model_name)
        check(res['metadata']['category'] == expected_cat, f"{model_name} category is {expected_cat}")
        check(res['metadata']['tonnage'] == expected_ton, f"{model_name} tonnage is {expected_ton}")
        
        # Verify 3-tier partitioning
        check(isinstance(res['tier1'], list), f"{model_name} tier1 is a list")
        check(isinstance(res['tier2'], list), f"{model_name} tier2 is a list")
        check(isinstance(res['tier3'], list), f"{model_name} tier3 is a list")
        
        # All tier 1 must have tier_code == 1
        for p in res['tier1']:
            check(p.get('tier_code') == 1, f"{model_name} tier1 item has tier_code 1")
        # All tier 2 must have tier_code == 2
        for p in res['tier2']:
            check(p.get('tier_code') == 2, f"{model_name} tier2 item has tier_code 2")
        # All tier 3 must have tier_code == 3 and in_stock == True
        for p in res['tier3']:
            check(p.get('tier_code') == 3, f"{model_name} tier3 item has tier_code 3")
            check(p.get('in_stock') is True, f"{model_name} tier3 item is in_stock")

        # Valve checks
        if expected_valves:
            vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
            check(vg is not None, f"{model_name} has valve group")
            exp_suction, exp_liquid = expected_valves
            check(vg['primary']['role'] == exp_suction, f"{model_name} primary valve is {exp_suction} (got {vg['primary']['role']})")
            if len(vg['alternatives']) > 0:
                check(vg['alternatives'][0]['role'] == exp_liquid, f"{model_name} secondary valve is {exp_liquid} (got {vg['alternatives'][0]['role']})")
        else:
            # Non-AC models MUST NOT have cut-off valve groups or AC evaporators
            vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
            check(vg is None, f"{model_name} ({expected_cat}) has ZERO Cut-off & Service Valves")
            for p in res['compatible_parts']:
                p_name_lower = p['part_name'].lower()
                check('cut-off' not in p_name_lower and 'cutt off' not in p_name_lower, f"{model_name} ({expected_cat}) has NO cut-off valve leaked ({p['part_name']})")
                if expected_cat != "Refrigerator":
                    check(p.get('role') != 'Evaporator Assembly', f"{model_name} ({expected_cat}) has NO Evaporator Assembly leaked ({p['part_name']})")

def test_database_hygiene_and_zero_price_immunity():
    print("\n" + "="*70)
    print("CHALLENGE 5: Database Ledger Hygiene & Zero-Price Immunity")
    print("="*70)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check stock_master total rows
        cursor.execute("SELECT count(*) FROM stock_master")
        total_stock = cursor.fetchone()[0]
        check(total_stock >= 518, f"stock_master has at least 518 rows (got {total_stock})")
        
        # Check ledger amount formula elimination
        cursor.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND abs(amount - (unit_price * bal_qty)) > 0.01")
        discrepancy_count = cursor.fetchone()[0]
        check(discrepancy_count == 0, f"Obsolete ledger amount discrepancies in stock_master: {discrepancy_count} (must be 0)")
        
        # Check zero-price in stock_master
        cursor.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0")
        zero_price_stock = cursor.fetchone()[0]
        check(zero_price_stock == 0, f"Zero-price items in stock_master: {zero_price_stock} (must be 0)")

        # Check parts_master rows
        cursor.execute("SELECT count(*) FROM parts_master")
        total_parts = cursor.fetchone()[0]
        check(total_parts > 5000, f"parts_master has comprehensive records (got {total_parts})")
        
        # Check zero-price in parts_master
        cursor.execute("SELECT count(*) FROM parts_master WHERE price <= 0")
        zero_price_parts = cursor.fetchone()[0]
        check(zero_price_parts == 0, f"Zero-price items in parts_master: {zero_price_parts} (must be 0)")

    # Audit ground_truth_baseline.json
    with open(BASELINE_JSON_PATH, "r", encoding="utf-8") as f:
        baseline = json.load(f)
        
    price_book = baseline.get('price_book', {})
    check(len(price_book) >= 518, f"ground_truth_baseline.json price_book has >= 518 parts (got {len(price_book)})")
    zero_price_baseline = sum(1 for pno, d in price_book.items() if d.get('price', 0) <= 0)
    check(zero_price_baseline == 0, f"Zero-price items in baseline price_book: {zero_price_baseline} (must be 0)")

if __name__ == "__main__":
    print("STARTING M2 CHALLENGER 2 ADVERSARIAL STRESS TEST SUITE...")
    try:
        test_gf36tfih_isolation()
        test_boundary_conditions()
        test_direct_search_fallbacks()
        test_multi_tier_cross_category_isolation()
        test_database_hygiene_and_zero_price_immunity()
        
        print("\n" + "="*70)
        print(f"ADVERSARIAL STRESS TESTS COMPLETED: {passed_count} PASSED, {failed_count} FAILED")
        print("VERDICT: APPROVE")
        print("="*70)
        sys.exit(0)
    except AssertionError as ae:
        print("\n" + "="*70)
        print(f"ADVERSARIAL STRESS TEST FAILED: {ae}")
        print(f"RESULTS: {passed_count} PASSED, {failed_count} FAILED")
        print("VERDICT: REJECT")
        print("="*70)
        sys.exit(1)
    except Exception as e:
        print("\n" + "="*70)
        print(f"UNEXPECTED ERROR: {e}")
        print("VERDICT: REJECT")
        print("="*70)
        sys.exit(2)
