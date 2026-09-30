# independent_audit.py
import sys
import os
import sqlite3
import pandas as pd
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database import fetch_tiered_compatible_parts, search_stock_global, get_stock_metadata
from config import tokenize_appliance_model, is_valve_tonnage_compatible, get_tonnage_valve_pairing

def run_audit():
    print("=" * 70)
    print("M2 REVIEWER 2 INDEPENDENT AUDIT & ADVERSARIAL INTEGRITY VERIFICATION")
    print("=" * 70)

    # 1. DATABASE HYGIENE AUDIT
    print("\n--- 1. DATABASE HYGIENE AUDIT (stock_master & parts_master) ---")
    db_path = os.path.join(BASE_DIR, "dwp_service.db")
    assert os.path.exists(db_path), f"Database not found at {db_path}"
    
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM stock_master")
        total_stock = c.fetchone()[0]
        
        c.execute("SELECT count(*) FROM stock_master WHERE last_synced = 'DWP Official Price Catalog (vp786.pdf)'")
        catalog_stock = c.fetchone()[0]

        c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND abs(amount - (unit_price * bal_qty)) > 0.01")
        discrepancies_positive = c.fetchone()[0]

        c.execute("SELECT count(*) FROM stock_master WHERE abs(amount - (unit_price * bal_qty)) > 0.01")
        discrepancies_all = c.fetchone()[0]

        c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0")
        zero_prices_stock = c.fetchone()[0]

        c.execute("SELECT count(*) FROM stock_master WHERE amount < 0")
        negative_amounts = c.fetchone()[0]

        c.execute("SELECT count(*) FROM stock_master WHERE part_no IS NULL OR trim(part_no) = ''")
        invalid_pno_stock = c.fetchone()[0]

        c.execute("SELECT count(*) FROM parts_master")
        total_parts = c.fetchone()[0]

        c.execute("SELECT count(*) FROM parts_master WHERE price <= 0")
        zero_prices_parts = c.fetchone()[0]

    print(f"Total stock_master rows: {total_stock}")
    print(f"Catalog rows (vp786.pdf): {catalog_stock}")
    print(f"Discrepancies where bal_qty > 0 and abs(amount - unit_price * bal_qty) > 0.01: {discrepancies_positive}")
    print(f"Total discrepancies across all rows: {discrepancies_all}")
    print(f"Stock items with unit_price <= 0: {zero_prices_stock}")
    print(f"Stock items with amount < 0: {negative_amounts}")
    print(f"Invalid part_no in stock_master: {invalid_pno_stock}")
    print(f"Total parts_master rows: {total_parts}")
    print(f"Parts with price <= 0 in parts_master: {zero_prices_parts}")

    assert total_stock >= 518, "stock_master must contain at least 518 catalog items"
    assert discrepancies_positive == 0, f"FAILED: Found {discrepancies_positive} rows with ledger residue!"
    assert discrepancies_all == 0, f"FAILED: Found {discrepancies_all} total rows with amount discrepancy!"
    assert zero_prices_stock == 0, "FAILED: Zero/negative price found in stock_master"
    assert negative_amounts == 0, "FAILED: Negative amounts found in stock_master"
    assert invalid_pno_stock == 0, "FAILED: Empty part numbers in stock_master"
    assert zero_prices_parts == 0, "FAILED: Zero/negative price found in parts_master"
    print(">>> PASS: Database Hygiene 100% clean. Exactly 0 rows have ledger residue.")

    # 2. MULTI-TIER OUTPUT STRUCTURE AUDIT
    print("\n--- 2. MULTI-TIER OUTPUT STRUCTURE AUDIT ---")
    test_models = [
        "GS-12PITH11W", "GS-18PITH11W", "GS-24PITH11W",
        "GS-12CITH11W", "GS-18CITH12G", "GS-24CITH1",
        "GS-18ZITH1W-T3", "GS-18AITH23W-T3", "GS-18FITH1",
        "GF-24ISH", "GF-36TFIH", "GF-48TF", "GF-48FW",
        "GR-E8768G-CP1", "GR-E6758G",
        "EW-F1202DC", "EW-7010S",
        "WD-E500", "WD-E1000",
        "LE-43D10", "MO-20M1"
    ]

    total_t1 = 0
    total_t2 = 0
    total_t3 = 0

    for m in test_models:
        res = fetch_tiered_compatible_parts(m)
        assert isinstance(res, dict), f"Model {m} did not return dict"
        required_keys = ['tier1', 'tier2', 'tier3', 'metadata', 'meta', 'role_groups', 'compatible_parts', 'model']
        for rk in required_keys:
            assert rk in res, f"Model {m} missing required key: {rk}"

        assert isinstance(res['tier1'], list), f"tier1 for {m} is not a list"
        assert isinstance(res['tier2'], list), f"tier2 for {m} is not a list"
        assert isinstance(res['tier3'], list), f"tier3 for {m} is not a list"
        assert isinstance(res['metadata'], dict), f"metadata for {m} is not a dict"

        # Check metadata consistency
        md = res['metadata']
        assert md['tier1_count'] == len(res['tier1']), f"{m} tier1_count mismatch"
        assert md['tier2_count'] == len(res['tier2']), f"{m} tier2_count mismatch"
        assert md['tier3_count'] == len(res['tier3']), f"{m} tier3_count mismatch"

        # Check tier1 items
        for p in res['tier1']:
            assert p['tier_code'] == 1, f"tier1 item {p['part_no']} has code {p.get('tier_code')}"
            assert p['price'] > 0, f"tier1 item {p['part_no']} has price <= 0"
            assert p['part_no'] and len(p['part_no'].strip()) > 0, "Empty part_no in tier1"

        # Check tier2 items
        for p in res['tier2']:
            assert p['tier_code'] == 2, f"tier2 item {p['part_no']} has code {p.get('tier_code')}"
            assert p['price'] > 0, f"tier2 item {p['part_no']} has price <= 0"
            assert p['part_no'] and len(p['part_no'].strip()) > 0, "Empty part_no in tier2"

        # Check tier3 items
        for p in res['tier3']:
            assert p['tier_code'] == 3, f"tier3 item {p['part_no']} has code {p.get('tier_code')}"
            assert p['price'] > 0, f"tier3 item {p['part_no']} has price <= 0"
            assert p['bal_qty'] > 0, f"tier3 item {p['part_no']} has bal_qty <= 0: {p['bal_qty']}"
            assert p['in_stock'] is True, f"tier3 item {p['part_no']} has in_stock != True"
            # Ensure cartons are never in tier3
            nl = p['part_name'].lower()
            assert not any(k in nl for k in ['carton', 'caton', 'packing', 'foam']), f"Packaging carton in tier3: {p['part_name']}"

        total_t1 += len(res['tier1'])
        total_t2 += len(res['tier2'])
        total_t3 += len(res['tier3'])
        print(f"Model {m:18s} | Cat: {md.get('category',''):16s} | Ton: {md.get('tonnage',''):8s} | T1: {len(res['tier1']):3d} | T2: {len(res['tier2']):3d} | T3: {len(res['tier3']):3d}")

    print(f"\nTotal verified items across 21 models: Tier1={total_t1}, Tier2={total_t2}, Tier3={total_t3}")
    print(">>> PASS: Multi-tier output structure verified across 21 diverse appliance models.")

    # 3. VALVE PAIRING AUDIT
    print("\n--- 3. PHYSICAL VALVE PAIRING & TONNAGE AUDIT ---")
    valve_tests = [
        ("GS-12PITH11W", "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", "7130239", "Cut-Off Valve (1/4\")"),
        ("GS-12CITH11W", "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", "7130239", "Cut-Off Valve (1/4\")"),
        ("GS-18PITH11W", "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", "7130239", "Cut-Off Valve (1/4\")"),
        ("GS-18ZITH1W-T3", "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", "7130239", "Cut-Off Valve (1/4\")"),
        ("GS-24PITH11W", "2.0 Ton", "7133844", "Cut-Off Valve (5/8\")", "7130239", "Cut-Off Valve (1/4\")"),
        ("GF-36TFIH", "3.0 Ton", "7133844", "Cut-Off Valve (5/8\")", "7130239", "Cut-Off Valve (1/4\")"),
        ("GF-48TF", "4.0 Ton", "7133844", "Cut-Off Valve (5/8\")", "71302395", "Cut-Off Valve (3/8\")"),
    ]

    for model, ton, exp_suc_pno, exp_suc_role, exp_liq_pno, exp_liq_role in valve_tests:
        res = fetch_tiered_compatible_parts(model)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        assert vg is not None, f"Valve group missing for {model}"
        pri = vg['primary']
        alts = vg['alternatives']
        assert pri['part_no'] == exp_suc_pno, f"{model} Primary valve pno: got {pri['part_no']}, expected {exp_suc_pno}"
        assert pri['role'] == exp_suc_role, f"{model} Primary valve role: got {pri['role']}, expected {exp_suc_role}"
        assert len(alts) == 1, f"{model} alternatives count: got {len(alts)}, expected 1"
        assert alts[0]['part_no'] == exp_liq_pno, f"{model} Alt valve pno: got {alts[0]['part_no']}, expected {exp_liq_pno}"
        assert alts[0]['role'] == exp_liq_role, f"{model} Alt valve role: got {alts[0]['role']}, expected {exp_liq_role}"
        print(f"{model:16s} ({ton}): Suction={pri['part_no']} ({pri['role']}) @ Rs. {pri['price']:,} | Liquid={alts[0]['part_no']} ({alts[0]['role']}) @ Rs. {alts[0]['price']:,}")

    print(">>> PASS: Physical valve pairing strictly verified (Suction #1, Liquid #2) with 0% contamination.")

    # 4. FLOOR STANDING AC & ISOLATION AUDIT
    print("\n--- 4. FLOOR STANDING ISOLATION AUDIT (GF-36TFIH) ---")
    res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
    evap_grp = next((g for g in res_36['role_groups'] if "Evaporator" in g['group_title']), None)
    assert evap_grp is not None, "Evaporator group missing for GF-36TFIH"
    assert evap_grp['primary']['part_no'] == "11001000602", f"GF-36TFIH evaporator pno mismatch: {evap_grp['primary']['part_no']}"
    assert evap_grp['primary']['price'] == 58000, f"GF-36TFIH evaporator price mismatch: {evap_grp['primary']['price']}"
    print(f"GF-36TFIH Evaporator: Part={evap_grp['primary']['part_no']} @ Rs. {evap_grp['primary']['price']:,}")
    # Verify no leaked evaporators
    all_36_evap_pnos = [evap_grp['primary']['part_no']] + [a['part_no'] for a in evap_grp['alternatives']]
    leaked = set(all_36_evap_pnos).intersection({'11001060092', '1004169', '11001060246'})
    assert not leaked, f"CRITICAL: Leaked evaporators in GF-36TFIH: {leaked}"
    print(">>> PASS: GF-36TFIH isolated with genuine 3.0T evaporator (11001000602 @ Rs. 58,000).")

    # 5. NON-AC CROSS-CATEGORY CONTAMINATION AUDIT
    print("\n--- 5. NON-AC CROSS-CATEGORY CONTAMINATION AUDIT ---")
    for non_ac_m in ["GR-E8768G-CP1", "EW-F1202DC", "WD-E500"]:
        res_na = fetch_tiered_compatible_parts(non_ac_m)
        all_na_parts = res_na['tier1'] + res_na['tier2'] + res_na['tier3']
        for p in all_na_parts:
            assert "Cut-Off Valve" not in p['role'], f"Leaked AC valve {p['part_no']} into {non_ac_m}"
            assert p['part_no'] not in {'7130239', '71302395', '7133774', '7133844'}, f"Leaked AC valve {p['part_no']} into {non_ac_m}"
            if "EW-" in non_ac_m or "WD-" in non_ac_m:
                assert "Evaporator" not in p['role'], f"Leaked Evaporator {p['part_no']} into {non_ac_m}"
        print(f"{non_ac_m:16s}: {len(all_na_parts)} components checked, ZERO AC component leakage detected.")
    print(">>> PASS: 0% cross-category contamination strictly verified.")

    # 6. ADVERSARIAL STRESS TESTING
    print("\n--- 6. ADVERSARIAL STRESS TESTING ---")
    hostile_inputs = [
        "'; DROP TABLE stock_master; --",
        "<script>alert('xss')</script>",
        "GS-18PITH11W' OR '1'='1",
        "UNKNOWN-MODEL-99999",
        "",
        "   ",
        "gs-18pith11w",
        "  GF-36TFIH  ",
        "%%%$$$@@@",
    ]
    for hi in hostile_inputs:
        try:
            res_h = fetch_tiered_compatible_parts(hi)
            assert isinstance(res_h, dict), f"Failed to handle '{hi}' gracefully"
            assert 'tier1' in res_h and 'tier2' in res_h and 'tier3' in res_h
            for p in res_h['compatible_parts']:
                assert p['price'] > 0, f"Hostile query {hi} returned price <= 0"
        except Exception as e:
            print(f"FAILED on hostile input '{hi}': {e}")
            raise e
    print(f"Tested {len(hostile_inputs)} hostile inputs: all handled safely without crashes or price anomalies.")
    print(">>> PASS: Adversarial stress testing passed.")

    print("\n" + "=" * 70)
    print("ALL M2 INDEPENDENT AUDIT SECTIONS PASSED WITH 100% SUCCESS (0 FAILURES)!")
    print("=" * 70)

if __name__ == '__main__':
    run_audit()
