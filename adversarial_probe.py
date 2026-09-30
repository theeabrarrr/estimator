# adversarial_probe.py
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import sqlite3
import pandas as pd
from database import fetch_tiered_compatible_parts, fetch_parts_and_models
from config import tokenize_appliance_model

print("=== ADVERSARIAL PROBE START ===")

# 1. Probe GF-36TFIH
print("\n--- PROBING GF-36TFIH ---")
res_36 = fetch_tiered_compatible_parts("GF-36TFIH")
tok_36 = res_36['meta']
print("GF-36TFIH Tokenized:", tok_36)
print("Role groups found:", [g['group_title'] for g in res_36['role_groups']])

evap_grp = next((g for g in res_36['role_groups'] if "Evaporator" in g['group_title']), None)
if evap_grp:
    print(f"Evaporator Primary: {evap_grp['primary']['part_no']} | {evap_grp['primary']['part_name']} | Rs. {evap_grp['primary']['price']}")
    print(f"Evaporator Alternatives count: {len(evap_grp['alternatives'])}")
    for alt in evap_grp['alternatives']:
        print(f"  Alt: {alt['part_no']} | {alt['part_name']} | Rs. {alt['price']}")
else:
    print("NO Evaporator group found!")

valves_grp = next((g for g in res_36['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
if valves_grp:
    print(f"Valves Primary: {valves_grp['primary']['part_no']} | {valves_grp['primary']['role']} | Rs. {valves_grp['primary']['price']}")
    print(f"Valves Alternatives count: {len(valves_grp['alternatives'])}")
    for alt in valves_grp['alternatives']:
        print(f"  Alt: {alt['part_no']} | {alt['role']} | Rs. {alt['price']}")
else:
    print("NO Valves group found!")

# 2. Probe valve pairing across multiple models
print("\n--- PROBING VALVE PAIRINGS ACROSS TONNAGES ---")
test_models = [
    # 1.0 Ton
    ("GS-12PITH11W", "1.0 Ton"),
    ("GS-12CITH11W", "1.0 Ton"),
    ("GS-12FITH1", "1.0 Ton"),
    ("GS-10PITH", "1.0 Ton"),
    ("GS-11CITH3F", "1.0 Ton"),
    # 1.5 Ton
    ("GS-18PITH11W", "1.5 Ton"),
    ("GS-18PITH1W", "1.5 Ton"),
    ("GS-18CITH12G", "1.5 Ton"),
    ("GS-18ZITH1W-T3", "1.5 Ton"),
    ("GS-18AITH23W-T3", "1.5 Ton"),
    ("GS-18VITH1", "1.5 Ton"),
    # 2.0 Ton
    ("GS-24PITH11W", "2.0 Ton"),
    ("GS-24CITH1", "2.0 Ton"),
    ("GS-24LITH11M", "2.0 Ton"),
    ("GF-24ISH", "2.0 Ton"),
    ("GF-24CB", "2.0 Ton"),
    # 3.0 Ton
    ("GF-36TFIH", "3.0 Ton"),
    ("GF-36TF", "3.0 Ton"),
    # 4.0 Ton
    ("GF-48TF", "4.0 Ton"),
    ("GF-48FW", "4.0 Ton"),
    ("GF-48FWITH", "4.0 Ton"),
]

for m, expected_ton in test_models:
    res = fetch_tiered_compatible_parts(m)
    actual_ton = res['meta']['tonnage']
    vg = next((g for g in res['role_groups'] if "Cut-off & Service Valves" in g['group_title']), None)
    if not vg:
        print(f"FAIL: {m} ({expected_ton}) has NO Cut-off & Service Valves group!")
        continue
    p = vg['primary']
    alts = vg['alternatives']
    alt_roles = [a['role'] for a in alts]
    alt_pnos = [a['part_no'] for a in alts]
    print(f"{m:16s} | {actual_ton:7s} | Primary: {p['part_no']} ({p['role']:21s}, Rs.{p['price']:5d}) | Alt: {alt_pnos} {alt_roles}")

print("=== ADVERSARIAL PROBE END ===")
