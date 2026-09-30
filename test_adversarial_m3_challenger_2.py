"""
Empirical Adversarial Stress Harness - Milestone 3 Challenger 2
=============================================================
Independent verification suite challenging:
1. Target Valve Prices (Rs. 1500, 1600, 2100, 2200) across direct searches, DB, and multi-model lookups.
2. All 7 Official Reference Evaporator Prices (58k, 26k, 30k, 70k, 72k, 75k, 66k) across direct queries & model resolutions.
3. GF-36TFIH Floor Standing Complete Isolation: assert 0% leakage of 24ISH, 48FW, or other evaporators/valves.
4. Universal AC Dual Physical Valve Pairing & Zero Clutter across tonnages and platforms.
5. Cross-Category Isolation (Refrigerators, Washing Machines, Water Dispensers vs AC valves & evaporators).
6. Zero-Price Immunity & Ledger Book Integrity audit.
7. Hostile and Fuzz inputs (SQL tokens, whitespace, mixed-case, unassigned models).
"""

import sys
import os
import sqlite3
import json
import re
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

total_checks = 0
passed_checks = 0
failed_checks = 0
failures = []

def record_check(success, description, details=""):
    global total_checks, passed_checks, failed_checks, failures
    total_checks += 1
    if success:
        passed_checks += 1
        print(f"  [PASS] {description}")
    else:
        failed_checks += 1
        msg = f"{description} | Details: {details}"
        failures.append(msg)
        print(f"  [FAIL] {msg}")

def test_target_valve_pricing():
    print("\n" + "="*80)
    print("CHALLENGE 1: Target Valve Pricing Verification (Rs. 1500, 1600, 2100, 2200)")
    print("="*80)

    valves = {
        '71302395': {'name': '3/8" Valve', 'price': 1500, 'role': 'Cut-Off Valve (3/8")'},
        '7130239':  {'name': '1/4" Valve', 'price': 1600, 'role': 'Cut-Off Valve (1/4")'},
        '7133774':  {'name': '1/2" Valve', 'price': 2100, 'role': 'Cut-Off Valve (1/2")'},
        '7133844':  {'name': '5/8" Valve', 'price': 2200, 'role': 'Cut-Off Valve (5/8")'}
    }

    # 1. Direct Database Checks
    with get_connection() as conn:
        for pno, info in valves.items():
            row = conn.execute("SELECT unit_price, bal_qty, amount FROM stock_master WHERE part_no = ?", (pno,)).fetchone()
            record_check(row is not None, f"Valve {pno} ({info['name']}) exists in stock_master")
            if row:
                upr, bqty, amt = row
                record_check(upr == info['price'], f"Valve {pno} stock_master unit_price == {info['price']}", f"got {upr}")
                if bqty > 0:
                    record_check(abs(amt - (upr * bqty)) < 0.01, f"Valve {pno} stock_master amount is ledger-clean (amt == {upr} * {bqty})")

    # 2. Baseline JSON Checks
    with open(BASELINE_JSON_PATH, "r", encoding="utf-8") as f:
        bl = json.load(f)
    pb = bl.get('price_book', {})
    gs = bl.get('global_stock', {})
    for pno, info in valves.items():
        record_check(pno in pb, f"Valve {pno} exists in baseline price_book")
        if pno in pb:
            record_check(pb[pno].get('price') == info['price'], f"Valve {pno} price_book price == {info['price']}", f"got {pb[pno].get('price')}")
        if pno in gs:
            record_check(gs[pno].get('unit_price') == info['price'], f"Valve {pno} global_stock unit_price == {info['price']}", f"got {gs[pno].get('unit_price')}")

    # 3. Direct Search Stress Test (Exact, whitespace, lowercase, prefix, and wildcard)
    for pno, info in valves.items():
        search_variants = [pno, f"  {pno}  ", pno.lower()]
        for query in search_variants:
            df = search_stock_global(query)
            match_row = df[df['part_no'] == pno]
            record_check(not match_row.empty, f"Direct search '{query}' returns valve {pno}")
            if not match_row.empty:
                res_pr = int(match_row.iloc[0]['price'])
                record_check(res_pr == info['price'], f"Direct search '{query}' price == {info['price']}", f"got {res_pr}")

    # 4. Multi-Model Resolution Checks across Tonnages
    # 3/8" valve on 1.0T models
    models_10 = ["GS-12PITH11W", "GS-12CITH11W", "GS-12PITH1W", "GS-12ZITH1W", "ES-12PITH"]
    for m in models_10:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        record_check(vg is not None, f"Model {m} has valve group")
        if vg:
            v_38 = vg['primary']
            record_check(v_38['part_no'] == '71302395', f"{m} primary valve is 3/8\" (71302395)", f"got {v_38['part_no']}")
            record_check(v_38['price'] == 1500, f"{m} 3/8\" valve price == Rs. 1,500", f"got {v_38['price']}")

    # 1/4" valve on all models (1.0T, 1.5T, 2.0T, 3.0T)
    models_14 = [
        "GS-12PITH11W", "GS-12CITH11W", "GS-18PITH11W", "GS-18CITH12G",
        "GS-18ZITH1W-T3", "GS-18AITH23W-T3", "GS-24PITH11W", "GS-24CITH1",
        "GF-24CB", "GF-36TFIH"
    ]
    for m in models_14:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        if vg:
            all_v = [vg['primary']] + vg['alternatives']
            v_14 = next((v for v in all_v if v['part_no'] == '7130239'), None)
            record_check(v_14 is not None, f"{m} includes 1/4\" valve (7130239)")
            if v_14:
                record_check(v_14['price'] == 1600, f"{m} 1/4\" valve price == Rs. 1,600", f"got {v_14['price']}")

    # 1/2" valve on 1.5T models
    models_15 = ["GS-18PITH11W", "GS-18CITH12G", "GS-18ZITH1W-T3", "GS-18AITH23W-T3", "GS-18FITH", "GS-18VITH"]
    for m in models_15:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        if vg:
            v_12 = vg['primary']
            record_check(v_12['part_no'] == '7133774', f"{m} primary valve is 1/2\" (7133774)", f"got {v_12['part_no']}")
            record_check(v_12['price'] == 2100, f"{m} 1/2\" valve price == Rs. 2,100", f"got {v_12['price']}")

    # 5/8" valve on 2.0T and 3.0T models
    models_58 = ["GS-24PITH11W", "GS-24CITH1", "GS-24ISH", "GF-24CB", "GF-36TFIH", "GF-36TF"]
    for m in models_58:
        res = fetch_tiered_compatible_parts(m)
        vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        if vg:
            v_58 = vg['primary']
            record_check(v_58['part_no'] == '7133844', f"{m} primary valve is 5/8\" (7133844)", f"got {v_58['part_no']}")
            record_check(v_58['price'] == 2200, f"{m} 5/8\" valve price == Rs. 2,200", f"got {v_58['price']}")

def test_seven_evaporator_pricing():
    print("\n" + "="*80)
    print("CHALLENGE 2: All 7 Official Reference Evaporator Prices (58k, 26k, 30k, 70k, 72k, 75k, 66k)")
    print("="*80)

    official_evaps = [
        {"model": "GF-36TFIH",       "pno": "11001000602", "price": 58000, "desc": "3.0 Ton Floor Standing"},
        {"model": "GS-18PITH1W",     "pno": "11001060868", "price": 26000, "desc": "1.5 Ton Split AC PITH"},
        {"model": "GS-18AITH23W-T3", "pno": "11001062414", "price": 30000, "desc": "1.5 Ton Split AC AITH-T3"},
        {"model": "GF-48FW",         "pno": "1004169",     "price": 70000, "desc": "4.0 Ton Floor Standing FW"},
        {"model": "GF-24ISH",        "pno": "11001060092", "price": 72000, "desc": "2.0 Ton Floor Standing ISH"},
        {"model": "GF-48TF",         "pno": "11001060521", "price": 75000, "desc": "4.0 Ton Floor Standing TF"},
        {"model": "GF-24CB",         "pno": "100404401",   "price": 66000, "desc": "2.0 Ton Floor Standing CB"}
    ]

    with get_connection() as conn:
        for item in official_evaps:
            m = item['model']
            pno = item['pno']
            exp_pr = item['price']
            desc = item['desc']

            # 1. DB stock_master check
            sm_row = conn.execute("SELECT unit_price FROM stock_master WHERE part_no = ?", (pno,)).fetchone()
            record_check(sm_row is not None, f"Evaporator {pno} ({desc}) exists in stock_master")
            if sm_row:
                record_check(sm_row[0] == exp_pr, f"Evaporator {pno} stock_master price == Rs. {exp_pr:,}", f"got {sm_row[0]}")

            # 2. DB parts_master check for the designated model
            pm_row = conn.execute("SELECT price FROM parts_master WHERE model = ? AND part_no = ?", (m, pno)).fetchone()
            record_check(pm_row is not None, f"Evaporator {pno} exists in parts_master for model {m}")
            if pm_row:
                record_check(pm_row[0] == exp_pr, f"Evaporator {pno} parts_master price == Rs. {exp_pr:,}", f"got {pm_row[0]}")

            # 3. Direct Stock Search check (whitespace and casing variants)
            for q in [pno, f"  {pno}  "]:
                df = search_stock_global(q)
                m_row = df[df['part_no'] == pno]
                record_check(not m_row.empty, f"Direct search '{q}' finds {pno}")
                if not m_row.empty:
                    d_price = int(m_row.iloc[0]['price'])
                    record_check(d_price == exp_pr, f"Direct search '{q}' price == Rs. {exp_pr:,}", f"got {d_price}")

            # 4. Model Lookup check
            res = fetch_tiered_compatible_parts(m)
            egrp = next((g for g in res['role_groups'] if "Evaporator" in g['group_title']), None)
            record_check(egrp is not None, f"Model {m} has Evaporator group")
            if egrp:
                pri = egrp['primary']
                record_check(pri['part_no'] == pno, f"Model {m} primary evaporator is {pno}", f"got {pri['part_no']}")
                record_check(pri['price'] == exp_pr, f"Model {m} primary evaporator price == Rs. {exp_pr:,}", f"got {pri['price']}")

                # 5. Price consistency (Model Price == Direct Search Price)
                record_check(pri['price'] == d_price, f"Model {m} evaporator price matches direct search price (Rs. {exp_pr:,})")

def test_gf36tfih_complete_isolation():
    print("\n" + "="*80)
    print("CHALLENGE 3: GF-36TFIH Floor Standing Complete Isolation & Zero Contamination")
    print("="*80)

    # Test with normal and adversarial input variants
    model_variants = ["GF-36TFIH", "  GF-36TFIH  ", "gf-36tfih", "  gf-36tfih  "]
    for m in model_variants:
        res = fetch_tiered_compatible_parts(m)
        meta = res.get('metadata', {})
        record_check(meta.get('category') == "Floor Standing AC", f"Model '{m}' classified as Floor Standing AC")
        record_check(meta.get('tonnage') == "3.0 Ton", f"Model '{m}' classified as 3.0 Ton")
        record_check(meta.get('series') == "TFIH", f"Model '{m}' classified as TFIH")

        # Evaporator Isolation
        evap_grp = next((g for g in res['role_groups'] if "Evaporator" in g['group_title']), None)
        record_check(evap_grp is not None, f"Model '{m}' has Evaporator group")
        if evap_grp:
            pri = evap_grp['primary']
            record_check(pri['part_no'] == "11001000602", f"Model '{m}' primary evaporator is 11001000602", f"got {pri['part_no']}")
            record_check(pri['price'] == 58000, f"Model '{m}' evaporator price == Rs. 58,000", f"got {pri['price']}")
            record_check(len(evap_grp['alternatives']) == 0, f"Model '{m}' has 0 alternative evaporators", f"got {len(evap_grp['alternatives'])}")

        # Valve Isolation & Exact Dual Pairing
        valve_grp = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
        record_check(valve_grp is not None, f"Model '{m}' has Cut-off & Service Valves group")
        if valve_grp:
            pri_v = valve_grp['primary']
            record_check(pri_v['part_no'] == "7133844", f"Model '{m}' primary valve is 5/8\" (7133844)", f"got {pri_v['part_no']}")
            record_check(pri_v['role'] == "Cut-Off Valve (5/8\")", f"Model '{m}' primary valve role is 5/8\"", f"got {pri_v['role']}")
            record_check(pri_v['price'] == 2200, f"Model '{m}' primary valve price == Rs. 2,200", f"got {pri_v['price']}")

            record_check(len(valve_grp['alternatives']) == 1, f"Model '{m}' has exactly 1 alternative valve", f"got {len(valve_grp['alternatives'])}")
            if len(valve_grp['alternatives']) >= 1:
                alt_v = valve_grp['alternatives'][0]
                record_check(alt_v['part_no'] == "7130239", f"Model '{m}' alt valve is 1/4\" (7130239)", f"got {alt_v['part_no']}")
                record_check(alt_v['role'] == "Cut-Off Valve (1/4\")", f"Model '{m}' alt valve role is 1/4\"", f"got {alt_v['role']}")
                record_check(alt_v['price'] == 1600, f"Model '{m}' alt valve price == Rs. 1,600", f"got {alt_v['price']}")

        # Exhaustive Contamination Scan across all tiers & groups
        all_part_nos = set(
            [g['primary']['part_no'] for g in res['role_groups']] +
            [a['part_no'] for g in res['role_groups'] for a in g['alternatives']] +
            [p['part_no'] for p in res['tier1']] +
            [p['part_no'] for p in res['tier2']] +
            [p['part_no'] for p in res['tier3']]
        )

        forbidden_parts = [
            ("11001060092", "2.0T 24ISH Evaporator"),
            ("1004169",     "4.0T 48FW Evaporator"),
            ("11001060246", "4.0T 48FWITH Evaporator"),
            ("100404401",   "2.0T 24CB Evaporator"),
            ("11001060521", "4.0T 48TF Evaporator"),
            ("11001060868", "1.5T PITH Evaporator"),
            ("1002937LC",   "1.5T CITH Evaporator"),
            ("11001062414", "1.5T AITH/ZITH Evaporator"),
            ("71302395",    "1.0T 3/8\" Valve"),
            ("7133774",     "1.5T 1/2\" Valve")
        ]

        for bad_pno, bad_label in forbidden_parts:
            record_check(bad_pno not in all_part_nos, f"GF-36TFIH 0% contamination: {bad_label} ({bad_pno}) NOT present in any tier/group")

def test_universal_ac_dual_valve_pairing_and_zero_clutter():
    print("\n" + "="*80)
    print("CHALLENGE 4: Universal AC Dual Physical Valve Pairing & Zero Clutter")
    print("="*80)

    ac_test_models = [
        # 1.0 Ton models -> 3/8" (1500) + 1/4" (1600)
        ("GS-12PITH11W", "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-12CITH11W", "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-12PITH1W",  "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-12ZITH1W",  "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("ES-12PITH",    "1.0 Ton", "71302395", "Cut-Off Valve (3/8\")", 1500, "7130239", "Cut-Off Valve (1/4\")", 1600),
        # 1.5 Ton models -> 1/2" (2100) + 1/4" (1600)
        ("GS-18PITH11W",    "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", 2100, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-18CITH12G",    "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", 2100, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-18ZITH1W-T3",  "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", 2100, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-18AITH23W-T3", "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", 2100, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-18FITH",       "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", 2100, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-18VITH",       "1.5 Ton", "7133774", "Cut-Off Valve (1/2\")", 2100, "7130239", "Cut-Off Valve (1/4\")", 1600),
        # 2.0 Ton models -> 5/8" (2200) + 1/4" (1600)
        ("GS-24PITH11W", "2.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-24CITH1",   "2.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GS-24ISH",     "2.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GF-24CB",      "2.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "7130239", "Cut-Off Valve (1/4\")", 1600),
        # 3.0 Ton models -> 5/8" (2200) + 1/4" (1600)
        ("GF-36TFIH", "3.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "7130239", "Cut-Off Valve (1/4\")", 1600),
        ("GF-36TF",   "3.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "7130239", "Cut-Off Valve (1/4\")", 1600),
        # 4.0 Ton models -> 5/8" (2200) + 3/8" (1500)
        ("GF-48TF", "4.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "71302395", "Cut-Off Valve (3/8\")", 1500),
        ("GF-48FW", "4.0 Ton", "7133844", "Cut-Off Valve (5/8\")", 2200, "71302395", "Cut-Off Valve (3/8\")", 1500),
    ]

    for model, ton, exp_suc_pno, exp_suc_role, suc_pr, exp_liq_pno, exp_liq_role, liq_pr in ac_test_models:
        res = fetch_tiered_compatible_parts(model)
        vg_list = [g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']]
        record_check(len(vg_list) == 1, f"Model {model} has exactly 1 valve group")
        if vg_list:
            vg = vg_list[0]
            pri = vg['primary']
            record_check(pri['part_no'] == exp_suc_pno, f"{model} ({ton}) Suction part == {exp_suc_pno}", f"got {pri['part_no']}")
            record_check(pri['role'] == exp_suc_role, f"{model} ({ton}) Suction role == {exp_suc_role}", f"got {pri['role']}")
            record_check(pri['price'] == suc_pr, f"{model} ({ton}) Suction price == Rs. {suc_pr:,}", f"got {pri['price']}")

            record_check(len(vg['alternatives']) == 1, f"{model} ({ton}) has exactly 1 alternative liquid valve", f"got {len(vg['alternatives'])}")
            if len(vg['alternatives']) == 1:
                alt = vg['alternatives'][0]
                record_check(alt['part_no'] == exp_liq_pno, f"{model} ({ton}) Liquid part == {exp_liq_pno}", f"got {alt['part_no']}")
                record_check(alt['role'] == exp_liq_role, f"{model} ({ton}) Liquid role == {exp_liq_role}", f"got {alt['role']}")
                record_check(alt['price'] == liq_pr, f"{model} ({ton}) Liquid price == Rs. {liq_pr:,}", f"got {alt['price']}")

            # Clutter assertion: No extraneous valve roles allowed in the group
            group_roles = [pri['role']] + [a['role'] for a in vg['alternatives']]
            record_check(set(group_roles) == {exp_suc_role, exp_liq_role}, f"{model} ({ton}) ZERO CLUTTER: exactly physical pair present")

        # Tier 3 capacity constraints check
        t3 = res.get('tier3', [])
        for p in t3:
            r = p.get('role', '')
            pn = p.get('part_no', '')
            if ton == '1.0 Ton':
                record_check(r not in ["Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")"], f"{model} (1.0T) Tier 3 has no 1/2\" or 5/8\" valve ({pn})")
                record_check(pn not in ["7133774", "7133844"], f"{model} (1.0T) Tier 3 has no 7133774 or 7133844 ({pn})")
            elif ton == '1.5 Ton':
                record_check(r not in ["Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")"], f"{model} (1.5T) Tier 3 has no 3/8\" or 5/8\" valve ({pn})")
                record_check(pn not in ["71302395", "7133844"], f"{model} (1.5T) Tier 3 has no 71302395 or 7133844 ({pn})")
            elif ton in ['2.0 Ton', '3.0 Ton']:
                record_check(r not in ["Cut-Off Valve (3/8\")", "Cut-Off Valve (1/2\")"], f"{model} ({ton}) Tier 3 has no 3/8\" or 1/2\" valve ({pn})")
                record_check(pn not in ["71302395", "7133774"], f"{model} ({ton}) Tier 3 has no 71302395 or 7133774 ({pn})")
            elif ton in ['4.0 Ton', '5.0 Ton']:
                record_check(r not in ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")"], f"{model} ({ton}) Tier 3 has no 1/4\" or 1/2\" valve ({pn})")
                record_check(pn not in ["7130239", "7133774"], f"{model} ({ton}) Tier 3 has no 7130239 or 7133774 ({pn})")

def test_cross_category_isolation():
    print("\n" + "="*80)
    print("CHALLENGE 5: Cross-Category Isolation (0% AC Parts Leakage into Non-AC Appliances)")
    print("="*80)

    non_ac_categories = {
        "Refrigerator": ["GR-E8768G-CP1", "GR-E9000", "GR-B300"],
        "Washing Machine": ["EW-F1202DC", "WM-100", "EW-800"],
        "Water Dispenser": ["WD-E500", "WD-300"]
    }

    ac_valves = {'7130239', '71302395', '7133774', '7133844', '7135142', '7133474'}
    ac_evaps = {'11001000602', '11001060868', '11001062414', '1004169', '11001060092', '11001060521', '100404401', '1002937LC', '11001061842LC'}

    for cat_name, models in non_ac_categories.items():
        for m in models:
            res = fetch_tiered_compatible_parts(m)
            all_parts = res['tier1'] + res['tier2'] + res['tier3']
            all_pnos = {p['part_no'] for p in all_parts}
            all_roles = {p['role'] for p in all_parts}

            # Check 1: Absolutely zero AC cut-off valves in any tier
            for v_pno in ac_valves:
                record_check(v_pno not in all_pnos, f"Non-AC model {m} ({cat_name}) has NO AC valve {v_pno}")

            for r in all_roles:
                record_check("Cut-Off Valve" not in r, f"Non-AC model {m} ({cat_name}) has NO Cut-Off Valve role ({r})")

            # Check 2: Washing Machine must not have Evaporators or Refrigerant gas
            if cat_name == "Washing Machine":
                for r in all_roles:
                    record_check("Evaporator" not in r, f"Washing Machine {m} has NO Evaporator role ({r})")
                    record_check("Gas" not in r and "Refrigerant" not in r, f"Washing Machine {m} has NO Gas/Refrigerant role ({r})")

            # Check 3: Zero AC Evaporators in Refrigerator or Water Dispenser
            for evap_pno in ac_evaps:
                record_check(evap_pno not in all_pnos, f"Non-AC model {m} ({cat_name}) has NO AC Evaporator {evap_pno}")

def test_zero_pricing_immunity_and_ledger_cleanliness():
    print("\n" + "="*80)
    print("CHALLENGE 6: Zero-Pricing Immunity & Ledger Formula Audit")
    print("="*80)

    with get_connection() as conn:
        c = conn.cursor()

        # stock_master zero price check
        c.execute("SELECT count(*) FROM stock_master WHERE unit_price <= 0 OR unit_price IS NULL")
        sm_zero_cnt = c.fetchone()[0]
        record_check(sm_zero_cnt == 0, "stock_master has 0 zero or null prices", f"found {sm_zero_cnt}")

        # parts_master zero price check
        c.execute("SELECT count(*) FROM parts_master WHERE price <= 0 OR price IS NULL")
        pm_zero_cnt = c.fetchone()[0]
        record_check(pm_zero_cnt == 0, "parts_master has 0 zero or null prices", f"found {pm_zero_cnt}")

        # Ledger amount check: amount == unit_price * bal_qty
        c.execute("SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01")
        discrepancy_cnt = c.fetchone()[0]
        record_check(discrepancy_cnt == 0, "stock_master has 0 rows with legacy ledger amount discrepancy", f"found {discrepancy_cnt}")

    # Codebase ledger formula audit
    files_to_check = ["etl.py", "build_baseline.py", "database.py"]
    for fn in files_to_check:
        with open(fn, "r", encoding="utf-8") as f:
            content = f.read()
        record_check("AMOUNT / BAL_QTY" not in content, f"{fn} has zero occurrences of obsolete formula 'AMOUNT / BAL_QTY'")
        record_check("amount / bal_qty" not in content.lower(), f"{fn} has zero occurrences of 'amount / bal_qty'")

def test_hostile_inputs_and_edge_cases():
    print("\n" + "="*80)
    print("CHALLENGE 7: Hostile Inputs, SQL Tokens, Whitespace & Edge Cases")
    print("="*80)

    hostile_queries = [
        " 71302395 ", "   7130239   ", "\t7133774\n", "  evaporator  ",
        "valve", "VALVE", "VaLvE", "pcb", "Pcb", "EVAPORATOR",
        '3/8"', '1/4"', '1/2"', '5/8"', "Cut-Off", "Assy",
        "713023", "1100100", "PITH", "CITH",
        "%", "_", "'", "''", ";", "--", "\\", "   ", "",
        "NON_EXISTENT_PART_XYZ_99999", "1234567890987654321"
    ]

    for q in hostile_queries:
        df = search_stock_global(q)
        record_check(isinstance(df, pd.DataFrame), f"Search query '{q}' safely returns DataFrame")
        if not df.empty:
            record_check((df['price'] > 0).all(), f"Search query '{q}' results have strictly positive prices")

    hostile_models = [
        "  GS-18ZITH1W-T3  ", "gs-18zith1w-t3", "  gf-36tfih  ", "=GF-36TFIH=",
        "UNKNOWN-MODEL-999", "GS-99UNKNOWN-T1", "RANDOM_STRING_MODEL", "", "   "
    ]

    for m in hostile_models:
        res = fetch_tiered_compatible_parts(m)
        record_check(isinstance(res, dict), f"Model lookup for '{m}' safely returns dict")
        for p in res.get('compatible_parts', []):
            record_check(p.get('price', 0) > 0, f"Hostile model '{m}' part {p.get('part_no')} price > 0")

def main():
    print("=" * 80)
    print("STARTING INDEPENDENT ADVERSARIAL STRESS TEST HARNESS (M3 CHALLENGER 2)")
    print("=" * 80)

    test_target_valve_pricing()
    test_seven_evaporator_pricing()
    test_gf36tfih_complete_isolation()
    test_universal_ac_dual_valve_pairing_and_zero_clutter()
    test_cross_category_isolation()
    test_zero_pricing_immunity_and_ledger_cleanliness()
    test_hostile_inputs_and_edge_cases()

    print("\n" + "=" * 80)
    print(f"ADVERSARIAL STRESS HARNESS SUMMARY:")
    print(f"  TOTAL CHECKS:  {total_checks}")
    print(f"  PASSED CHECKS: {passed_checks}")
    print(f"  FAILED CHECKS: {failed_checks}")
    print("=" * 80)

    if failed_checks > 0:
        print("\nFAILURES DETECTED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n>>> ALL ADVERSARIAL STRESS CHECKS PASSED WITH ZERO FAILURES! <<<")
        sys.exit(0)

if __name__ == "__main__":
    main()
