# Handoff Report: Catalog Spec Miner

**Agent Folder:** `c:\Users\PC\Desktop\estimator\.agents\teamwork\spec_miner_survey_1`  
**Report Type:** Hard Handoff (Task Complete)  
**Deliverable Document:** `c:\Users\PC\Desktop\estimator\.agents\teamwork\spec_miner_survey_1\catalog_spec_report.md`  

---

## 1. Observation

1. **Master Catalog Files**:
   - `vp786.pdf`: Located at root `c:\Users\PC\Desktop\estimator\vp786.pdf`, size 52,203,363 bytes (~52.2 MB), 49 pages.
   - `data/pdf_extracted_stock_report.csv`: Located at `c:\Users\PC\Desktop\estimator\data\pdf_extracted_stock_report.csv`, size 46,865 bytes, 533 total lines.
   - Line 1 header: `part_no,item_desc,model,pdf_price,total_stock,page`.
   - Data rows: 531 rows (lines 2 to 532).
   - Duplicate count: Exactly 13 multi-entry rows (e.g. `0305010102` has 4 entries, `0305010103` has 3 entries, `7130239` has 2 entries, `11230002000152` has 2 entries, `15010400000102` has 2 entries, `15010406008801` has 2 entries, `1521200606` has 2 entries, `1521212901` has 2 entries, `GR35-E77610089` has 2 entries).
   - Unique parts: $531 - 13 = \mathbf{518}$ unique parts.

2. **Acceptance Criteria Target Parts Verification** in `data/pdf_extracted_stock_report.csv`:
   - 3/8" Valve: Line 458: `71302395,Cut-off valve 3/8 71302395 GS- 12PITH1W/O,GS-12PITH1W,1500.0,1,43` $\rightarrow$ Rs. 1,500.
   - 1/4" Valve: Line 7 & Line 456: `7130239,Cut-off Valve GS-24ECH10 7130239,GS-24ECH10,1600.0,15,1` and `7130239,Cut off Valve 1/4 GS-11CITH3F 7130239,GS-11CITH3F,1600.0,-6,41` $\rightarrow$ Rs. 1,600.
   - 1/2" Valve: Line 460: `7133774,Cut Off Valve Assy 1/2 7133774 GS- 18VITH1,GS-18VITH1,2100.0,6,43` $\rightarrow$ Rs. 2,100.
   - 5/8" Valve: Line 461: `7133844,Cutt Off Valve 5/8 24LITH11M 7133844,GS-24LITH11M,2200.0,-6,43` $\rightarrow$ Rs. 2,200.
   - Evaporator GF-36TFIH: Line 64: `11001000602,Evaporator Assy GF-36TFIH 11001000602,GF-36TFIH,58000.0,0,5` $\rightarrow$ Rs. 58,000.
   - Evaporator GS-18PITH1W: Line 72: `11001060868,Evaporator Assy GS-18PITH1W 11001060868,GS-18PITH1W,26000.0,48,5` $\rightarrow$ Rs. 26,000.
   - Evaporator GS-18AITH23W-T3: Line 78: `11001062414,Evaporator Assy GS-18AITH23W-T3 / GS-18AITH21W-T3/ GS-18CM11 / GS- 18ZITH 11001062414,GS-18AITH23W-T3,30000.0,-31,7` $\rightarrow$ Rs. 30,000.
   - Evaporator GF-48FW: Line 46: `1004169,Evaporater Assy 48FW 1004169,GF-48FW,70000.0,-3,3` $\rightarrow$ Rs. 70,000.
   - Evaporator GF-24ISH: Line 69: `11001060092,Evaporator Assy 11001060092 24ISH,GF-24ISH,72000.0,-1,5` $\rightarrow$ Rs. 72,000.
   - Evaporator GF-48TF: Line 71: `11001060521,Evaporator Assy GF-48TF 11001060521,GF-48TF,75000.0,2,5` $\rightarrow$ Rs. 75,000.
   - Evaporator GF-24CB: Line 45: `100404401,Evaporator Assy 24CB/ 24TFIH 1100100218 / 100404401,GF-24CB,66000.0,0,3` $\rightarrow$ Rs. 66,000.

3. **Legacy Formula & Database Observations**:
   - `etl.py` lines 103–106: `df['calc_price'] = df.apply(lambda r: int(round(r['amount'] / r['bal_qty'])) if (r['bal_qty'] > 0 and r['amount'] > 0) else 0, axis=1)`.
   - `build_baseline.py` line 44: `unit_calc = int(round(amt / bal)) if (bal > 0 and amt > 0) else 0`.
   - `data/stock_inventory_latest.csv` Line 403: Part `11001060868` (GS-18PITH1W Evaporator) has `AMOUNT=1,384,687.44` with `BAL_QTY=1`, computing a distorted ledger ratio of **Rs. 1,384,687** instead of the official **Rs. 26,000**.
   - `data/stock_inventory_latest.csv` Line 549: Part `7133844` (5/8" Valve) has `AMOUNT=171,768.01` with `BAL_QTY=5`, computing **Rs. 34,354** instead of the official **Rs. 2,200**.
   - `data/stock_inventory_latest.csv` Line 361: Part `7133774` (1/2" Valve) has `AMOUNT=532,433.41` with `BAL_QTY=20`, computing **Rs. 26,622** instead of the official **Rs. 2,100**.
   - `data/stock_inventory_latest.csv` Line 542: Part `7130239` (1/4" Valve) has `AMOUNT=87,676.74` with `BAL_QTY=15`, computing **Rs. 5,845** instead of the official **Rs. 1,600**.
   - `data/stock_inventory_latest.csv` was missing 5 floor standing evaporators (`11001000602`, `1004169`, `11001060092`, `11001060521`, `100404401`).
   - SQLite tables in `dwp_service.db`: `stock_master`, `parts_master`, `history_master`, `tech_performance_master`.

---

## 2. Logic Chain

1. **Premise 1**: The user request and acceptance criteria designate `vp786.pdf` (Store Wise Stock Report from 01-Jan-26 to 30-Sep-26) as the Master Price Authority containing 518 unique parts.
2. **Premise 2**: Direct inspection of `data/pdf_extracted_stock_report.csv` demonstrates that it contains 531 data rows, exactly 13 of which are multi-entry duplicates, yielding exactly 518 unique hardware parts.
3. **Premise 3**: Tracing all 11 target items (valves 71302395, 7130239, 7133774, 7133844 and evaporators 11001000602, 11001060868, 11001062414, 1004169, 11001060092, 11001060521, 100404401) shows a 100% exact match to the user acceptance criteria in both price and part number.
4. **Premise 4**: Tracing the legacy code shows that previous versions relied on `stock_inventory_latest.csv` and computed `AMOUNT / BAL_QTY`, leading to distorted runaway prices (e.g. Rs. 1.38M for GS-18PITH1W evaporator, Rs. 34.3k for 5/8" valve) and missing floor standing models. Temporary patches (`known_price_overrides` in `etl.py` and `build_baseline.py`) were applied as workarounds.
5. **Conclusion**: `data/pdf_extracted_stock_report.csv` must become the primary Master Price Authority for `stock_master` and `parts_master` across `etl.py`, `build_baseline.py`, and `database.py`.

---

## 3. Caveats

- In `data/pdf_extracted_stock_report.csv`, some `total_stock` values are negative (e.g., `-1`, `-31`). In ERP warehouse systems, negative stock indicates stock issued before receipt entries were finalized. The ingestion logic must maintain the integer stock for auditing but enforce `in_stock = bal_qty > 0` for catalog display and availability badges.
- `vp786.pdf` is 52 MB; the pre-extracted `data/pdf_extracted_stock_report.csv` provides clean structured access to all 518 parts without requiring continuous runtime binary PDF parsing.

---

## 4. Conclusion

Requirement R1 is fully mined and specified.
- Master catalog authority: `data/pdf_extracted_stock_report.csv` (extracted from `vp786.pdf`).
- Part count: Exactly 518 unique parts across 531 rows.
- Target parts and evaporators: 100% verified.
- Flawed ledger formula `AMOUNT / BAL_QTY` thoroughly analyzed and proven invalid for customer billing.
- Detailed report written to `catalog_spec_report.md`.

---

## 5. Verification Method

To independently verify these findings:
1. Inspect `data/pdf_extracted_stock_report.csv` line count and unique part numbers:
   - Header is line 1; lines 2 to 532 are 531 data rows.
   - Lines 7 and 456 contain `7130239` (1/4" Valve, Rs. 1,600).
   - Line 458 contains `71302395` (3/8" Valve, Rs. 1,500).
   - Line 460 contains `7133774` (1/2" Valve, Rs. 2,100).
   - Line 461 contains `7133844` (5/8" Valve, Rs. 2,200).
   - Line 64 contains `11001000602` (GF-36TFIH Evaporator, Rs. 58,000).
   - Line 72 contains `11001060868` (GS-18PITH1W Evaporator, Rs. 26,000).
   - Line 78 contains `11001062414` (GS-18AITH23W-T3 Evaporator, Rs. 30,000).
   - Line 46 contains `1004169` (GF-48FW Evaporator, Rs. 70,000).
   - Line 69 contains `11001060092` (GF-24ISH Evaporator, Rs. 72,000).
   - Line 71 contains `11001060521` (GF-48TF Evaporator, Rs. 75,000).
   - Line 45 contains `100404401` (GF-24CB Evaporator, Rs. 66,000).
2. Inspect `catalog_spec_report.md` at `c:\Users\PC\Desktop\estimator\.agents\teamwork\spec_miner_survey_1\catalog_spec_report.md`.
