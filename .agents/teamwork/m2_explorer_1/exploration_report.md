# Milestone 2 Exploration Report: Multi-Tier Spare Parts Resolution Engine & Database Hygiene

**Explorer**: M2 Explorer 1  
**Date**: 2026-09-29  
**Status**: COMPLETE & READY FOR WORKER 2 IMPLEMENTATION  
**Target Systems**: `database.py`, `app.py`, `etl.py`, `config.py`, `test_system_verification.py`

---

## 1. Executive Summary & Objective

In Milestone 1, the Master Price Authority (`data/pdf_extracted_stock_report.csv` / `vp786.pdf`) was ingested into `dwp_service.db`, the legacy accounting ledger formula (`AMOUNT / BAL_QTY`) was purged, and the Triangular Ground-Truth Engine was established, passing all 14 tests in `test_system_verification.py`.

The objective of **Milestone 2 (Requirement R3 & F5-F8)** is to implement a clean, autonomous, 3-tier spare parts resolution engine and complete database hygiene:
1. **Tier 1 (Exact Model Match)**: Return genuine components historically replaced on this model or assigned to this model in the official catalog, priced at the official rate with 100% field descriptions.
2. **Tier 2 (Platform Series Match)**: Return platform-compatible components for the same series and capacity.
3. **Tier 3 (Store In-Stock Fallback)**: Return live in-stock store items with strict physical line/capacity constraints (e.g. 1.0T -> 3/8" + 1/4"; 1.5T -> 1/2" + 1/4"; 2.0T/3.0T -> 5/8" + 1/4"; 4.0T -> 5/8" + 3/8").
4. **Chassis & Model Authority / Zero Contamination**: Ensure 0% cross-category or cross-series leakage (Split AC vs Floor Standing vs Refrigerator vs Washing Machine vs Water Dispenser). Packaging cartons must remain strictly excluded from cooling/electrical roles.
5. **Database Hygiene**: Eliminate the remaining 452 non-catalog inventory rows in `stock_master` where `amount != unit_price * bal_qty`.
6. **UI Presentation (`app.py`)**: Deliver distinct badges (Gold for Tier 1, Blue for Tier 2, Green for Tier 3) and a multi-tier resolution summary banner.
7. **Verification**: Maintain 100% pass on existing 14 tests and provide new automated tests (Test 15 & 16) for Tier 3 resolution and zero ledger discrepancies.

---

## 2. Current Architecture & Codebase Audit

### 2.1 Audit of `database.py:fetch_tiered_compatible_parts`
- **Location**: `database.py` lines 123–426.
- **Current Observation**:
  - `fetch_tiered_compatible_parts` gathers Tier 1 parts (`baseline['models'][model_name]['parts']`) and direct stock model matches (`stock_master WHERE item_desc LIKE %model%`).
  - It gathers Tier 2 parts (`baseline['series'][series_key]`).
  - **Missing Tier 3 Implementation**: There is no general query or fallback for Tier 3 live in-stock items. Instead, lines 314–339 feature a hardcoded dictionary (`warehouse_stock_map`) specifically for AC valves, which only injects valves if suction or liquid valve is missing, and labels them incorrectly as `"Tier 1: Stock Inventory (Standard Valve)"` with `tier_code = 1`.
  - **Interface Contract Gap**: The function returns:
    ```python
    return {
        'model': selected_model,
        'meta': tok,
        'role_groups': structured_groups,
        'total_verified_jobs': total_verified_jobs,
        'total_parts_found': len(scored_parts)
    }
    ```
    It does not explicitly return the discrete lists `'tier1'`, `'tier2'`, `'tier3'`, or `'metadata'` specified in `PROJECT.md` §Interface Contracts (`database.py ↔ app.py`).
  - **Cross-Category Guardrail Gap**: In line 250–255 (`direct_stk_sql`), `stock_master` is queried for matching `item_desc` without filtering on `stock_master.category`. If a model token matches a description in a different appliance category, cross-category contamination could occur.

### 2.2 Audit of `stock_master` Database Hygiene
- **Observation**:
  - Running `SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01` returns **452 rows**.
  - **Root Cause**: In Milestone 1, `ingest_pdf_stock_catalog` correctly computed `amount = unit_price * bal_qty` for the 518 catalog parts. However, the other 452 rows in `stock_master` were initially ingested from `stock_inventory_latest.csv` (secondary inventory, LED TVs, washing machines, older stock), where `amount` was imported from the legacy ledger book column.
  - In `etl.py:bootstrap_master_data()` (lines 388–401), when `stock_master.unit_price` is updated from `price_book`, `amount` is never recomputed.

### 2.3 Audit of `app.py` UI Presentation
- **Location**: `app.py` lines 166–242.
- **Current Observation**:
  - `render_part_row` displays `tier_str` using a generic gray badge:
    `tier_badge = f'<span style="background-color:#F1F5F9; color:#475569; padding:2px 6px; border-radius:10px; font-size:0.70rem; margin-left:4px;">{tier_str}</span>'`
  - There is no visual distinction between Tier 1 (Genuine Exact Match), Tier 2 (Platform Series), and Tier 3 (Live Store Fallback).
  - There is no summary banner showing how many parts were resolved under Tier 1, Tier 2, and Tier 3.

### 2.4 Audit of Test Suites
- **`test_system_verification.py`**: All 14 tests pass successfully.
- **`test_adversarial_m1_challenger_2.py`**: All 6 challenge sections pass with 0 failures.
- Both test suites access `res['role_groups']` and `res['meta']`. Backward compatibility for these keys must be 100% preserved.

---

## 3. Technical Design: Multi-Tier Spare Parts Resolution Engine

### 3.1 Multi-Tier Resolution Definitions

| Tier | Name | Criteria / Authority | Origin Data Source | Pricing Authority | Tier Code & Badge |
|---|---|---|---|---|---|
| **Tier 1** | **Exact Model Match** | Genuine components historically replaced on this model or assigned to this model in official catalog | `baseline['models'][model]['parts']` + `stock_master` direct model matches | Official catalog retail price (`pdf_price`) or verified closed complaint rate | `tier_code: 1`<br>`⭐ Tier 1: Exact Model Verified` |
| **Tier 2** | **Platform Series Match** | Platform-compatible components for the same series and capacity | `baseline['series'][series_key]` | Official catalog retail price or series platform rate | `tier_code: 2`<br>`🔄 Tier 2: {series} Platform Series` |
| **Tier 3** | **Store In-Stock Fallback** | Live store in-stock items (`bal_qty > 0`) satisfying strict physical line/capacity constraints | Live `stock_master` (`bal_qty > 0`) matching category & physical capacity | `stock_master.unit_price` (official master rate) | `tier_code: 3`<br>`📦 Tier 3: Store In-Stock Fallback` |

### 3.2 Elimination of Hardcoded Valve Fallbacks
- In `database.py`, lines 314–339 currently contain `warehouse_stock_map` with hardcoded tuples.
- **Refactoring Strategy**:
  - Replace `warehouse_stock_map` with dynamic live store querying from `stock_master`.
  - For AC models (`Split AC`, `Floor Standing AC`), query `stock_master` for active cut-off valves matching the target tonnage pair:
    - 1.0 Ton: Suction = `71302395` (3/8", Rs. 1,500), Liquid = `7130239` (1/4", Rs. 1,600)
    - 1.5 Ton: Suction = `7133774` (1/2", Rs. 2,100), Liquid = `7130239` (1/4", Rs. 1,600)
    - 2.0 Ton / 3.0 Ton: Suction = `7133844` (5/8", Rs. 2,200), Liquid = `7130239` (1/4", Rs. 1,600)
    - 4.0 Ton / 5.0 Ton: Suction = `7133844` (5/8", Rs. 2,200), Liquid = `71302395` (3/8", Rs. 1,500)
  - If the model did not have historical valve replacements in Tier 1 or Tier 2, these live store valves are added under **Tier 3** (`tier_code: 3`, `tier: "Tier 3: Store In-Stock Fallback"`).
  - Price is retrieved directly from `stock_master.unit_price` (or `price_book`), ensuring zero hardcoding.

### 3.3 Dynamic Tier 3 Store In-Stock Fallback Discovery
When assembling candidate parts for any model:
1. Query `stock_master` for in-stock items (`bal_qty > 0`):
   - Category filtering:
     - `Split AC` -> `stock_master.category IN ('Split AC', 'SPLIT AC 2', 'T1 R410 DC Inverter Indoor Units')`
     - `Floor Standing AC` -> `stock_master.category = 'Floor Standing AC'`
     - `Refrigerator` -> `stock_master.category = 'Refrigerator'`
     - `Washing Machine` -> `stock_master.category IN ('Washing Machine', 'Spinner')`
     - `Water Dispenser` -> `stock_master.category IN ('Water Dispenser', 'Water Dispensor', 'Water Dispensors')`
2. Apply Strict Chassis Isolation:
   - Chassis-sensitive roles (`Evaporator Assembly`, `Outdoor Inverter PCB`, `Indoor Main PCB`, `Display Board`, `Cross Flow Fan`, `Front Panel`) are **never** populated across series or tonnages into Tier 3. They require exact chassis matching.
3. Exclude Packaging Cartons:
   - Keywords `['carton', 'caton', 'packing', 'tray', 'box', 'foam']` are classified as `Component Hardware` and never placed in cooling/electrical groups.
4. Non-valve generic roles (Capacitors, Universal Temperature Sensors, 4-Way Valve Coils, Stepping Motors, Common Hardware):
   - In-stock store items that match the category are included in `tier3` as fallback options for their respective functional groups if not already present in Tier 1 or Tier 2.
5. All Tier 3 items are labeled with:
   - `tier_code = 3`
   - `tier = "Tier 3: Store In-Stock Fallback"`
   - `score = 15` (Tier 1 scores 35–100, Tier 2 scores 20–35, Tier 3 scores 15)

### 3.4 Return Payload Specification (Interface Contract)
`fetch_tiered_compatible_parts` will return:
```python
{
    'model': selected_model,
    'meta': tok,
    'metadata': {
        **tok,
        'valve_pairing': get_tonnage_valve_pairing(tok.get('tonnage')) if tok.get('category') in ['Split AC', 'Floor Standing AC', 'Air Conditioner'] else None,
        'tier1_count': len(tier1_parts),
        'tier2_count': len(tier2_parts),
        'tier3_count': len(tier3_parts)
    },
    'tier1': tier1_parts,
    'tier2': tier2_parts,
    'tier3': tier3_parts,
    'role_groups': structured_groups,
    'total_verified_jobs': total_verified_jobs,
    'total_parts_found': len(tier1_parts) + len(tier2_parts) + len(tier3_parts)
}
```

---

## 4. Chassis & Model Authority / Zero Contamination

### 4.1 Cross-Category Zero Leakage Rules
1. **Split AC vs Floor Standing AC**:
   - `GF-36TFIH` returns ONLY 3.0T Evaporator `11001000602`, 5/8" Suction `7133844`, and 1/4" Liquid `7130239`.
   - Never leak 2.0T `11001060092` (24ISH) or 4.0T `1004169` (48FW) into 3.0T.
2. **Refrigerators**:
   - Return only Refrigerator components (R-600 compressors, defrosters, ref sensors). 0% AC evaporators, valves, or PCBs.
3. **Washing Machines**:
   - Return only Washing Machine components (inlet valves, gear boxes, pulsators, drain motors, wash capacitors). 0% AC refrigerant valves or evaporators.
4. **Water Dispensers**:
   - Return only Water Dispenser components (cold tanks, dispenser taps, R-134a compressors, thermostats). 0% AC valves or evaporators.
5. **Direct Stock SQL Guardrail**:
   - In `direct_stk_sql`, add category constraint:
     `AND (category = ? OR category IN (...))` matching the model's tokenized category.

### 4.2 Packaging Carton Exclusion
- In `config.py:classify_component_role`, packaging tokens `['carton', 'caton', 'packing', 'tray', 'support', 'bracket', 'foam', 'box']` are mapped to `"Component Hardware"`.
- In `fetch_tiered_compatible_parts`, items classified as `"Component Hardware"` must never be placed into `"❄️ Evaporator Assemblies"`, `"⚡ Outdoor Inverter PCBs"`, or `"🔩 Cut-off & Service Valves"`.

---

## 5. Strict Valve Physical Pairing & Capacity Constraints

### 5.1 Physical Line Rules Matrix
| Tonnage Bracket | Applicable Models | Suction Gas Valve (Primary #1) | Liquid Valve (Alternative #2) | Prohibited Valve Sizes (0% Leakage) |
|---|---|---|---|---|
| **1.0 Ton** | GS-12PITH11W, GS-12CITH11W, ES-12 | `71302395` (3/8", Rs. 1,500) | `7130239` (1/4", Rs. 1,600) | 1/2", 5/8" |
| **1.5 Ton** | GS-18PITH11W, GS-18CITH12G, GS-18ZITH1W-T3, ES-18 | `7133774` (1/2", Rs. 2,100) | `7130239` (1/4", Rs. 1,600) | 3/8", 5/8" |
| **2.0 Ton** | GS-24PITH11W, GS-24CITH1, GF-24ISH, GF-24CB | `7133844` (5/8", Rs. 2,200) | `7130239` (1/4", Rs. 1,600) | 3/8", 1/2" |
| **3.0 Ton** | GF-36TFIH, GF-36TF | `7133844` (5/8", Rs. 2,200) | `7130239` (1/4", Rs. 1,600) | 3/8", 1/2" |
| **4.0 Ton / 5.0 Ton** | GF-48FW, GF-48TF, GF-48FWITH, GF-60 | `7133844` (5/8", Rs. 2,200) | `71302395` (3/8", Rs. 1,500) | 1/4", 1/2" |

### 5.2 Ordering Rule
- Within the `"🔩 Cut-off & Service Valves"` group:
  - **Primary Item (#1)**: Suction Valve (larger line: 3/8" for 1.0T, 1/2" for 1.5T, 5/8" for 2.0T–5.0T).
  - **Alternative Item (#2)**: Liquid Valve (smaller line: 1/4" for 1.0T–3.0T, 3/8" for 4.0T–5.0T).
  - No extraneous valve items in this group.

---

## 6. Database Hygiene Plan: Eliminating 452 Ledger Amount Discrepancies

### 6.1 Root Cause
When secondary stock files were initially ingested, `amount` was populated from the CSV's ledger valuation instead of `unit_price * bal_qty`. 452 non-catalog inventory rows currently hold obsolete values.

### 6.2 Recommended SQL Fix for Worker 2
Add the following hygiene update to `etl.py:bootstrap_master_data()` and `database.py:init_db_schema()`:
```python
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE stock_master 
        SET amount = ROUND(unit_price * bal_qty, 2)
        WHERE bal_qty > 0
    """)
    cursor.execute("""
        UPDATE stock_master 
        SET amount = 0.0
        WHERE bal_qty <= 0
    """)
```
### 6.3 Ingestion Pipeline Guardrail
In `etl.py:ingest_stock_file` (lines 316–318), ensure:
```python
df['unit_price'] = df.apply(calculate_clean_unit_price, axis=1)
df['amount'] = df.apply(lambda r: float(round(r['unit_price'] * r['bal_qty'], 2)) if r['bal_qty'] > 0 else 0.0, axis=1)
```
This guarantees that any future uploaded stock files automatically maintain `amount = unit_price * bal_qty`.

---

## 7. UI Presentation Design (`app.py`)

### 7.1 Tier Badges Styling (CSS)
In `app.py` CSS section (around line 65):
```css
/* Multi-Tier Resolution Badges */
.badge-tier-1 { background-color: #FEF3C7; color: #92400E; padding: 2px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 700; border: 1px solid #FCD34D; display: inline-block; margin-left: 4px; }
.badge-tier-2 { background-color: #EFF6FF; color: #1D4ED8; padding: 2px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 600; border: 1px solid #BFDBFE; display: inline-block; margin-left: 4px; }
.badge-tier-3 { background-color: #F0FDF4; color: #166534; padding: 2px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 600; border: 1px solid #BBF7D0; display: inline-block; margin-left: 4px; }
```

### 7.2 Multi-Tier Resolution Summary Banner
In `app.py` line 176 (right after the model info banner):
```python
t1_count = len(tiered_data.get('tier1', []))
t2_count = len(tiered_data.get('tier2', []))
t3_count = len(tiered_data.get('tier3', []))

col_t1, col_t2, col_t3 = st.columns(3)
with col_t1:
    st.markdown(f"""
    <div style="background:#FFFBEB; border:1px solid #FCD34D; border-radius:6px; padding:6px 10px; text-align:center;">
        <span style="color:#92400E; font-weight:700; font-size:0.78rem;">⭐ Tier 1: Exact Model</span><br>
        <span style="font-size:1.15rem; font-weight:800; color:#B45309;">{t1_count} parts</span>
    </div>
    """, unsafe_allow_html=True)
with col_t2:
    st.markdown(f"""
    <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:6px; padding:6px 10px; text-align:center;">
        <span style="color:#1D4ED8; font-weight:700; font-size:0.78rem;">🔄 Tier 2: Series Platform</span><br>
        <span style="font-size:1.15rem; font-weight:800; color:#2563EB;">{t2_count} parts</span>
    </div>
    """, unsafe_allow_html=True)
with col_t3:
    st.markdown(f"""
    <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-radius:6px; padding:6px 10px; text-align:center;">
        <span style="color:#166534; font-weight:700; font-size:0.78rem;">📦 Tier 3: Store Fallback</span><br>
        <span style="font-size:1.15rem; font-weight:800; color:#15803D;">{t3_count} parts</span>
    </div>
    """, unsafe_allow_html=True)
```

### 7.3 Badge Rendering in `render_part_row`
In `app.py` lines 189–200:
```python
t_code = part.get('tier_code', 1)
tier_str = part.get('tier', '')
if t_code == 1:
    tier_badge = f'<span class="badge-tier-1">⭐ {tier_str}</span>'
elif t_code == 2:
    tier_badge = f'<span class="badge-tier-2">🔄 {tier_str}</span>'
else:
    tier_badge = f'<span class="badge-tier-3">📦 {tier_str}</span>'
```

---

## 8. Verification & Test Plan

### 8.1 Regression Check
Worker 2 must verify that all 14 existing tests in `test_system_verification.py` continue to pass with 0 errors.

### 8.2 New Milestone 2 Tests to Add to `test_system_verification.py`

#### TEST 15: Multi-Tier Resolution Contract & Tier Integrity
- Verify that calling `fetch_tiered_compatible_parts(model)` returns `'tier1'`, `'tier2'`, `'tier3'`, `'metadata'`, and `'role_groups'`.
- Verify that every item in `tier1` has `tier_code == 1`.
- Verify that every item in `tier2` has `tier_code == 2`.
- Verify that every item in `tier3` has `tier_code == 3` and `bal_qty > 0`.
- Verify across models: `GS-18PITH11W`, `GS-12PITH11W`, `GF-36TFIH`, `GR-E8768G-CP1`, `EW-F1202DC`.

#### TEST 16: Zero Ledger Discrepancy & Tier 3 Physical Line Strictness
- Assert `SELECT count(*) FROM stock_master WHERE bal_qty > 0 AND ABS(amount - (unit_price * bal_qty)) > 0.01` is strictly **0**.
- Verify that for any AC model in Tier 3:
  - 1.0T models contain 0% 1/2" or 5/8" valves.
  - 1.5T models contain 0% 3/8" or 5/8" valves.
  - 2.0T/3.0T models contain 0% 3/8" or 1/2" valves.
  - 4.0T models contain 0% 1/4" or 1/2" valves.
- Verify that Refrigerator and Washing Machine models contain 0% AC evaporators and 0% AC service valves in any tier.

---

## 9. Line-by-Line Implementation Recommendations for Worker 2

### Target File 1: `database.py`
1. **Lines 181–243**: Collect Tier 1 (`tier1_parts`) from `baseline['models'][model_name]['parts']`, setting `tier_code = 1`, `tier = "Tier 1: Exact Model Verified"`.
2. **Lines 244–286**: When querying `direct_stk_sql`, add category filter: `category = tok['category']` (or category compatible). Add matched items to `tier1_parts`.
3. **Lines 215–243**: Collect Tier 2 (`tier2_parts`) from `baseline['series'][series_key]`, excluding part numbers already in `tier1_parts`. Set `tier_code = 2`, `tier = f"Tier 2: {tok['series']} Series Platform"`.
4. **Lines 287–340 (New Tier 3 Collection)**:
   - Query `stock_master` for active stock (`bal_qty > 0`) matching the category.
   - For AC models: filter valves using `is_valve_tonnage_compatible`. Exclude chassis-sensitive roles (Evaporators, Inverter PCBs) unless marked universal.
   - For non-AC models: include matching category parts (sensors, capacitors, inlet valves, motors) excluding AC parts.
   - Set `tier_code = 3`, `tier = "Tier 3: Store In-Stock Fallback"`, `score = 15`.
   - Add to `tier3_parts`.
5. **Lines 341–392 (Valve Pairing Refactor)**:
   - Discard the hardcoded `warehouse_stock_map`.
   - Look up the suction and liquid valve part numbers for the model's tonnage from `stock_master` / `live_stock_map`.
   - Ensure Suction Valve is Primary (#1) and Liquid Valve is Alternative (#2).
6. **Lines 420–427 (Return Dictionary)**:
   - Return `tier1`, `tier2`, `tier3`, `metadata`, `meta`, `role_groups`, `total_verified_jobs`, `total_parts_found`.

### Target File 2: `etl.py`
1. **Lines 398–401 (`bootstrap_master_data`)**:
   - Immediately following the `UPDATE stock_master SET unit_price = ?` loop, add:
     ```python
     cursor.execute("UPDATE stock_master SET amount = ROUND(unit_price * bal_qty, 2) WHERE bal_qty > 0")
     cursor.execute("UPDATE stock_master SET amount = 0.0 WHERE bal_qty <= 0")
     ```
2. **Lines 317–318 (`ingest_stock_file`)**:
   - Ensure `amount = round(unit_price * bal_qty, 2)`.

### Target File 3: `app.py`
1. **Lines 50–65**: Add `.badge-tier-1`, `.badge-tier-2`, `.badge-tier-3` CSS classes.
2. **Line 176**: Add 3-column metric cards for Tier 1, Tier 2, and Tier 3 part counts.
3. **Lines 189–200 (`render_part_row`)**: Render badge based on `part.get('tier_code')`.

### Target File 4: `test_system_verification.py`
1. Add `[TEST 15] Testing Multi-Tier Resolution Contract & Tier Structure Integrity...`
2. Add `[TEST 16] Testing Tier 3 Physical Line & Capacity Strict Filtering & Zero Cross-Contamination...`
3. Update `TEST 14.1` to assert that ledger amount discrepancy count is strictly 0.

---

## 10. Conclusion & Handoff Readiness
All technical investigations for Milestone 2 are complete. The requirements, root causes, constraints, and exact line-by-line implementation strategy are established. Worker 2 can implement these modifications cleanly and reliably.
