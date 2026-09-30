import os
import sys
import pandas as pd

# Test runner for DWP Service Field Assistant
from config import tokenize_appliance_model, get_tonnage_specs
from database import fetch_tiered_compatible_parts, search_stock_global, get_stock_metadata
from etl import bootstrap_master_data

def run_tests():
    print("=" * 60)
    print("RUNNING SYSTEM UPGRADE VERIFICATION SUITE")
    print("=" * 60)

    # 1. Bootstrap & Metadata Check
    print("\n[TEST 1] Testing Database Bootstrap & Stock Metadata...")
    bootstrap_master_data()
    meta = get_stock_metadata()
    print(f"Stock Metadata: Total Items={meta['total_items']}, In-Stock={meta['in_stock_items']}, Synced={meta['last_synced']}")
    assert meta['total_items'] > 0, "Stock items should be > 0"
    print(">>> PASS: Bootstrap & Stock Metadata active.")

    # 2. Strict Model Tokenizer & Capacity Test
    print("\n[TEST 2] Testing Strict Model Tokenizer...")
    tok_pith = tokenize_appliance_model("GS-18PITH11W")
    assert tok_pith['tonnage'] == "1.5 Ton", f"Expected 1.5 Ton, got {tok_pith['tonnage']}"
    assert tok_pith['series'] == "PITH", f"Expected PITH series, got {tok_pith['series']}"

    tok_cith = tokenize_appliance_model("GS-18CITH12G")
    assert tok_cith['tonnage'] == "1.5 Ton", f"Expected 1.5 Ton, got {tok_cith['tonnage']}"
    assert tok_cith['series'] == "CITH", f"Expected CITH series, got {tok_cith['series']}"

    tok_ref = tokenize_appliance_model("GR-E8768G-CP1")
    assert tok_ref['category'] == "Refrigerator", f"Expected Refrigerator, got {tok_ref['category']}"

    tok_wm = tokenize_appliance_model("EW-F1202DC")
    assert tok_wm['category'] == "Washing Machine", f"Expected Washing Machine, got {tok_wm['category']}"
    print(">>> PASS: Strict Tokenizer properly parses tonnages, platforms, and categories.")

    # 3. Cross-Series Isolation & Evaporator Matching Test
    print("\n[TEST 3] Testing Cross-Series Isolation (PITH vs CITH)...")
    res_pith = fetch_tiered_compatible_parts("GS-18PITH11W")
    pith_pnos = []
    for g in res_pith['role_groups']:
        pith_pnos.append(g['primary']['part_no'])
        for a in g['alternatives']:
            pith_pnos.append(a['part_no'])

    # GS-18PITH11W primary evaporator must be 11001060868 (Rs. 26,000)
    evap_grp = next((g for g in res_pith['role_groups'] if "Evaporator" in g['group_title']), None)
    assert evap_grp is not None, "GS-18PITH11W must have an Evaporator group"
    assert evap_grp['primary']['part_no'] == "11001060868", f"Expected 11001060868 as primary, got {evap_grp['primary']['part_no']}"
    assert evap_grp['primary']['price'] == 26000, f"Expected Rs. 26,000 for 11001060868, got {evap_grp['primary']['price']}"
    assert "1002937LC" not in pith_pnos, "CRITICAL ERROR: CITH part 1002937LC leaked into GS-18PITH11W!"
    print(f"GS-18PITH11W Primary Evaporator: {evap_grp['primary']['part_no']} (Score: {evap_grp['primary']['score']}, Jobs: {evap_grp['primary']['verified_jobs']}, Price: Rs. {evap_grp['primary']['price']:,})")
    print(f"GS-18PITH11W Alternatives: {[a['part_no'] for a in evap_grp['alternatives']]}")

    # GS-18CITH12G must NOT have 11001060868
    res_cith = fetch_tiered_compatible_parts("GS-18CITH12G")
    cith_pnos = []
    for g in res_cith['role_groups']:
        cith_pnos.append(g['primary']['part_no'])
        for a in g['alternatives']:
            cith_pnos.append(a['part_no'])

    assert "11001060868" not in cith_pnos, "CRITICAL ERROR: PITH part 11001060868 leaked into GS-18CITH12G!"
    cith_evap = next((g for g in res_cith['role_groups'] if "Evaporator" in g['group_title']), None)
    assert cith_evap is not None, "GS-18CITH12G must have an Evaporator group"
    assert cith_evap['primary']['part_no'] == "1002937LC", f"Expected 1002937LC, got {cith_evap['primary']['part_no']}"
    assert cith_evap['primary']['price'] == 26000, f"Expected Rs. 26,000 for 1002937LC, got {cith_evap['primary']['price']}"
    print(f"GS-18CITH12G Primary Evaporator: {cith_evap['primary']['part_no']} (Price: Rs. {cith_evap['primary']['price']:,})")
    print(">>> PASS: Cross-Series Isolation strictly validated. Zero cross-contamination.")

    # 4. Zero-Pricing Verification
    print("\n[TEST 4] Testing Zero-Price Immunity on diverse models...")
    test_models = [
        "GS-18PITH11W", "GS-18CITH12G", "GS-12PITH11W", "GS-24PITH11W",
        "GR-E8768G-CP1", "EW-F1202DC", "GF-48TF"
    ]
    zero_price_found = False
    total_parts_checked = 0
    for m in test_models:
        res = fetch_tiered_compatible_parts(m)
        for g in res['role_groups']:
            parts_to_check = [g['primary']] + g['alternatives']
            for p in parts_to_check:
                total_parts_checked += 1
                pr = p.get('price', 0)
                if pr <= 0:
                    print(f"FAIL: Part {p['part_no']} ({p['part_name']}) in model {m} has price {pr}!")
                    zero_price_found = True

    assert not zero_price_found, "Zero price found in compatible parts!"
    print(f">>> PASS: Verified {total_parts_checked} parts across {len(test_models)} models. All prices > Rs. 0.")

    # 5. Global Stock Search Verification
    print("\n[TEST 5] Testing Global Stock Search...")
    search_queries = ["Evaporator", "PCB", "Valve", "Sensor", "Motor"]
    for q in search_queries:
        res_df = search_stock_global(q, limit=10)
        assert not res_df.empty, f"Search for '{q}' returned no results!"
        assert (res_df['price'] > 0).all(), f"Search for '{q}' returned items with zero price!"
        print(f"Search '{q}': {len(res_df)} items found, all with prices > 0.")
    print(">>> PASS: Global search returns accurate results with verified prices.")

    # 6. GS-18ZITH1W-T3 Evaporator Verification
    print("\n[TEST 6] Testing GS-18ZITH1W-T3 Evaporator & Parts...")
    tok_zith = tokenize_appliance_model("GS-18ZITH1W-T3")
    assert tok_zith['series'] == "ZITH", f"Expected ZITH series, got {tok_zith['series']}"
    res_zith = fetch_tiered_compatible_parts("GS-18ZITH1W-T3")
    zith_evap_grp = next((g for g in res_zith['role_groups'] if "Evaporator" in g['group_title']), None)
    assert zith_evap_grp is not None, "GS-18ZITH1W-T3 must have an Evaporator group!"
    zith_primary_pno = zith_evap_grp['primary']['part_no']
    print(f"GS-18ZITH1W-T3 Primary Evaporator: {zith_primary_pno} ({zith_evap_grp['primary']['part_name']}) Stock={zith_evap_grp['primary']['bal_qty']}")
    assert zith_primary_pno == "11001062414", f"Expected 11001062414 as primary, got {zith_primary_pno}"
    assert "1000106068502" in [a['part_no'] for a in zith_evap_grp['alternatives']], "1000106068502 should be in alternatives!"
    print(">>> PASS: GS-18ZITH1W-T3 has primary in-stock Evaporator and alternate revision.")

    # 7. Overheads Verification (Visit=600, Mobility=2000, Ref Gas=4000, Dispenser Gas=3500)
    print("\n[TEST 7] Testing Standard Overheads & Gas Pricing...")
    from config import CATEGORY_OVERHEADS
    for cat_name, ov in CATEGORY_OVERHEADS.items():
        assert ov['visit'] == 600, f"Visit charges for {cat_name} must be 600, got {ov['visit']}"
        assert ov['mobility'] == 2000, f"Mobility charges for {cat_name} must be 2000, got {ov['mobility']}"
    assert CATEGORY_OVERHEADS['Refrigerator']['gas_default'] == 4000, "Ref gas default must be 4000"
    assert CATEGORY_OVERHEADS['Water Dispenser']['gas_default'] == 3500, "Water dispenser gas default must be 3500"
    _, ref_gas, _, _, _ = get_tonnage_specs("GR-E8768G-CP1")
    assert ref_gas == 4000, f"Ref gas must be 4000, got {ref_gas}"
    _, wd_gas, _, _, _ = get_tonnage_specs("WD-E500")
    assert wd_gas == 3500, f"WD gas must be 3500, got {wd_gas}"
    print(">>> PASS: All categories have Mobility=Rs. 2,000, Visit=Rs. 600, Ref Gas=Rs. 4,000, Dispenser Gas=Rs. 3,500.")

    # 8. Price Consistency Test: Direct Part Search vs Model Search
    print("\n[TEST 8] Testing Price Consistency (Direct vs Model Search)...")
    zith_model_evap = zith_evap_grp['primary']
    assert zith_model_evap['price'] == 30000, f"Expected Model Search price 30,000, got {zith_model_evap['price']}"
    
    stk_zith_df = search_stock_global("11001062414")
    assert not stk_zith_df.empty, "Direct search for 11001062414 must return record"
    direct_zith_price = int(stk_zith_df.iloc[0]['price'])
    assert direct_zith_price == 30000, f"Expected Direct Search price 30,000, got {direct_zith_price}"
    assert zith_model_evap['price'] == direct_zith_price, f"DISCREPANCY DETECTED: Model {zith_model_evap['price']} vs Direct {direct_zith_price}"
    print(f">>> PASS: 100% Price Consistency: Part 11001062414 is Rs. {direct_zith_price:,} in BOTH Model & Direct Search.")

    # 9. Packaging Carton Exclusion & Evaporator Price Floor Test
    print("\n[TEST 9] Testing Packaging Carton Exclusion & Role Floor Protection...")
    res_cith13 = fetch_tiered_compatible_parts("GS-18CITH13W")
    cith13_evap_grp = next((g for g in res_cith13['role_groups'] if "Evaporator" in g['group_title']), None)
    assert cith13_evap_grp is not None, "GS-18CITH13W must have Evaporator group"
    cith13_evap_pnos = [cith13_evap_grp['primary']['part_no']] + [a['part_no'] for a in cith13_evap_grp['alternatives']]
    assert "03010102510004" not in cith13_evap_pnos, "CRITICAL ERROR: Packing carton 03010102510004 leaked into Evaporator Assemblies!"
    
    # Check alternate evaporator 1000106068502 floor protection
    zith_alt = next((a for a in zith_evap_grp['alternatives'] if a['part_no'] == "1000106068502"), None)
    assert zith_alt is not None, "Alternate evaporator 1000106068502 must exist"
    assert zith_alt['price'] == 26000, f"Expected floor price 26,000, got {zith_alt['price']}"
    print(f">>> PASS: Packing carton excluded. Alternate Evaporator 1000106068502 protected with floor price Rs. {zith_alt['price']:,}.")

    # 10. Strict Service Valve Tonnage Isolation & Dual Pairing Test
    print("\n[TEST 10] Testing Strict Service Valve Tonnage Isolation & Dual Pairing...")
    
    # 1.0 Ton Models (1/4" liquid + 3/8" suction)
    for m in ["GS-12PITH11W", "GS-12CITH11W"]:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['role'] == "Cut-Off Valve (3/8\")", f"{m} Primary valve must be 3/8\" suction, got {vg['primary']['role']}"
        assert vg['primary']['part_no'] == "71302395", f"{m} Primary valve part_no must be 71302395, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 1500, f"{m} Primary valve price must be 1500, got {vg['primary']['price']}"
        assert len(vg['alternatives']) == 1, f"{m} must have exactly 1 alternative valve, got {len(vg['alternatives'])}"
        assert vg['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")", f"{m} Alt valve must be 1/4\" liquid, got {vg['alternatives'][0]['role']}"
        assert vg['alternatives'][0]['part_no'] == "7130239", f"{m} Alt valve part_no must be 7130239, got {vg['alternatives'][0]['part_no']}"
        assert vg['alternatives'][0]['price'] == 1600, f"{m} Alt valve price must be 1600, got {vg['alternatives'][0]['price']}"
        all_roles = [vg['primary']['role']] + [a['role'] for a in vg['alternatives']]
        assert "Cut-Off Valve (1/2\")" not in all_roles, f"{m} must NOT contain 1/2\" valve!"
        assert "Cut-Off Valve (5/8\")" not in all_roles, f"{m} must NOT contain 5/8\" valve!"
    print(">>> PASS: 1.0 Ton models strictly paired with 3/8\" Suction + 1/4\" Liquid valves (0% leakage of 1/2\" & 5/8\").")

    # 1.5 Ton Models (1/4" liquid + 1/2" suction) including GS-18ZITH1W-T3
    for m in ["GS-18ZITH1W-T3", "GS-18PITH11W", "GS-18CITH12G"]:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['role'] == "Cut-Off Valve (1/2\")", f"{m} Primary valve must be 1/2\" suction, got {vg['primary']['role']}"
        assert vg['primary']['part_no'] == "7133774", f"{m} Primary valve part_no must be 7133774, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 2100, f"{m} Primary valve price must be 2100, got {vg['primary']['price']}"
        assert len(vg['alternatives']) == 1, f"{m} must have exactly 1 alternative valve, got {len(vg['alternatives'])}"
        assert vg['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")", f"{m} Alt valve must be 1/4\" liquid, got {vg['alternatives'][0]['role']}"
        assert vg['alternatives'][0]['part_no'] == "7130239", f"{m} Alt valve part_no must be 7130239, got {vg['alternatives'][0]['part_no']}"
        assert vg['alternatives'][0]['price'] == 1600, f"{m} Alt valve price must be 1600, got {vg['alternatives'][0]['price']}"
        all_roles = [vg['primary']['role']] + [a['role'] for a in vg['alternatives']]
        assert "Cut-Off Valve (3/8\")" not in all_roles, f"{m} must NOT contain 3/8\" valve!"
        assert "Cut-Off Valve (5/8\")" not in all_roles, f"{m} must NOT contain 5/8\" valve!"
        if m == "GS-18ZITH1W-T3":
            assert vg['primary']['in_stock'] is True, "GS-18ZITH1W-T3 primary 1/2\" valve must be IN STOCK"
            assert vg['alternatives'][0]['in_stock'] is True, "GS-18ZITH1W-T3 alt 1/4\" valve must be IN STOCK"
            assert vg['primary']['price'] > 0, "GS-18ZITH1W-T3 primary valve price must be > 0"
            assert vg['alternatives'][0]['price'] > 0, "GS-18ZITH1W-T3 alt valve price must be > 0"
    print(">>> PASS: 1.5 Ton models (including GS-18ZITH1W-T3) strictly paired with 1/2\" Suction + 1/4\" Liquid valves (0% leakage of 3/8\" & 5/8\").")

    # 2.0 Ton Models (1/4" liquid + 5/8" suction)
    for m in ["GS-24PITH11W", "GS-24CITH1"]:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['role'] == "Cut-Off Valve (5/8\")", f"{m} Primary valve must be 5/8\" suction, got {vg['primary']['role']}"
        assert vg['primary']['part_no'] == "7133844", f"{m} Primary valve part_no must be 7133844, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 2200, f"{m} Primary valve price must be 2200, got {vg['primary']['price']}"
        assert len(vg['alternatives']) == 1, f"{m} must have exactly 1 alternative valve, got {len(vg['alternatives'])}"
        assert vg['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")", f"{m} Alt valve must be 1/4\" liquid, got {vg['alternatives'][0]['role']}"
        assert vg['alternatives'][0]['part_no'] == "7130239", f"{m} Alt valve part_no must be 7130239, got {vg['alternatives'][0]['part_no']}"
        assert vg['alternatives'][0]['price'] == 1600, f"{m} Alt valve price must be 1600, got {vg['alternatives'][0]['price']}"
        all_roles = [vg['primary']['role']] + [a['role'] for a in vg['alternatives']]
        assert "Cut-Off Valve (3/8\")" not in all_roles, f"{m} must NOT contain 3/8\" valve!"
        assert "Cut-Off Valve (1/2\")" not in all_roles, f"{m} must NOT contain 1/2\" valve!"
    print(">>> PASS: 2.0 Ton models strictly paired with 5/8\" Suction + 1/4\" Liquid valves (0% leakage of 3/8\" & 1/2\").")

    # 4.0 Ton Models (3/8" liquid + 5/8" suction)
    for m in ["GF-48TF", "GF-48FW"]:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['role'] == "Cut-Off Valve (5/8\")", f"{m} Primary valve must be 5/8\" suction, got {vg['primary']['role']}"
        assert vg['primary']['part_no'] == "7133844", f"{m} Primary valve part_no must be 7133844, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 2200, f"{m} Primary valve price must be 2200, got {vg['primary']['price']}"
        assert len(vg['alternatives']) == 1, f"{m} must have exactly 1 alternative valve, got {len(vg['alternatives'])}"
        assert vg['alternatives'][0]['role'] == "Cut-Off Valve (3/8\")", f"{m} Alt valve must be 3/8\" liquid, got {vg['alternatives'][0]['role']}"
        assert vg['alternatives'][0]['part_no'] == "71302395", f"{m} Alt valve part_no must be 71302395, got {vg['alternatives'][0]['part_no']}"
        assert vg['alternatives'][0]['price'] == 1500, f"{m} Alt valve price must be 1500, got {vg['alternatives'][0]['price']}"
        all_roles = [vg['primary']['role']] + [a['role'] for a in vg['alternatives']]
        assert "Cut-Off Valve (1/4\")" not in all_roles, f"{m} must NOT contain 1/4\" valve!"
        assert "Cut-Off Valve (1/2\")" not in all_roles, f"{m} must NOT contain 1/2\" valve!"
    print(">>> PASS: 4.0 Ton models strictly paired with 5/8\" Suction + 3/8\" Liquid valves (0% leakage of 1/4\" & 1/2\").")

    # 11. Floor Standing AC Isolation & Genuine Evaporator Protection
    print("\n[TEST 11] Testing Floor Standing AC Isolation & Genuine Evaporator Protection...")
    tok_36 = tokenize_appliance_model("GF-36TFIH")
    assert tok_36['category'] == "Floor Standing AC", f"Expected Floor Standing AC, got {tok_36['category']}"
    assert tok_36['tonnage'] == "3.0 Ton", f"Expected 3.0 Ton, got {tok_36['tonnage']}"
    assert tok_36['series'] == "TFIH", f"Expected TFIH series, got {tok_36['series']}"

    res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
    evap_36 = next((g for g in res_36['role_groups'] if "Evaporator" in g['group_title']), None)
    assert evap_36 is not None, "GF-36TFIH must have Evaporator group"
    assert evap_36['primary']['part_no'] == "11001000602", f"Expected primary evaporator 11001000602, got {evap_36['primary']['part_no']}"
    assert evap_36['primary']['price'] == 58000, f"Expected verified price 58,000, got {evap_36['primary']['price']}"

    all_36_evap_pnos = [evap_36['primary']['part_no']] + [a['part_no'] for a in evap_36['alternatives']]
    assert "11001060092" not in all_36_evap_pnos, "CRITICAL ERROR: 2.0 Ton 24ISH (11001060092) leaked into GF-36TFIH!"
    assert "1004169" not in all_36_evap_pnos, "CRITICAL ERROR: 4.0 Ton 48FW (1004169) leaked into GF-36TFIH!"
    assert "11001060246" not in all_36_evap_pnos, "CRITICAL ERROR: 4.0 Ton 48FWITH (11001060246) leaked into GF-36TFIH!"

    # 3.0 Ton Valve Pairing: 5/8" suction + 1/4" liquid
    vg_36 = next((g for g in res_36['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    assert vg_36 is not None, "GF-36TFIH must have Cut-off & Service Valves group"
    assert vg_36['primary']['role'] == "Cut-Off Valve (5/8\")", f"GF-36TFIH primary valve must be 5/8\", got {vg_36['primary']['role']}"
    assert vg_36['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")", f"GF-36TFIH alt valve must be 1/4\", got {vg_36['alternatives'][0]['role']}"
    print(f"GF-36TFIH Evaporator: {evap_36['primary']['part_no']} (Price: Rs. {evap_36['primary']['price']:,}, Stock: {evap_36['primary']['bal_qty']})")
    print(f"GF-36TFIH Valves: Suction={vg_36['primary']['part_no']} ({vg_36['primary']['role']}), Liquid={vg_36['alternatives'][0]['part_no']} ({vg_36['alternatives'][0]['role']})")
    print(">>> PASS: GF-36TFIH 100% verified with genuine Evaporator 11001000602 at Rs. 58,000 (0% leakage of 24ISH & 48FW).")

    # 12. 1.0 Ton 3/8" Valve Customer Verified Pricing (Rs. 1,500) & Dual Pairing Consistency
    print("\n[TEST 12] Testing 1.0 Ton 3/8\" Valve Customer Verified Pricing (Rs. 1,500)...")
    res_12 = fetch_tiered_compatible_parts("GS-12PITH11W")
    vg_12 = next((g for g in res_12['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    assert vg_12 is not None, "GS-12PITH11W must have Cut-off & Service Valves group"
    assert vg_12['primary']['part_no'] == "71302395", f"Primary valve must be 71302395, got {vg_12['primary']['part_no']}"
    assert vg_12['primary']['price'] == 1500, f"Expected 1.0 Ton 3/8\" valve price 1,500, got {vg_12['primary']['price']}"
    assert vg_12['alternatives'][0]['part_no'] == "7130239", f"Alt valve must be 7130239, got {vg_12['alternatives'][0]['part_no']}"
    assert vg_12['alternatives'][0]['price'] == 1600, f"Expected 1.0 Ton 1/4\" valve price 1,600, got {vg_12['alternatives'][0]['price']}"

    stk_12_valve = search_stock_global("71302395")
    assert not stk_12_valve.empty, "Direct search for 71302395 must return item"
    direct_valve_price = int(stk_12_valve.iloc[0]['price'])
    assert direct_valve_price == 1500, f"Direct stock search for 71302395 must return 1,500, got {direct_valve_price}"
    assert vg_12['primary']['price'] == direct_valve_price, "Price discrepancy between model search and stock search for 3/8\" valve!"
    print(f"1.0 Ton 3/8\" Valve 71302395: Rs. {vg_12['primary']['price']:,} (Model Search) == Rs. {direct_valve_price:,} (Direct Stock Search)")
    print(">>> PASS: 1.0 Ton 3/8\" valve accurately verified at customer billing rate Rs. 1,500 with 100% system consistency.")

    # 13. Exact Closed Complaint Ground-Truth Rate & Description Verification (GF-36TFIH & System-Wide)
    print("\n[TEST 13] Testing Exact Closed-Complaint Ground-Truth Rates & Field Descriptions...")
    res_36_gt = fetch_tiered_compatible_parts("GF-36TFIH")
    vg_36_gt = next((g for g in res_36_gt['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    assert vg_36_gt is not None, "GF-36TFIH must have Cut-off & Service Valves group"
    
    # 5/8" Valve verification (Customer billing collection = Rs. 2,200)
    v58 = vg_36_gt['primary']
    assert v58['part_no'] == "7133844", f"Expected 7133844, got {v58['part_no']}"
    assert v58['price'] == 2200, f"Expected Rs. 2,200 for 7133844, got {v58['price']}"
    assert "24LITH11M" in v58['part_name'], f"Expected closed complaint description, got {v58['part_name']}"
    
    # 1/4" Valve verification (Customer billing collection = Rs. 1,600)
    v14 = vg_36_gt['alternatives'][0]
    assert v14['part_no'] == "7130239", f"Expected 7130239, got {v14['part_no']}"
    assert v14['price'] == 1600, f"Expected Rs. 1,600 for 7130239, got {v14['price']}"
    assert "GS-11CITH3F" in v14['part_name'], f"Expected closed complaint description 'Cut off Valve 1/4 GS-11CITH3F', got {v14['part_name']}"
    
    # SQLite parts_master verification
    import sqlite3
    with sqlite3.connect("dwp_service.db") as conn:
        c = conn.cursor()
        c.execute("SELECT part_no, part_name, price FROM parts_master WHERE model = 'GF-36TFIH' AND part_no IN ('7133844', '7130239', '11001000602')")
        db_rows = {row[0]: (row[1], row[2]) for row in c.fetchall()}
        assert '7133844' in db_rows and db_rows['7133844'][1] == 2200, f"DB parts_master 7133844 must be 2200, got {db_rows.get('7133844')}"
        assert '7130239' in db_rows and db_rows['7130239'][1] == 1600, f"DB parts_master 7130239 must be 1600, got {db_rows.get('7130239')}"
        assert '11001000602' in db_rows and db_rows['11001000602'][1] == 58000, f"DB parts_master 11001000602 must be 58000, got {db_rows.get('11001000602')}"
        
    print(f"GF-36TFIH 5/8\" Valve: {v58['part_name']} -> Rs. {v58['price']:,} (Verified from Closed Complaint #282629821)")
    print(f"GF-36TFIH 1/4\" Valve: {v14['part_name']} -> Rs. {v14['price']:,} (Verified from Closed Complaint #282629821)")
    print(">>> PASS: Exact closed-complaint ground-truth rates & field descriptions verified with 100% precision.")

    # 14. Milestone 1 Challenger 1 Empirical Adversarial Stress Test Suite
    print("\n[TEST 14] Running Milestone 1 Challenger 1 Empirical Adversarial Stress Test Suite...")
    import sqlite3
    import json
    import pandas as pd

    # 14.1 Database Integrity & Zero-Price Immunity
    with sqlite3.connect("dwp_service.db") as conn:
        c = conn.cursor()
        for tbl in ['stock_master', 'parts_master', 'history_master', 'tech_performance_master']:
            c.execute(f"SELECT count(*) FROM {tbl}")
            cnt = c.fetchone()[0]
            print(f"Table {tbl}: {cnt} rows")
            if tbl != 'tech_performance_master':
                assert cnt > 0, f"Table {tbl} must not be empty"

        c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0 OR unit_price IS NULL")
        assert c.fetchone()[0] == 0, "Found zero or negative prices in stock_master!"

        c.execute("SELECT count(*) FROM parts_master WHERE price <= 0 OR price IS NULL")
        assert c.fetchone()[0] == 0, "Found zero or negative prices in parts_master!"

        # Ledger book leakage audit: amount == unit_price * bal_qty
        c.execute("SELECT count(*) FROM stock_master WHERE last_synced = 'DWP Official Price Catalog (vp786.pdf)' AND bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01")
        cat_discrepancy = c.fetchone()[0]
        print(f"Catalog rows discrepancy count (vp786.pdf): {cat_discrepancy}")
        assert cat_discrepancy == 0, "Catalog rows have ledger leakage!"

        c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01")
        total_discrepancy = c.fetchone()[0]
        print(f"Non-catalog inventory rows with old ledger amount: {total_discrepancy} of 972 rows.")
        assert total_discrepancy == 0, f"Found {total_discrepancy} non-catalog inventory rows with old ledger amount!"

        c.execute("SELECT count(*) FROM stock_master WHERE part_no IS NULL OR TRIM(part_no) = ''")
        assert c.fetchone()[0] == 0, "Found null/empty part_no in stock_master!"
        c.execute("SELECT count(*) FROM parts_master WHERE part_no IS NULL OR TRIM(part_no) = ''")
        assert c.fetchone()[0] == 0, "Found null/empty part_no in parts_master!"

    # 14.2 Ground Truth Baseline JSON Stress Test
    with open("data/ground_truth_baseline.json", "r", encoding="utf-8") as f:
        bl = json.load(f)

    pb = bl.get('price_book', {})
    assert len(pb) > 0, "Baseline price_book is empty!"
    for pno, d in pb.items():
        assert isinstance(d.get('price'), (int, float)) and d['price'] > 0, f"Baseline price_book part {pno} has invalid price {d.get('price')}"

    gs = bl.get('global_stock', {})
    assert len(gs) > 0, "Baseline global_stock is empty!"
    for pno, d in gs.items():
        assert d.get('unit_price', 0) > 0, f"Baseline global_stock part {pno} has invalid unit_price {d.get('unit_price')}"

    for m, m_data in bl.get('models', {}).items():
        for p in m_data.get('parts', []):
            assert p.get('price', 0) > 0, f"Baseline model {m} part {p.get('part_no')} has invalid price {p.get('price')}"

    for s_key, s_parts in bl.get('series', {}).items():
        for p in s_parts:
            assert p.get('price', 0) > 0, f"Baseline series {s_key} part {p.get('part_no')} has invalid price {p.get('price')}"

    print(">>> PASS 14.1 & 14.2: dwp_service.db and data/ground_truth_baseline.json 100% zero-price immune and free of ledger corruption.")

    # 14.3 Official Catalog 518 Parts Ingestion & Price Fidelity
    df_cat = pd.read_csv("data/pdf_extracted_stock_report.csv")
    df_cat['clean_pno'] = df_cat['part_no'].astype(str).str.strip().str.upper()
    df_cat['clean_pr'] = pd.to_numeric(df_cat['pdf_price'], errors='coerce').fillna(0).round().astype(int)
    cat_agg = df_cat.groupby('clean_pno')['clean_pr'].max().to_dict()
    assert len(cat_agg) == 518, f"Expected 518 unique parts in catalog, got {len(cat_agg)}"

    with sqlite3.connect("dwp_service.db") as conn:
        c = conn.cursor()
        c.execute("SELECT part_no, unit_price FROM stock_master")
        db_stk = dict(c.fetchall())
        c.execute("SELECT DISTINCT part_no FROM parts_master")
        db_pm = set(r[0] for r in c.fetchall())

    for pno, exp_pr in cat_agg.items():
        assert pno in db_stk, f"Catalog part {pno} missing from stock_master!"
        assert db_stk[pno] == exp_pr, f"Catalog part {pno} price mismatch in stock_master: got {db_stk[pno]}, expected {exp_pr}"
        assert pno in db_pm, f"Catalog part {pno} missing from parts_master!"
        assert pno in pb, f"Catalog part {pno} missing from baseline price_book!"
        assert pb[pno]['price'] == exp_pr, f"Catalog part {pno} price mismatch in price_book: got {pb[pno]['price']}, expected {exp_pr}"

    print(f">>> PASS 14.3: All {len(cat_agg)} catalog parts verified across stock_master, parts_master, and price_book.")

    # 14.4 Target Components Reconciliation Across DB, Baseline, and Global Search
    target_components = {
        '71302395': ('Cut-Off Valve (3/8")', 1500),
        '7130239':  ('Cut-Off Valve (1/4")', 1600),
        '7133774':  ('Cut-Off Valve (1/2")', 2100),
        '7133844':  ('Cut-Off Valve (5/8")', 2200),
        '11001000602': ('Evaporator Assembly', 58000),
        '11001060868': ('Evaporator Assembly', 26000),
        '11001062414': ('Evaporator Assembly', 30000),
        '1004169':     ('Evaporator Assembly', 70000),
        '11001060092': ('Evaporator Assembly', 72000),
        '11001060521': ('Evaporator Assembly', 75000),
        '100404401':   ('Evaporator Assembly', 66000),
    }
    for pno, (role, exp_pr) in target_components.items():
        assert db_stk.get(pno) == exp_pr, f"Target part {pno} DB price mismatch: got {db_stk.get(pno)}, expected {exp_pr}"
        assert pb.get(pno, {}).get('price') == exp_pr, f"Target part {pno} price_book mismatch: got {pb.get(pno, {}).get('price')}, expected {exp_pr}"
        sr = search_stock_global(pno)
        assert not sr.empty, f"Target part {pno} direct search returned empty"
        assert int(sr.iloc[0]['price']) == exp_pr, f"Target part {pno} direct search price mismatch: got {int(sr.iloc[0]['price'])}, expected {exp_pr}"

    print(f">>> PASS 14.4: All {len(target_components)} target components match official prices across DB, Baseline, and Direct Search.")

    # 14.5 Adversarial Edge Case Lookups & Robustness
    hostile_queries = [
        " 71302395 ", "   7130239   ", "\t7133774\n", "  evaporator  ",
        "valve", "VALVE", "VaLvE", "pcb", "Pcb", "EVAPORATOR",
        '3/8"', '1/4"', '1/2"', '5/8"', "Cut-Off", "Assy",
        "713023", "1100100", "PITH", "CITH",
        "%", "_", "'", "''", ";", "--", "\\", "   ", "",
        "NON_EXISTENT_PART_XYZ_99999", "1234567890987654321"
    ]
    for q in hostile_queries:
        res_sr = search_stock_global(q, limit=20)
        assert isinstance(res_sr, pd.DataFrame), f"Search query '{q}' did not return DataFrame"
        if not res_sr.empty:
            assert 'price' in res_sr.columns, "Search missing price column"
            assert (res_sr['price'] > 0).all(), f"Search query '{q}' returned parts with price <= 0!"

    hostile_models = [
        "  GS-18ZITH1W-T3  ", "gs-18zith1w-t3", "  gf-36tfih  ", "=GF-36TFIH=",
        "UNKNOWN-MODEL-999", "GS-99UNKNOWN-T1", "RANDOM_STRING_MODEL", "", "   "
    ]
    for hm in hostile_models:
        res_m = fetch_tiered_compatible_parts(hm)
        assert isinstance(res_m, dict), f"Model lookup for '{hm}' did not return dict"
        for grp in res_m.get('role_groups', []):
            pri = grp.get('primary')
            if pri:
                assert pri.get('price', 0) > 0, f"Model '{hm}' primary part {pri.get('part_no')} price <= 0!"
            for alt in grp.get('alternatives', []):
                assert alt.get('price', 0) > 0, f"Model '{hm}' alt part {alt.get('part_no')} price <= 0!"

    print(">>> PASS 14.5: Adversarial queries, SQL characters, whitespace variations, and unknown models handled gracefully with zero price violations.")

    # 15. Interface Contract & Multi-Tier Structure Validation (Requirement R3 & Milestone 2)
    print("\n[TEST 15] Testing Interface Contract & Multi-Tier Structure Validation...")
    models_to_test = ["GS-18PITH11W", "GS-12PITH11W", "GF-36TFIH", "GR-E8768G-CP1", "EW-F1202DC"]
    for m in models_to_test:
        res = fetch_tiered_compatible_parts(m)
        assert isinstance(res, dict), f"Result for {m} must be a dict"
        # Verify required contract keys
        for key in ['tier1', 'tier2', 'tier3', 'metadata', 'meta', 'role_groups', 'compatible_parts']:
            assert key in res, f"Result for {m} missing contract key '{key}'"

        assert isinstance(res['tier1'], list), f"{m} tier1 must be a list"
        assert isinstance(res['tier2'], list), f"{m} tier2 must be a list"
        assert isinstance(res['tier3'], list), f"{m} tier3 must be a list"
        assert isinstance(res['metadata'], dict), f"{m} metadata must be a dict"

        # Verify metadata contract
        meta_d = res['metadata']
        assert 'tier1_count' in meta_d and meta_d['tier1_count'] == len(res['tier1'])
        assert 'tier2_count' in meta_d and meta_d['tier2_count'] == len(res['tier2'])
        assert 'tier3_count' in meta_d and meta_d['tier3_count'] == len(res['tier3'])

        # Verify tier codes and integrity
        for p in res['tier1']:
            assert p.get('tier_code') == 1, f"{m} tier1 part {p.get('part_no')} has invalid tier_code: {p.get('tier_code')}"
            assert p.get('price', 0) > 0, f"{m} tier1 part {p.get('part_no')} price <= 0"

        for p in res['tier2']:
            assert p.get('tier_code') == 2, f"{m} tier2 part {p.get('part_no')} has invalid tier_code: {p.get('tier_code')}"
            assert p.get('price', 0) > 0, f"{m} tier2 part {p.get('part_no')} price <= 0"

        for p in res['tier3']:
            assert p.get('tier_code') == 3, f"{m} tier3 part {p.get('part_no')} has invalid tier_code: {p.get('tier_code')}"
            assert p.get('bal_qty', 0) > 0, f"{m} tier3 part {p.get('part_no')} bal_qty must be > 0"
            assert p.get('in_stock') is True, f"{m} tier3 part {p.get('part_no')} in_stock must be True"
            assert p.get('price', 0) > 0, f"{m} tier3 part {p.get('part_no')} price <= 0"

        print(f"{m} ({meta_d.get('category')}, {meta_d.get('tonnage')}): Tier 1={len(res['tier1'])}, Tier 2={len(res['tier2'])}, Tier 3={len(res['tier3'])}, Groups={len(res['role_groups'])}")
    print(">>> PASS: Interface contract and 3-tier structure integrity validated across Split AC, Floor Standing, Refrigerator, and Washing Machine.")

    # 16. Tier 3 Strict Physical Pairing & Zero Ledger Discrepancy (Requirement R3 & Milestone 2)
    print("\n[TEST 16] Testing Tier 3 Strict Physical Pairing & Zero Ledger Discrepancy...")
    with sqlite3.connect("dwp_service.db") as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01")
        discrepancy_cnt = c.fetchone()[0]
        assert discrepancy_cnt == 0, f"Expected 0 ledger discrepancies in stock_master, found {discrepancy_cnt}"
        print(f"Zero ledger discrepancy verified: {discrepancy_cnt} rows with obsolete ledger valuation.")

    # AC Physical Valve Pairing Strictness in Tier 3
    ac_tonnage_tests = [
        ("GS-12PITH11W", "1.0 Ton", ["Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")"], ["7133774", "7133844"]),
        ("GS-18PITH11W", "1.5 Ton", ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"], ["71302395", "7133844"]),
        ("GS-24PITH11W", "2.0 Ton", ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"], ["71302395", "7133774"]),
        ("GF-36TFIH",    "3.0 Ton", ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"], ["71302395", "7133774"]),
        ("GF-48TF",      "4.0 Ton", ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"], ["7130239", "7133774"])
    ]
    for model_code, ton, prohibited_roles, prohibited_pnos in ac_tonnage_tests:
        res = fetch_tiered_compatible_parts(model_code)
        for p in res['tier3']:
            for pr in prohibited_roles:
                assert p.get('role') != pr, f"{model_code} ({ton}) leaked prohibited valve role {pr} in Tier 3: {p.get('part_no')}"
            for pp in prohibited_pnos:
                assert p.get('part_no') != pp, f"{model_code} ({ton}) leaked prohibited valve part_no {pp} in Tier 3: {p.get('part_name')}"

    # Non-AC Category Isolation in ALL Tiers
    non_ac_models = ["GR-E8768G-CP1", "EW-F1202DC", "WD-E500"]
    ac_valves = {'7130239', '71302395', '7133774', '7133844'}
    ac_evaps = {'11001000602', '11001060868', '11001062414', '1004169', '11001060092', '11001060521', '100404401', '1002937LC', '11001061842LC'}
    for m in non_ac_models:
        res = fetch_tiered_compatible_parts(m)
        all_parts = res['tier1'] + res['tier2'] + res['tier3']
        for p in all_parts:
            r = p.get('role', '')
            pno = p.get('part_no', '')
            assert "Cut-Off Valve" not in r, f"Non-AC model {m} leaked AC Cut-off Valve: {pno} ({r})"
            assert pno not in ac_valves, f"Non-AC model {m} leaked AC Valve part {pno}!"
            if "EW-" in m or "WM-" in m:
                assert "Evaporator" not in r, f"Washing Machine model {m} leaked Evaporator: {pno}"
            if "Evaporator" in r:
                assert pno not in ac_evaps, f"Non-AC model {m} leaked AC Evaporator {pno}!"
    print(">>> PASS: Strict physical line pairing, zero ledger discrepancies, and 0% cross-category contamination verified.")

    # 17. Milestone 3: Official Master Catalog & Valve Selling Prices Across Models & Direct Searches (R4 Acceptance Criteria)
    print("\n[TEST 17] Testing Official Valve Prices Across All Categories & Direct Searches...")

    # (a) 3/8" Valve (71302395) displays Rs. 1,500 across 1.0 Ton AC models and direct searches
    models_10 = ["GS-12PITH11W", "GS-12CITH11W", "GS-12PITH1W", "GS-12ZITH1W"]
    for m in models_10:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['part_no'] == "71302395", f"{m} 3/8\" suction valve expected 71302395, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 1500, f"{m} 3/8\" valve price expected 1,500, got {vg['primary']['price']}"
    
    stk_38 = search_stock_global("71302395")
    assert not stk_38.empty, "Direct search for 71302395 must return item"
    assert int(stk_38.iloc[0]['price']) == 1500, f"Direct search for 71302395 expected 1,500, got {int(stk_38.iloc[0]['price'])}"
    print(">>> PASS 17.a: 3/8\" Valve (71302395) displays Rs. 1,500 across all 1.0 Ton AC models and direct searches.")

    # (b) 1/4" Valve (7130239) displays Rs. 1,600 across all models and direct searches
    models_14 = [
        "GS-12PITH11W", "GS-12CITH11W", "GS-12PITH1W", "GS-12ZITH1W",
        "GS-18PITH11W", "GS-18CITH12G", "GS-18ZITH1W-T3", "GS-18AITH23W-T3",
        "GS-24PITH11W", "GS-24CITH1", "GS-24ISH", "GF-24CB", "GF-36TFIH"
    ]
    for m in models_14:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        all_valves = [vg['primary']] + vg['alternatives']
        v14 = next((v for v in all_valves if v['part_no'] == "7130239"), None)
        assert v14 is not None, f"{m} must contain 1/4\" liquid valve 7130239"
        assert v14['price'] == 1600, f"{m} 1/4\" valve 7130239 expected price 1,600, got {v14['price']}"

    stk_14 = search_stock_global("7130239")
    assert not stk_14.empty, "Direct search for 7130239 must return item"
    row_14 = stk_14[stk_14['part_no'] == '7130239']
    assert not row_14.empty, "Direct search for 7130239 must contain 7130239 record"
    assert int(row_14.iloc[0]['price']) == 1600, f"Direct search for 7130239 expected 1,600, got {int(row_14.iloc[0]['price'])}"
    print(">>> PASS 17.b: 1/4\" Valve (7130239) displays Rs. 1,600 across all models and direct searches.")

    # (c) 1/2" Valve (7133774) displays Rs. 2,100 across all 1.5 Ton models and direct searches
    models_15 = ["GS-18PITH11W", "GS-18CITH12G", "GS-18ZITH1W-T3", "GS-18AITH23W-T3"]
    for m in models_15:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['part_no'] == "7133774", f"{m} 1/2\" suction valve expected 7133774, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 2100, f"{m} 1/2\" valve price expected 2,100, got {vg['primary']['price']}"

    stk_12 = search_stock_global("7133774")
    assert not stk_12.empty, "Direct search for 7133774 must return item"
    assert int(stk_12.iloc[0]['price']) == 2100, f"Direct search for 7133774 expected 2,100, got {int(stk_12.iloc[0]['price'])}"
    print(">>> PASS 17.c: 1/2\" Valve (7133774) displays Rs. 2,100 across all 1.5 Ton models and direct searches.")

    # (d) 5/8" Valve (7133844) displays Rs. 2,200 across all 2.0 Ton and 3.0 Ton models (including GF-36TFIH) and direct searches
    models_20_30 = ["GS-24PITH11W", "GS-24CITH1", "GS-24ISH", "GF-24CB", "GF-36TFIH"]
    for m in models_20_30:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"{m} must have Cut-off & Service Valves group"
        assert vg['primary']['part_no'] == "7133844", f"{m} 5/8\" suction valve expected 7133844, got {vg['primary']['part_no']}"
        assert vg['primary']['price'] == 2200, f"{m} 5/8\" valve price expected 2,200, got {vg['primary']['price']}"

    stk_58 = search_stock_global("7133844")
    assert not stk_58.empty, "Direct search for 7133844 must return item"
    assert int(stk_58.iloc[0]['price']) == 2200, f"Direct search for 7133844 expected 2,200, got {int(stk_58.iloc[0]['price'])}"
    print(">>> PASS 17.d: 5/8\" Valve (7133844) displays Rs. 2,200 across all 2.0 Ton and 3.0 Ton models (including GF-36TFIH) and direct searches.")

    # 18. Milestone 3: Official Evaporator Pricing for All 7 Specified Reference Models (R4 Acceptance Criteria)
    print("\n[TEST 18] Testing Official Evaporator Pricing for All 7 Specified Reference Models...")
    official_evaps = [
        ("GF-36TFIH",       "11001000602", 58000, "3.0 Ton Floor Standing"),
        ("GS-18PITH1W",     "11001060868", 26000, "1.5 Ton Split AC PITH"),
        ("GS-18AITH23W-T3", "11001062414", 30000, "1.5 Ton Split AC AITH-T3"),
        ("GF-48FW",         "1004169",     70000, "4.0 Ton Floor Standing"),
        ("GF-24ISH",        "11001060092", 72000, "2.0 Ton Floor Standing ISH"),
        ("GF-48TF",         "11001060521", 75000, "4.0 Ton Floor Standing TF"),
        ("GF-24CB",         "100404401",   66000, "2.0 Ton Floor Standing CB")
    ]
    for model_code, exp_pno, exp_price, desc in official_evaps:
        # Check model resolution
        res = fetch_tiered_compatible_parts(model_code)
        evap_grp = next((g for g in res['role_groups'] if "Evaporator" in g['group_title']), None)
        assert evap_grp is not None, f"Model {model_code} must have an Evaporator group"
        assert evap_grp['primary']['part_no'] == exp_pno, f"Model {model_code} primary evaporator expected {exp_pno}, got {evap_grp['primary']['part_no']}"
        assert evap_grp['primary']['price'] == exp_price, f"Model {model_code} evaporator price expected Rs. {exp_price:,}, got Rs. {evap_grp['primary']['price']:,}"
        
        # Check direct stock search
        stk_df = search_stock_global(exp_pno)
        assert not stk_df.empty, f"Direct stock search for {exp_pno} ({model_code}) returned empty"
        direct_pr = int(stk_df.iloc[0]['price'])
        assert direct_pr == exp_price, f"Direct search for {exp_pno} expected Rs. {exp_price:,}, got Rs. {direct_pr:,}"
        print(f"  * {model_code:16} ({desc}): Evaporator {exp_pno} = Rs. {exp_price:,} (Model & Direct Match)")

    print(">>> PASS: All 7 official evaporator reference prices verified with 100% precision across model lookups and direct searches.")

    # 19. Milestone 3: GF-36TFIH Floor Standing Complete Physical Isolation & Zero Contamination (R4 Acceptance Criteria)
    print("\n[TEST 19] Testing GF-36TFIH Floor Standing Complete Physical Isolation & Zero Contamination...")
    res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
    
    # Evaporator Isolation
    evap_grp_36 = next((g for g in res_36['role_groups'] if "Evaporator" in g['group_title']), None)
    assert evap_grp_36 is not None, "GF-36TFIH must have an Evaporator group"
    assert evap_grp_36['primary']['part_no'] == "11001000602", f"GF-36TFIH evaporator must be 11001000602, got {evap_grp_36['primary']['part_no']}"
    assert evap_grp_36['primary']['price'] == 58000, f"GF-36TFIH evaporator price must be 58,000, got {evap_grp_36['primary']['price']}"
    assert len(evap_grp_36['alternatives']) == 0, f"GF-36TFIH must have 0 alternative evaporators, got {len(evap_grp_36['alternatives'])}"

    # Valve Isolation & Exact Dual Pairing
    valve_grp_36 = next((g for g in res_36['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    assert valve_grp_36 is not None, "GF-36TFIH must have Cut-off & Service Valves group"
    assert valve_grp_36['primary']['part_no'] == "7133844", f"GF-36TFIH suction valve must be 7133844, got {valve_grp_36['primary']['part_no']}"
    assert valve_grp_36['primary']['price'] == 2200, f"GF-36TFIH suction valve price must be 2,200, got {valve_grp_36['primary']['price']}"
    assert valve_grp_36['primary']['role'] == "Cut-Off Valve (5/8\")", f"GF-36TFIH suction valve role must be 5/8\", got {valve_grp_36['primary']['role']}"
    
    assert len(valve_grp_36['alternatives']) == 1, f"GF-36TFIH must have exactly 1 alternative valve, got {len(valve_grp_36['alternatives'])}"
    assert valve_grp_36['alternatives'][0]['part_no'] == "7130239", f"GF-36TFIH liquid valve must be 7130239, got {valve_grp_36['alternatives'][0]['part_no']}"
    assert valve_grp_36['alternatives'][0]['price'] == 1600, f"GF-36TFIH liquid valve price must be 1,600, got {valve_grp_36['alternatives'][0]['price']}"
    assert valve_grp_36['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")", f"GF-36TFIH liquid valve role must be 1/4\", got {valve_grp_36['alternatives'][0]['role']}"

    # Zero Contamination Across Entire Response (role_groups, tier1, tier2, tier3)
    all_36_parts = (
        [g['primary']['part_no'] for g in res_36['role_groups']] +
        [a['part_no'] for g in res_36['role_groups'] for a in g['alternatives']] +
        [p['part_no'] for p in res_36['tier1']] +
        [p['part_no'] for p in res_36['tier2']] +
        [p['part_no'] for p in res_36['tier3']]
    )
    prohibited_contaminants = [
        ("11001060092", "2.0 Ton 24ISH Evaporator"),
        ("1004169",     "4.0 Ton 48FW Evaporator"),
        ("11001060246", "4.0 Ton 48FWITH Evaporator"),
        ("100404401",   "2.0 Ton 24CB Evaporator"),
        ("11001060521", "4.0 Ton 48TF Evaporator"),
        ("71302395",    "1.0 Ton 3/8\" Valve"),
        ("7133774",     "1.5 Ton 1/2\" Valve")
    ]
    for pno_bad, label in prohibited_contaminants:
        assert pno_bad not in all_36_parts, f"CRITICAL LEAKAGE: {label} ({pno_bad}) leaked into GF-36TFIH!"

    print(">>> PASS: GF-36TFIH returns ONLY genuine Evaporator 11001000602 (Rs. 58,000), 5/8\" Suction Valve 7133844 (Rs. 2,200), and 1/4\" Liquid Valve 7130239 (Rs. 1,600) with 0% contamination.")

    # 20. Milestone 3: Universal AC Dual Physical Valve Pairing & Zero Clutter Across All Categories (R4 Acceptance Criteria)
    print("\n[TEST 20] Testing Universal AC Dual Physical Valve Pairing & Zero Clutter Across All Categories...")
    universal_valve_matrix = [
        # (model, category, tonnage, expected_suction_pno, expected_suction_role, suction_price, expected_liquid_pno, expected_liquid_role, liquid_price)
        ("GS-12PITH11W",    "Split AC",          "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-12CITH11W",    "Split AC",          "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-12PITH1W",     "Split AC",          "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-12ZITH1W",     "Split AC",          "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-18PITH11W",    "Split AC",          "1.5 Ton", "7133774",  "Cut-Off Valve (1/2\")", 2100, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-18CITH12G",    "Split AC",          "1.5 Ton", "7133774",  "Cut-Off Valve (1/2\")", 2100, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-18ZITH1W-T3",  "Split AC",          "1.5 Ton", "7133774",  "Cut-Off Valve (1/2\")", 2100, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-18AITH23W-T3", "Split AC",          "1.5 Ton", "7133774",  "Cut-Off Valve (1/2\")", 2100, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-24PITH11W",    "Split AC",          "2.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-24CITH1",      "Split AC",          "2.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GS-24ISH",        "Split AC",          "2.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GF-24CB",         "Floor Standing AC", "2.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GF-36TFIH",       "Floor Standing AC", "3.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "7130239",  "Cut-Off Valve (1/4\")", 1600),
        ("GF-48TF",         "Floor Standing AC", "4.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "71302395", "Cut-Off Valve (3/8\")", 1500),
        ("GF-48FW",         "Floor Standing AC", "4.0 Ton", "7133844",  "Cut-Off Valve (5/8\")", 2200, "71302395", "Cut-Off Valve (3/8\")", 1500),
    ]

    for model, cat, ton, exp_suc_pno, exp_suc_role, suc_pr, exp_liq_pno, exp_liq_role, liq_pr in universal_valve_matrix:
        res = fetch_tiered_compatible_parts(model)
        vg_list = [g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']]
        assert len(vg_list) == 1, f"Model {model} must have exactly 1 Cut-off & Service Valves group, got {len(vg_list)}"
        vg = vg_list[0]
        
        # Verify Suction valve (primary)
        pri = vg['primary']
        assert pri['part_no'] == exp_suc_pno, f"{model} ({ton}) Suction valve expected {exp_suc_pno}, got {pri['part_no']}"
        assert pri['role'] == exp_suc_role, f"{model} ({ton}) Suction role expected {exp_suc_role}, got {pri['role']}"
        assert pri['price'] == suc_pr, f"{model} ({ton}) Suction price expected Rs. {suc_pr:,}, got Rs. {pri['price']:,}"
        
        # Verify Liquid valve (alternative) - exactly 1 alternative
        assert len(vg['alternatives']) == 1, f"{model} ({ton}) must have exactly 1 alternative valve, got {len(vg['alternatives'])}"
        alt = vg['alternatives'][0]
        assert alt['part_no'] == exp_liq_pno, f"{model} ({ton}) Liquid valve expected {exp_liq_pno}, got {alt['part_no']}"
        assert alt['role'] == exp_liq_role, f"{model} ({ton}) Liquid role expected {exp_liq_role}, got {alt['role']}"
        assert alt['price'] == liq_pr, f"{model} ({ton}) Liquid price expected Rs. {liq_pr:,}, got Rs. {alt['price']:,}"
        
        # Zero clutter check: only these 2 valve sizes allowed in the group
        all_group_roles = [pri['role'], alt['role']]
        allowed_roles = {exp_suc_role, exp_liq_role}
        assert set(all_group_roles) == allowed_roles, f"{model} ({ton}) contains cluttered roles: {all_group_roles}"
        print(f"  * {model:16} ({cat}, {ton:7}): {exp_suc_role} ({exp_suc_pno}) Rs. {suc_pr:,} + {exp_liq_role} ({exp_liq_pno}) Rs. {liq_pr:,} [ZERO CLUTTER]")

    print(">>> PASS: Universal AC Dual Physical Valve Pairing verified across all 15 test models with zero clutter and exact pricing.")

    print("\n" + "=" * 60)
    print("ALL 20 SYSTEM & ADVERSARIAL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()

