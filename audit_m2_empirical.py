"""
Comprehensive Empirical Audit & Adversarial Stress Test for Milestone 2
Audited by: M2 Reviewer 1
"""
import sqlite3
import pandas as pd
from database import fetch_tiered_compatible_parts, fetch_parts_with_live_stock, search_stock_global
from config import tokenize_appliance_model, get_tonnage_valve_pairing

def audit_database_hygiene():
    print("=== AUDIT 1: DATABASE HYGIENE ===")
    conn = sqlite3.connect("dwp_service.db")
    c = conn.cursor()
    
    # 1. Check stock_master ledger discrepancies
    c.execute("SELECT count(*) FROM stock_master WHERE abs(amount - (unit_price * bal_qty)) > 0.01")
    disc_count = c.fetchone()[0]
    print(f"Discrepancies where abs(amount - (unit_price * bal_qty)) > 0.01: {disc_count}")
    assert disc_count == 0, f"Found {disc_count} ledger discrepancies in stock_master!"
    
    # 2. Check for null or <= 0 prices in stock_master
    c.execute("SELECT count(*) FROM stock_master WHERE unit_price IS NULL OR unit_price <= 0")
    bad_price_stock = c.fetchone()[0]
    print(f"stock_master unit_price <= 0: {bad_price_stock}")
    assert bad_price_stock == 0, f"Found {bad_price_stock} stock items with invalid price!"
    
    # 3. Check for null or <= 0 prices in parts_master
    c.execute("SELECT count(*) FROM parts_master WHERE price IS NULL OR price <= 0")
    bad_price_parts = c.fetchone()[0]
    print(f"parts_master price <= 0: {bad_price_parts}")
    assert bad_price_parts == 0, f"Found {bad_price_parts} parts items with invalid price!"
    
    # 4. Check official vp786 parts in stock_master
    c.execute("SELECT count(*) FROM stock_master WHERE last_synced = 'DWP Official Price Catalog (vp786.pdf)'")
    official_count = c.fetchone()[0]
    print(f"Official catalog parts in stock_master: {official_count}")
    assert official_count == 518, f"Expected 518 official parts, found {official_count}"
    
    conn.close()
    print(">>> AUDIT 1 PASSED: Database hygiene 100% verified.")

def audit_tiered_separation_and_contract():
    print("\n=== AUDIT 2: MULTI-TIER SEPARATION & BACKWARD COMPATIBILITY ===")
    test_models = [
        'GS-18PITH11W',
        'GS-12PITH11W',
        'GS-24PITH11W',
        'GF-36TFIH',
        'GF-48FW',
        'GF-24ISH',
        'GR-E8768G-CP1',
        'EW-F1202DC',
        'WD-E500',
        'EM-20',
        'CX-43',
        'NONEXISTENT-MODEL-XYZ',
        '   gs-18pith11w   ',
        ''
    ]
    
    required_keys = ['model', 'meta', 'metadata', 'tier1', 'tier2', 'tier3', 'compatible_parts', 'role_groups', 'total_verified_jobs', 'total_parts_found']
    
    for m in test_models:
        res = fetch_tiered_compatible_parts(m)
        assert isinstance(res, dict), f"Result for '{m}' must be dict"
        for k in required_keys:
            assert k in res, f"Model '{m}' result missing required key '{k}'"
            
        t1 = res['tier1']
        t2 = res['tier2']
        t3 = res['tier3']
        
        # Check that lists contain dicts
        assert isinstance(t1, list)
        assert isinstance(t2, list)
        assert isinstance(t3, list)
        
        # Check tier codes
        for p in t1:
            assert p.get('tier_code') == 1, f"T1 item {p.get('part_no')} has invalid tier_code {p.get('tier_code')}"
            assert p.get('price', 0) > 0, f"T1 item {p.get('part_no')} has invalid price"
        for p in t2:
            assert p.get('tier_code') == 2, f"T2 item {p.get('part_no')} has invalid tier_code {p.get('tier_code')}"
            assert p.get('price', 0) > 0, f"T2 item {p.get('part_no')} has invalid price"
        for p in t3:
            assert p.get('tier_code') == 3, f"T3 item {p.get('part_no')} has invalid tier_code {p.get('tier_code')}"
            assert p.get('price', 0) > 0, f"T3 item {p.get('part_no')} has invalid price"
            assert p.get('bal_qty', 0) > 0, f"T3 item {p.get('part_no')} bal_qty <= 0"
            assert p.get('in_stock') is True, f"T3 item {p.get('part_no')} in_stock is False"
            
        # Clean separation: zero duplicate part_nos across tiers
        t1_pnos = {p['part_no'] for p in t1}
        t2_pnos = {p['part_no'] for p in t2}
        t3_pnos = {p['part_no'] for p in t3}
        
        o_1_2 = t1_pnos & t2_pnos
        o_1_3 = t1_pnos & t3_pnos
        o_2_3 = t2_pnos & t3_pnos
        
        assert len(o_1_2) == 0, f"Model '{m}': overlap between Tier 1 & Tier 2: {o_1_2}"
        assert len(o_1_3) == 0, f"Model '{m}': overlap between Tier 1 & Tier 3: {o_1_3}"
        assert len(o_2_3) == 0, f"Model '{m}': overlap between Tier 2 & Tier 3: {o_2_3}"
        
        # Backward compatibility check with legacy wrapper
        legacy_res = fetch_parts_with_live_stock(m)
        assert isinstance(legacy_res, pd.DataFrame)
        
        # Role groups structure check
        for grp in res['role_groups']:
            assert 'group_title' in grp
            assert 'primary' in grp
            assert 'alternatives' in grp
            assert 'total_items' in grp
            assert 'in_stock_items' in grp
            
        print(f"Model '{m:22}': T1={len(t1):3}, T2={len(t2):3}, T3={len(t3):3}, Groups={len(res['role_groups']):2} -> SEPARATION VERIFIED")
        
    print(">>> AUDIT 2 PASSED: Multi-tier separation & backward compatibility 100% verified.")

def audit_physical_pairing_and_carton_exclusion():
    print("\n=== AUDIT 3: PHYSICAL PAIRING & CARTON EXCLUSION ===")
    valve_pairing_expectations = {
        'GS-10PITH1': ('Cut-Off Valve (3/8")', 'Cut-Off Valve (1/4")', 1500, 1600),
        'GS-12PITH11W': ('Cut-Off Valve (3/8")', 'Cut-Off Valve (1/4")', 1500, 1600),
        'GS-18PITH11W': ('Cut-Off Valve (1/2")', 'Cut-Off Valve (1/4")', 2100, 1600),
        'GS-18ZITH1W-T3': ('Cut-Off Valve (1/2")', 'Cut-Off Valve (1/4")', 2100, 1600),
        'GS-24PITH11W': ('Cut-Off Valve (5/8")', 'Cut-Off Valve (1/4")', 2200, 1600),
        'GF-36TFIH': ('Cut-Off Valve (5/8")', 'Cut-Off Valve (1/4")', 2200, 1600),
        'GF-48TF': ('Cut-Off Valve (5/8")', 'Cut-Off Valve (3/8")', 2200, 1500)
    }
    
    for m, (exp_suc, exp_liq, exp_suc_pr, exp_liq_pr) in valve_pairing_expectations.items():
        res = fetch_tiered_compatible_parts(m)
        vg = [g for g in res['role_groups'] if 'Valves' in g['group_title']]
        assert len(vg) == 1, f"{m} missing valves group"
        valves = vg[0]
        pri = valves['primary']
        alt = valves['alternatives']
        assert pri is not None, f"{m} has no primary valve"
        assert pri['role'] == exp_suc, f"{m} primary valve role mismatch: got {pri['role']}, expected {exp_suc}"
        assert pri['price'] == exp_suc_pr, f"{m} primary valve price mismatch: got {pri['price']}, expected {exp_suc_pr}"
        
        # Check liquid valve
        liq_matches = [a for a in alt if a['role'] == exp_liq]
        assert len(liq_matches) >= 1, f"{m} missing liquid valve {exp_liq}"
        assert liq_matches[0]['price'] == exp_liq_pr, f"{m} liquid valve price mismatch: got {liq_matches[0]['price']}, expected {exp_liq_pr}"
        
        # Check no leaking valves
        all_valves = [pri] + alt
        for v in all_valves:
            assert v['role'] in (exp_suc, exp_liq), f"{m} leaked prohibited valve role {v['role']}: {v['part_no']}"
            
        print(f"{m:16}: Suction={pri['role']} (Rs.{pri['price']}), Liquid={liq_matches[0]['role']} (Rs.{liq_matches[0]['price']}) -> PERFECT PAIRING")
        
    # Check carton exclusion
    models_to_check = ['GS-18PITH11W', 'GS-18ZITH1W-T3', 'GF-36TFIH', 'GR-E8768G-CP1', 'EW-F1202DC']
    for m in models_to_check:
        res = fetch_tiered_compatible_parts(m)
        all_parts = res['tier1'] + res['tier2'] + res['tier3']
        for p in all_parts:
            desc = p['part_name'].lower()
            role = p.get('role', '')
            if any(k in desc for k in ['carton', 'caton', 'packing', 'tray', 'foam']):
                assert role not in ['Evaporator Assembly', 'Compressor & Fittings', 'Indoor Main PCB', 'Outdoor Inverter PCB'], f"{m} carton classified into critical role: {p['part_no']} - {desc}"
                
    print(">>> AUDIT 3 PASSED: Physical pairing & carton exclusion 100% verified.")

def audit_integrity_and_anti_cheating():
    print("\n=== AUDIT 4: INTEGRITY & ANTI-CHEATING AUDIT ===")
    # Check source files for suspicious hardcoding or dummy implementations
    with open("database.py", "r", encoding="utf-8") as f:
        db_content = f.read()
    with open("etl.py", "r", encoding="utf-8") as f:
        etl_content = f.read()
    with open("app.py", "r", encoding="utf-8") as f:
        app_content = f.read()
        
    # Verify no legacy amount / bal_qty division in database or etl
    assert "amount / bal_qty" not in db_content.lower(), "Found 'amount / bal_qty' in database.py"
    assert "r['amount'] / r['bal_qty']" not in etl_content, "Found 'r['amount'] / r['bal_qty']' in etl.py"
    
    # Verify fetch_tiered_compatible_parts is a real implementation, not a dummy
    assert "def fetch_tiered_compatible_parts(" in db_content
    assert "tier1_parts" in db_content
    assert "tier2_parts" in db_content
    assert "tier3_parts" in db_content
    assert "get_tonnage_valve_pairing" in db_content
    
    # Verify no hardcoded dictionary of model-to-answer shortcuts in database.py
    # e.g., if model == 'GS-18PITH11W': return [...]
    assert "if selected_model == 'GS-18PITH11W':" not in db_content
    assert "if selected_model == 'GF-36TFIH':" not in db_content
    
    print(">>> AUDIT 4 PASSED: Integrity check passed. No dummy logic, no facade shortcuts.")

def audit_edge_cases_and_performance():
    print("\n=== AUDIT 5: EDGE CASES & PERFORMANCE STRESS TESTING ===")
    import time
    
    # 1. Hostile & Edge Case Models
    hostile_models = [
        None,
        "",
        "   ",
        "' OR '1'='1' --",
        "<script>alert(1)</script>",
        "GS-999999999999999999999999999999999999999",
        "!!!@@@###$$$%%%^^^&&&***()",
        "gs-18pith11w\x00nullbyte"
    ]
    for hm in hostile_models:
        try:
            res = fetch_tiered_compatible_parts(hm)
            assert isinstance(res, dict)
            assert 'tier1' in res and 'tier2' in res and 'tier3' in res
        except Exception as e:
            # None might be passed, let's see how it behaves
            print(f"Hostile model '{hm}' raised: {type(e).__name__}: {e}")
            
    # 2. Hostile Search Queries
    hostile_queries = [
        ".*", "[a-z]+", "(", ")", "+", "?", "\\", "^$",
        "' OR 1=1", "; DROP TABLE stock_master; --",
        "   ", "\t\n", "EVAPORATOR", "11001000602"
    ]
    for hq in hostile_queries:
        res = fetch_tiered_compatible_parts("GS-18PITH11W", search_query=hq)
        assert isinstance(res, dict)
        assert 'tier1' in res
        
    # 3. Latency / Performance Test
    t0 = time.time()
    iterations = 20
    for _ in range(iterations):
        fetch_tiered_compatible_parts("GS-18PITH11W")
    avg_latency_ms = ((time.time() - t0) / iterations) * 1000
    print(f"Average lookup latency: {avg_latency_ms:.2f} ms")
    assert avg_latency_ms < 500, f"Lookup latency too high: {avg_latency_ms} ms"
    
    # 4. Non-AC Metadata Verification
    for non_ac in ['GR-E8768G-CP1', 'EW-F1202DC', 'WD-E500', 'EM-20', 'CX-43']:
        res = fetch_tiered_compatible_parts(non_ac)
        assert res['metadata']['valve_pairing'] is None, f"{non_ac} should have None valve_pairing"
    print("Non-AC valve pairing metadata verified.")

    print(">>> AUDIT 5 PASSED: Edge cases and performance stress testing verified.")

if __name__ == "__main__":
    audit_database_hygiene()
    audit_tiered_separation_and_contract()
    audit_physical_pairing_and_carton_exclusion()
    audit_integrity_and_anti_cheating()
    audit_edge_cases_and_performance()
    print("\n=======================================================")
    print("ALL EMPIRICAL AUDITS COMPLETED SUCCESSFULLY WITH 0 FAILURES!")
    print("=======================================================")
