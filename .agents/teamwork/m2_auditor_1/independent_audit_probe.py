# independent_audit_probe.py
import os
import sys
import sqlite3
import json

BASE_DIR = r"c:\Users\PC\Desktop\estimator"
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    tokenize_appliance_model, classify_component_role,
    is_valve_tonnage_compatible, get_tonnage_valve_pairing,
    CATEGORY_OVERHEADS
)
from database import (
    get_connection, init_db_schema, fetch_tiered_compatible_parts,
    search_stock_global, get_stock_metadata, fetch_parts_and_models
)
from etl import bootstrap_master_data

def run_probe():
    print("=" * 60)
    print("INDEPENDENT FORENSIC AUDITOR PROBE")
    print("=" * 60)

    # 1. Database Ledger Hygiene Audit
    print("\n[CHECK 1] Database Ledger Hygiene Audit...")
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND abs(amount - (unit_price * bal_qty)) > 0.01")
        discrepancies = c.fetchone()[0]
        print(f"Residual ledger discrepancies (amount != unit_price * bal_qty): {discrepancies}")
        assert discrepancies == 0, f"Found {discrepancies} ledger discrepancies in stock_master!"

        c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0 OR unit_price IS NULL")
        zero_stk = c.fetchone()[0]
        print(f"Zero or negative prices in stock_master: {zero_stk}")
        assert zero_stk == 0, f"Found {zero_stk} zero prices in stock_master!"

        c.execute("SELECT count(*) FROM parts_master WHERE price <= 0 OR price IS NULL")
        zero_pm = c.fetchone()[0]
        print(f"Zero or negative prices in parts_master: {zero_pm}")
        assert zero_pm == 0, f"Found {zero_pm} zero prices in parts_master!"

        c.execute("SELECT count(*) FROM stock_master WHERE last_synced = 'DWP Official Price Catalog (vp786.pdf)'")
        pdf_parts = c.fetchone()[0]
        print(f"Official vp786.pdf catalog parts in stock_master: {pdf_parts}")
        assert pdf_parts >= 518, f"Expected at least 518 official parts, found {pdf_parts}"

    print(">>> CHECK 1 PASSED: 100% clean database state.")

    # 2. Dynamic Synthetic Model Resolution (Adversarial stress-test against hardcoding)
    print("\n[CHECK 2] Dynamic Synthetic Model Resolution (Adversarial Stress-Test)...")
    
    # 2a. Synthetic Split AC (1.5 Ton)
    res_syn_split = fetch_tiered_compatible_parts("GS-18SYNTHETIC99W")
    assert res_syn_split['metadata']['category'] == "Split AC"
    assert res_syn_split['metadata']['tonnage'] == "1.5 Ton"
    assert res_syn_split['metadata']['series'] == "STANDARD"
    # Tier 3 must contain 1.5 Ton valve pair
    vg_syn = next((g for g in res_syn_split['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    assert vg_syn is not None, "Synthetic Split AC must have valve group"
    assert vg_syn['primary']['role'] == "Cut-Off Valve (1/2\")"
    assert vg_syn['primary']['part_no'] == "7133774"
    assert vg_syn['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")"
    assert vg_syn['alternatives'][0]['part_no'] == "7130239"
    print(">>> 2a Synthetic Split AC 1.5T correctly resolved dynamically without hardcoding.")

    # 2b. Synthetic Floor Standing AC (3.0 Ton)
    res_syn_floor = fetch_tiered_compatible_parts("GF-36SYNTHETIC")
    assert res_syn_floor['metadata']['category'] == "Floor Standing AC"
    assert res_syn_floor['metadata']['tonnage'] == "3.0 Ton"
    vg_syn_floor = next((g for g in res_syn_floor['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    assert vg_syn_floor is not None, "Synthetic Floor Standing AC must have valve group"
    assert vg_syn_floor['primary']['role'] == "Cut-Off Valve (5/8\")"
    assert vg_syn_floor['primary']['part_no'] == "7133844"
    assert vg_syn_floor['alternatives'][0]['role'] == "Cut-Off Valve (1/4\")"
    assert vg_syn_floor['alternatives'][0]['part_no'] == "7130239"
    print(">>> 2b Synthetic Floor Standing AC 3.0T correctly resolved dynamically without hardcoding.")

    # 2c. Synthetic Non-AC Category Isolation (Refrigerator)
    res_syn_ref = fetch_tiered_compatible_parts("GR-SYNTHETIC777")
    assert res_syn_ref['metadata']['category'] == "Refrigerator"
    ref_all_parts = res_syn_ref['tier1'] + res_syn_ref['tier2'] + res_syn_ref['tier3']
    for p in ref_all_parts:
        assert "Cut-Off Valve" not in p.get('role', ''), f"Leaked AC valve into Refrigerator: {p['part_no']}"
        assert p.get('part_no') not in ['7130239', '71302395', '7133774', '7133844'], f"Leaked AC valve part: {p['part_no']}"
    print(">>> 2c Synthetic Refrigerator strictly isolated from AC valves.")

    # 2d. Synthetic Non-AC Category Isolation (Washing Machine)
    res_syn_wm = fetch_tiered_compatible_parts("EW-SYNTHETIC888")
    assert res_syn_wm['metadata']['category'] == "Washing Machine"
    wm_all_parts = res_syn_wm['tier1'] + res_syn_wm['tier2'] + res_syn_wm['tier3']
    for p in wm_all_parts:
        assert "Cut-Off Valve" not in p.get('role', ''), f"Leaked AC valve into Washing Machine: {p['part_no']}"
        assert "Evaporator" not in p.get('role', ''), f"Leaked Evaporator into Washing Machine: {p['part_no']}"
    print(">>> 2d Synthetic Washing Machine strictly isolated from AC valves & evaporators.")

    print(">>> CHECK 2 PASSED: Pure dynamic resolution proven via synthetic counter-models.")

    # 3. Acceptance Criteria Price Catalog Verification
    print("\n[CHECK 3] Acceptance Criteria Official Prices Verification...")
    expected_acceptance_prices = {
        '71302395': 1500,     # 3/8" Valve (1.0 Ton AC)
        '7130239': 1600,      # 1/4" Valve (All AC models)
        '7133774': 2100,      # 1/2" Valve (1.5 Ton AC)
        '7133844': 2200,      # 5/8" Valve (2.0T and 3.0T AC)
        '11001000602': 58000, # GF-36TFIH Evaporator
        '11001060868': 26000, # GS-18PITH1W Evaporator
        '11001062414': 30000, # GS-18AITH23W-T3 Evaporator
        '1004169': 70000,     # GF-48FW Evaporator
        '11001060092': 72000, # GF-24ISH Evaporator
        '11001060521': 75000, # GF-48TF Evaporator
        '100404401': 66000    # GF-24CB Evaporator
    }
    with get_connection() as conn:
        c = conn.cursor()
        for pno, exp_pr in expected_acceptance_prices.items():
            c.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,))
            row = c.fetchone()
            assert row is not None, f"Part {pno} missing from stock_master"
            assert row[0] == exp_pr, f"Part {pno} price mismatch in stock_master: got {row[0]}, expected {exp_pr}"

            sr = search_stock_global(pno)
            assert not sr.empty, f"search_stock_global failed for {pno}"
            assert int(sr.iloc[0]['price']) == exp_pr, f"search_stock_global price mismatch for {pno}: got {sr.iloc[0]['price']}, expected {exp_pr}"

    print(f">>> CHECK 3 PASSED: All {len(expected_acceptance_prices)} acceptance targets verified.")

    # 4. Multi-Tier Resolution Contract Integrity
    print("\n[CHECK 4] Multi-Tier Resolution Contract Integrity...")
    test_models = ["GS-18PITH11W", "GS-12PITH11W", "GF-36TFIH", "GR-E8768G-CP1", "EW-F1202DC", "WD-E500"]
    for m in test_models:
        res = fetch_tiered_compatible_parts(m)
        assert all(k in res for k in ['model', 'meta', 'metadata', 'tier1', 'tier2', 'tier3', 'compatible_parts', 'role_groups', 'total_verified_jobs', 'total_parts_found'])
        assert res['metadata']['tier1_count'] == len(res['tier1'])
        assert res['metadata']['tier2_count'] == len(res['tier2'])
        assert res['metadata']['tier3_count'] == len(res['tier3'])
        
        # Verify no overlapping part numbers across tiers
        t1_pnos = {p['part_no'] for p in res['tier1']}
        t2_pnos = {p['part_no'] for p in res['tier2']}
        t3_pnos = {p['part_no'] for p in res['tier3']}
        assert t1_pnos.isdisjoint(t2_pnos), f"Overlap between Tier 1 and Tier 2 in model {m}: {t1_pnos & t2_pnos}"
        assert t1_pnos.isdisjoint(t3_pnos), f"Overlap between Tier 1 and Tier 3 in model {m}: {t1_pnos & t3_pnos}"
        assert t2_pnos.isdisjoint(t3_pnos), f"Overlap between Tier 2 and Tier 3 in model {m}: {t2_pnos & t3_pnos}"
        
        # Verify tier codes
        for p in res['tier1']:
            assert p['tier_code'] == 1
        for p in res['tier2']:
            assert p['tier_code'] == 2
        for p in res['tier3']:
            assert p['tier_code'] == 3
            assert p['bal_qty'] > 0
            assert p['in_stock'] is True

    print(">>> CHECK 4 PASSED: Multi-tier contracts completely disjoint, properly coded, and verified.")

    print("\n" + "=" * 60)
    print("ALL AUDIT PROBE CHECKS PASSED WITH 0 ERRORS!")
    print("=" * 60)

if __name__ == "__main__":
    run_probe()
