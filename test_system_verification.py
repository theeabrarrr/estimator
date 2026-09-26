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

    # GS-18PITH11W primary evaporator must be 11001060868
    evap_grp = next((g for g in res_pith['role_groups'] if "Evaporator" in g['group_title']), None)
    assert evap_grp is not None, "GS-18PITH11W must have an Evaporator group"
    assert evap_grp['primary']['part_no'] == "11001060868", f"Expected 11001060868 as primary, got {evap_grp['primary']['part_no']}"
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

    print("\n" + "=" * 60)
    print("ALL 7 SYSTEM TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
