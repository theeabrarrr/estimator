# Milestone 1 Data Foundation Investigation & Ingestion Architecture Handoff

**Handoff Type:** Hard (Task complete)  
**Author:** M1 Explorer 1 (`m1_explorer_1`)  
**Target Milestone:** Milestone 1 — Official Catalog Ingestion & Triangular Ground-Truth Engine  
**Recipient:** Orchestrator (`orchestrator_1`) / Worker (`m1_worker_1`)  
**Date:** September 29, 2026  

---

## 1. Observation

1. **Official PDF Catalog Asset**:
   - Path: `c:\Users\PC\Desktop\estimator\data\pdf_extracted_stock_report.csv`
   - Row count: 531 data rows across 49 pages from Store 786 (Karachi Store).
   - Unique part numbers: Exactly 518 unique hardware part numbers (`df['part_no'].nunique() == 518`).
   - Unique primary models: 193 models (`df['model'].nunique() == 193`).
   - Model-part unique pairings: 524 pairs (`df[['model', 'part_no']].drop_duplicates().shape[0] == 524`).
   - Price range: Rs. 25.0 to Rs. 99,500.0 with 0 nulls and 0 non-positive prices.
   - Ten part numbers have duplicate entries across bins: `0305010102`, `0305010103`, `11230002000152`, `15010400000102`, `15010406008801`, `1521200606`, `1521212901`, `35060059`, `7130239`, `GR35-E77610089`.

2. **Current Codebase Audit**:
   - `grep_search` across `c:\Users\PC\Desktop\estimator` for `pdf_extracted_stock_report` returned **No results found** in any Python files.
   - `etl.py` lines 103–106:
     ```python
     df['calc_price'] = df.apply(
         lambda r: int(round(r['amount'] / r['bal_qty'])) if (r['bal_qty'] > 0 and r['amount'] > 0) else 0,
         axis=1
     )
     ```
   - `etl.py` lines 118–123:
     ```python
     known_price_overrides = {
         '71302395': 1500,
         '7130239': 1600,
         '7133844': 2200,
         '11001000602': 58000,
     }
     ```
   - `etl.py` lines 188–205 (`bootstrap_master_data`):
     Checks `if stock_count == 0:` before ingesting stock. When `dwp_service.db` already exists with legacy records (774 rows), stock ingestion is bypassed.
   - `database.py` lines 43–69 (`init_db_schema`):
     `parts_master` only has a primary key index on `(model, part_no)`. Lookup by `part_no` alone lacks an index.

3. **Current Database Inconsistencies in `dwp_service.db`**:
   - `stock_master` contains 774 rows.
   - **198 official catalog parts are completely missing** from `stock_master` (`pdf_pnos - sm_pnos == 198`), including 5 target evaporators:
     - `11001000602` (GF-36TFIH Evaporator, Rs. 58,000)
     - `1004169` (GF-48FW Evaporator, Rs. 70,000)
     - `11001060092` (GF-24ISH Evaporator, Rs. 72,000)
     - `11001060521` (GF-48TF Evaporator, Rs. 75,000)
     - `100404401` (GF-24CB Evaporator, Rs. 66,000)
   - Running `search_stock_global('1004169')` returns an `Empty DataFrame`.
   - **124 parts have price mismatches** between `pdf_extracted_stock_report.csv` and `stock_master`:
     - 1/2" Valve `7133774`: `stock_master` price is Rs. 1,600 (flawed legacy calculation), whereas official PDF price is Rs. 2,100.
     - R-410a Gas `0305010102`: `stock_master` price is Rs. 28,114, whereas official PDF price is Rs. 40,000.
     - R-32 Gas `0305010103`: `stock_master` price is Rs. 25,984, whereas official PDF price is Rs. 40,000.
     - Evaporator `11001060868`: Legacy inventory `amount` is Rs. 1,384,687.44 with `bal_qty` = 1 (flawed ledger cost ratio Rs. 1,384,687).

4. **Performance Benchmark**:
   - Executing a batch upsert of 518 parts into SQLite in WAL mode took **22.09 ms**.

---

## 2. Logic Chain

1. **Premise 1**: The User Request §R1 and Master Specification §F1 establish `data/pdf_extracted_stock_report.csv` (derived from `vp786.pdf`) as the Master Price Authority.
2. **Premise 2**: Since `data/pdf_extracted_stock_report.csv` contains all 518 unique parts and 524 model-part associations, and currently 198 parts are missing from `stock_master` and 124 prices are distorted, an autonomous ingestion pipeline (`ingest_pdf_stock_catalog`) is strictly required in `etl.py`.
3. **Premise 3**: In `stock_master`, `part_no` is the PRIMARY KEY. For parts appearing on multiple pages/bins (10 parts), taking `MAX(pdf_price)` resolves price conflicts safely, and taking `SUM(total_stock)` aggregates live warehouse stock. In `parts_master`, the primary key is `(model, part_no)`. Therefore, all 524 pairs can be inserted without collision, giving every model its genuine assigned part.
4. **Premise 4**: The accounting ledger formula `AMOUNT / BAL_QTY` in `etl.py` is the root cause of the 124 price distortions. By eliminating `AMOUNT / BAL_QTY` and `known_price_overrides`, and sourcing prices directly from `pdf_price` (with existing collection prices and role floors as clean fallbacks), zero accounting costs can leak into user estimates.
5. **Premise 5**: Because `bootstrap_master_data()` only loaded stock when `stock_count == 0`, existing databases were frozen in the flawed state. Since ingestion of 518 rows takes only 22 ms, running `ingest_pdf_stock_catalog()` unconditionally during `bootstrap_master_data()` guarantees 100% price synchronization at cold start and server launch.
6. **Premise 6**: Adding `CREATE INDEX IF NOT EXISTS idx_parts_pno ON parts_master(part_no)` and `CREATE INDEX IF NOT EXISTS idx_parts_model ON parts_master(model)` prevents full table scans during parts cross-enrichment and model lookups.

---

## 3. Caveats

- **Warehouse Items Outside PDF Catalog**: There are 452 parts in `data/stock_inventory_latest.csv` (mainly LED TV and Microwave Oven components) that do not appear in `vp786.pdf`. Our design preserves these items in `stock_master` during general stock load, but prices them safely via role price floors and collection history, while ensuring all 518 official cooling/appliance parts are strictly governed by `pdf_extracted_stock_report.csv`.
- **Negative Stock Values in PDF Report**: Some rows in the PDF report list negative stock (e.g. -3, -6) representing unallocated pending tickets in Store 786. In the UI and estimator, `in_stock` is determined by `bal_qty > 0`. Negative and zero balances are correctly flagged as out-of-stock without crashing the pipeline.

---

## 4. Conclusion

The technical strategy is fully developed, validated, and ready for Worker 1 to implement:
1. Implement `ingest_pdf_stock_catalog(csv_path=None) -> int` in `etl.py` to upsert 518 parts into `stock_master` and 524 pairs into `parts_master`.
2. Permanently eliminate `AMOUNT / BAL_QTY` and `known_price_overrides` from `ingest_stock_file()` in `etl.py`.
3. Add missing indexes in `database.py` (`idx_parts_pno`, `idx_parts_model`, `idx_stock_brand`).
4. Re-route `bootstrap_master_data()` in `etl.py` to unconditionally synchronize `data/pdf_extracted_stock_report.csv`.
5. Update `search_stock_global` and `fetch_tiered_compatible_parts` in `database.py` to prioritize `unit_price` from `stock_master`.

All line-by-line recommendations are documented in:
`c:\Users\PC\Desktop\estimator\.agents\teamwork\m1_explorer_1\exploration_report.md`.

---

## 5. Verification Method

Once Worker 1 applies the code modifications, execute the following commands in the workspace terminal:

```bash
# 1. Run the system verification regression test suite
python test_system_verification.py

# 2. Verify all 518 parts are indexed in stock_master with valid prices
python -c "import sqlite3; conn = sqlite3.connect('dwp_service.db'); cur = conn.cursor(); cur.execute('SELECT count(*) FROM stock_master WHERE unit_price > 0'); print('Stock master positive price count:', cur.fetchone()[0]); cur.execute('SELECT count(distinct part_no) FROM parts_master WHERE price > 0'); print('Parts master positive price count:', cur.fetchone()[0])"

# 3. Assert all 11 acceptance target parts match exact official prices
python -c "import sqlite3; conn = sqlite3.connect('dwp_service.db'); cur = conn.cursor(); pnos = ('71302395', '7130239', '7133774', '7133844', '11001000602', '11001060868', '11001062414', '1004169', '11001060092', '11001060521', '100404401'); cur.execute('SELECT part_no, unit_price FROM stock_master WHERE part_no IN ' + str(pnos)); rows = dict(cur.fetchall()); expected = {'71302395': 1500, '7130239': 1600, '7133774': 2100, '7133844': 2200, '11001000602': 58000, '11001060868': 26000, '11001062414': 30000, '1004169': 70000, '11001060092': 72000, '11001060521': 75000, '100404401': 66000}; assert rows == expected, f'Mismatch: {rows} vs {expected}'; print('ALL 11 TARGET PARTS VERIFIED AT OFFICIAL PRICES!')"

# 4. Invalidation condition:
# If test_system_verification.py fails or if any of the 11 target parts differ from expected, the handoff is invalid.
```
