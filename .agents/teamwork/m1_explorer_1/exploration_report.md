# Milestone 1 Technical Implementation Strategy & Exploration Report: R1 & R2 Data Foundation

**Document ID:** M1-EXP-R1-R2-001  
**Author:** M1 Explorer 1 (`m1_explorer_1`)  
**Target Milestone:** Milestone 1 — Official Catalog Ingestion & Triangular Ground-Truth Engine  
**Workspace:** `c:\Users\PC\Desktop\estimator`  
**Date:** September 29, 2026  

---

## Executive Summary

This report establishes the complete, production-grade technical implementation strategy for **Milestone 1 (Requirements R1 and R2 Data Foundation)**. It addresses the systematic ingestion of the executive-approved DWP Store-Wise Stock Report (`data/pdf_extracted_stock_report.csv`), the permanent eradication of the distorted accounting ledger valuation formula (`AMOUNT / BAL_QTY`), the schema indexing and cold-start bootstrap synchronization in `database.py` and `etl.py`, and provides explicit line-by-line implementation guidance for Worker 1.

### Core Discoveries & Baseline Metrics
1. **Catalog Source Audit (`data/pdf_extracted_stock_report.csv`)**:
   - Contains **531 data rows** across 49 pages of Store 786 (Karachi Store).
   - Resolves to exactly **518 unique hardware part numbers** and **193 unique appliance models**.
   - Price range: **Rs. 25 to Rs. 99,500** with **0 null prices** and **0 zero-prices**.
   - Contains all target acceptance parts: 3/8" Valve (Rs. 1,500), 1/4" Valve (Rs. 1,600), 1/2" Valve (Rs. 2,100), 5/8" Valve (Rs. 2,200), and all 7 target evaporators (GF-36TFIH = Rs. 58,000; GS-18PITH1W = Rs. 26,000; GS-18AITH23W-T3 = Rs. 30,000; GF-48FW = Rs. 70,000; GF-24ISH = Rs. 72,000; GF-48TF = Rs. 75,000; GF-24CB = Rs. 66,000).

2. **Current System State & Gaps in `dwp_service.db`**:
   - Currently, `dwp_service.db` contains 774 parts in `stock_master`.
   - **198 official catalog parts are completely missing** from `stock_master` (including evaporators `1004169`, `11001000602`, `11001060092`, `11001060521`, `100404401`). Consequently, direct search (`search_stock_global`) for `1004169` returns an empty dataframe.
   - For the 320 parts present in both the catalog and `stock_master`, **124 parts have severe price discrepancies** due to legacy accounting ledger calculations (`AMOUNT / BAL_QTY`), e.g., 1/2" Valve `7133774` has Rs. 1,600 instead of Rs. 2,100; R-410a gas has Rs. 28,114 instead of Rs. 40,000; and Evaporator `11001060868` had a ledger ratio of Rs. 1,384,687 (+5,225% distortion).
   - Ingestion of `data/pdf_extracted_stock_report.csv` is currently **completely absent** from the codebase (0 references in Python source files).
   - `bootstrap_master_data()` fails to synchronize the official catalog on cold start because it checks `if stock_count == 0:`, which is skipped if legacy records already exist.

---

## 1. Master Price Catalog Ingestion Design (`ingest_pdf_stock_catalog`)

### 1.1 Source Data Specification & Normalization Rules
Source file: `data/pdf_extracted_stock_report.csv`  
Standard Columns: `part_no`, `item_desc`, `model`, `pdf_price`, `total_stock`, `page`

```
Source CSV Row
  ├── part_no     ──► clean_val() ──► .upper() ──► Primary Key in stock_master
  ├── item_desc   ──► regex normalize spaces (GS- 18 -> GS-18) ──► Canonical Desc
  ├── model       ──► clean_val() ──► tokenize_appliance_model() ──► Brand, Cat, Ton
  ├── pdf_price   ──► float() ──► int(round()) ──► Official unit_price
  ├── total_stock ──► int() ──► live bal_qty
  └── page        ──► int() (source trace)
```

#### Field Normalization Rules:
1. **`part_no`**:
   - Must be read with `dtype=str` to preserve leading zeros (e.g. `00205200018`, `0305010101`).
   - Strip quotes, equals signs (`=`), leading/trailing whitespace, and cast to uppercase.
2. **`item_desc`**:
   - Normalize irregular spaces created during PDF OCR/extraction:
     `re.sub(r'\b(GS|GF|ES|EF|EW|GR|GW|WD|CX|EM)-\s+([0-9A-Za-z])', r'\1-\2', desc)`
   - Collapse multiple consecutive whitespace characters to a single space: `re.sub(r'\s+', ' ', desc).strip()`.
3. **`model`**:
   - Strip quotes, equals signs, whitespace, and cast to uppercase.
4. **`pdf_price`**:
   - Convert to `float`, then `int(round(price))`.
   - Validate `unit_price > 0`.
5. **`total_stock`**:
   - Convert to integer with `pd.to_numeric(errors='coerce').fillna(0).astype(int)`.
   - Maps directly to `bal_qty` in `stock_master`.

### 1.2 Duplicate Part Resolution Strategy (531 Rows -> 518 Unique Parts)
Across 531 rows, exactly 10 part numbers appear in multiple rows (13 duplicate entries):
- `0305010102` (R-410a Gas): 4 entries (ATTI & CO, Kaghan Chemicals, Kaghan Traders, S.A Khan Traders)
- `0305010103` (R-32 Gas): 3 entries
- `11230002000152` (Stepping Motor): 2 entries (ES-18DU01WG, ES-18GS01W)
- `15010400000102` (GF-36TFIH Fan Motor): 2 entries
- `15010406008801` (Brushless DC Motor): 2 entries (GS-18CM11, GS-24PIT10W)
- `1521200606` (Stepping Motor): 2 entries (GS-18PIT10W @ 1000, GS-18PITH2W @ 2000)
- `1521212901` (Stepping Motor MP24AA): 2 entries (GS-12ECH10, GS-11CITH3F)
- `35060059` (IGBT FGH40N60SMD): 2 entries (GS-18CITH11S, GS-18CITH1)
- `7130239` (1/4" Cut-off Valve): 2 entries (GS-24ECH10, GS-11CITH3F)
- `GR35-E77610089` (Temp Sensor): 2 entries (GR-E8768G-CW1)

#### Resolution Logic:
1. **For `parts_master` (Dual-Key `(model, part_no)` Table)**:
   - Every row in the CSV represents a valid model-to-part compatibility mapping!
   - Ingest **all 531 rows** (524 distinct `(model, part_no)` pairs) using:
     ```sql
     INSERT INTO parts_master (model, part_no, part_name, price)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(model, part_no) DO UPDATE SET
         price = excluded.price,
         part_name = excluded.part_name
     ```
   - This ensures that both `GS-24ECH10` and `GS-11CITH3F` link to genuine 1/4" Valve `7130239` at Rs. 1,600!
2. **For `stock_master` (Single-Key `part_no` Table)**:
   - Group the 531 rows by `part_no`:
     - **`unit_price`**: Take `MAX(pdf_price)`. (Ensures R-410a gas is Rs. 40,000, motor 1521200606 is Rs. 2,000).
     - **`bal_qty`**: Take `SUM(total_stock)` across warehouse bins.
     - **`item_desc`**: Select the longest, most detailed canonical description (`max(descriptions, key=len)`).
     - **`model`**: Select designated primary model (`first()`).
     - **`metadata tokenization`**: Call `tokenize_appliance_model(primary_model)` to extract `brand`, `category`, `capacity` (tonnage).
     - **`amount`**: Compute `unit_price * bal_qty` (if `bal_qty > 0` else `0.0`).
     - **`last_synced`**: Set to `'DWP Official Price Catalog (vp786.pdf)'`.

---

## 2. Elimination of Ledger Accounting Formula (`AMOUNT / BAL_QTY`)

### 2.1 The Mathematical Hazard
The legacy formula in `etl.py` and `build_baseline.py`:
$$\text{calc\_price} = \text{round}\left(\frac{\text{AMOUNT}}{\text{BAL\_QTY}}\right)$$
violates retail pricing principles because:
1. `AMOUNT` in ERP stores historical financial batch ledger cost pools, not customer unit selling prices.
2. When `BAL_QTY` dwindles to 1, ledger adjustments produce runaway price spikes (e.g. `11001060868` became Rs. 1,384,687).
3. When `BAL_QTY` is high, fractional FOB component landed costs leak without warranty, freight, duty, or retail margin.
4. Hardcoded overrides (`known_price_overrides = {'71302395': 1500, ...}`) were required as duct-tape patches.

### 2.2 Permanent Eradication Protocol in `etl.py`
1. **Delete** `df['calc_price'] = df.apply(lambda r: int(round(r['amount'] / r['bal_qty'])), axis=1)` from `ingest_stock_file()`.
2. **Delete** `known_price_overrides` dictionary from `etl.py`.
3. **Establish Official Master Authority**:
   When ingesting any stock file in `etl.py`:
   - Load `official_price_map` from `data/pdf_extracted_stock_report.csv`.
   - For each part:
     1. If `part_no in official_price_map`: `unit_price = official_price_map[part_no]`.
     2. Else if `part_no in existing_prices and existing_prices[part_no] > 0`: `unit_price = existing_prices[part_no]`.
     3. Else: `unit_price = get_role_price_floor(role, ton, cat)`.
4. **Re-anchor `amount`**:
   `df['amount'] = df.apply(lambda r: float(r['unit_price'] * r['bal_qty']) if r['bal_qty'] > 0 else 0.0, axis=1)`.
   The `amount` column now represents true live stock retail inventory value.

---

## 3. Database Schema, Indexing & Cold-Start Synchronization

### 3.1 Schema & Index Optimizations in `database.py`
Audit of `dwp_service.db` revealed that `parts_master` only possessed an index on `(model, part_no)`. Lookup by `part_no` alone (required by ETL cross-enrichment and price auditing) triggered a full-table scan of 5,595 rows.

#### Required DDL Updates in `init_db_schema()`:
```sql
-- Existing stock_master indexes
CREATE INDEX IF NOT EXISTS idx_stock_pno ON stock_master(part_no);
CREATE INDEX IF NOT EXISTS idx_stock_desc ON stock_master(item_desc);
CREATE INDEX IF NOT EXISTS idx_stock_cat ON stock_master(category);
CREATE INDEX IF NOT EXISTS idx_stock_brand ON stock_master(brand);

-- New parts_master indexes
CREATE INDEX IF NOT EXISTS idx_parts_pno ON parts_master(part_no);
CREATE INDEX IF NOT EXISTS idx_parts_model ON parts_master(model);

-- Existing history_master & performance indexes
CREATE INDEX IF NOT EXISTS idx_hist_search ON history_master(serial, phone, complaint_no);
CREATE INDEX IF NOT EXISTS idx_hist_model ON history_master(model);
CREATE INDEX IF NOT EXISTS idx_hist_closed ON history_master(closed_date);
CREATE INDEX IF NOT EXISTS idx_tp ON tech_performance_master(technician_name, status, closed_date);
```

### 3.2 Cold-Start Bootstrap Architecture in `etl.py`
The existing `bootstrap_master_data()` function contained a fatal logic bypass:
```python
# FLAW: If stock_master already has rows, official catalog is NEVER synced!
if stock_count == 0:
    latest_stock = find_latest_stock_file()
    if latest_stock:
        ingest_stock_file(latest_stock)
```

#### Redesigned Bootstrap Flow:
1. `init_db_schema()`: Create tables and indexes.
2. If `history_master` is empty and feedback report exists: Ingest feedback and collections.
3. If `stock_master` is empty and legacy stock file exists: Ingest legacy stock file (with new zero-ledger formula).
4. **Unconditional Catalog Synchronization**:
   Always execute `ingest_pdf_stock_catalog(OFFICIAL_STOCK_CSV_PATH)`!
   Benchmarked execution time on SQLite WAL mode: **22.09 milliseconds**.
   This guarantees that:
   - 100% of all 518 official parts are always present in `stock_master`.
   - 100% of official retail prices override any stale or corrupted values.
   - 100% of official model-part assignments exist in `parts_master`.
   - System starts up instantaneously without delay.

---

## 4. Query & Resolution Synchronization in `database.py`

### 4.1 Global Stock Search (`search_stock_global`)
In `database.py` lines 453–470:
Previously, `search_stock_global` was overriding `stock_master.unit_price` with `price_book` to bypass corrupted ledger costs.
Now that `stock_master` stores official executive prices:
- If `r['price'] > 0` (from `stock_master.unit_price`), return `r['price']` directly!
- Only fall back to `price_book` or role price floor if `r['price'] <= 0`.
- This ensures 100% consistency between direct stock search and model search.

### 4.2 Multi-Tier Resolution (`fetch_tiered_compatible_parts`)
In `fetch_tiered_compatible_parts`:
- In Tier 1 and Tier 2 candidate loops:
  `if pno in live_stock_map and live_stock_map[pno]['unit_price'] > 0: p_copy['price'] = live_stock_map[pno]['unit_price']`
  The live official price from `stock_master` takes absolute precedence.
- If a model in Tier 1 has designated parts in `parts_master` (from `data/pdf_extracted_stock_report.csv`), those parts are immediately accessible.

---

## 5. Exact Line-by-Line Code Recommendations for Worker 1

### 5.1 File: `config.py`
Add the official catalog path constant:
```python
# Insert around line 93 (near STOCK_CSV_PATH)
OFFICIAL_STOCK_CSV_PATH = os.path.join(BASE_DIR, "data", "pdf_extracted_stock_report.csv")
```

### 5.2 File: `database.py`
1. **In `init_db_schema()` (around line 69)**:
   Add indexes:
   ```python
   cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_brand ON stock_master(brand)")
   cursor.execute("CREATE INDEX IF NOT EXISTS idx_parts_pno ON parts_master(part_no)")
   cursor.execute("CREATE INDEX IF NOT EXISTS idx_parts_model ON parts_master(model)")
   ```
2. **In `fetch_tiered_compatible_parts()` (around lines 185-195 and 212-220)**:
   Ensure live stock official price has priority:
   ```python
   # Line 185:
   if pno in live_stock_map and live_stock_map[pno]['unit_price'] > 0:
       p_copy['price'] = live_stock_map[pno]['unit_price']
   elif p_copy.get('price', 0) <= 0:
       if pno in price_book and price_book[pno].get('price', 0) > 0:
           p_copy['price'] = int(price_book[pno]['price'])
       else:
           p_copy['price'] = baseline.get('category_floors', {}).get(p['role'], 26000 if 'Evaporator' in p['role'] else 1500)
   ```
3. **In `search_stock_global()` (around lines 457-470)**:
   Simplify `resolve_price()`:
   ```python
   def resolve_price(r):
       pr = int(r.get('price') or 0)
       if pr > 0:
           return pr
       pno = str(r['part_no']).upper()
       if pno in price_book and price_book[pno].get('price', 0) > 0:
           return int(price_book[pno]['price'])
       role = classify_component_role(r['part_name'], pno)
       floor = int(floors.get(role, 26000 if 'Evaporator' in role else 1500))
       return floor
   ```

### 5.3 File: `etl.py`
1. **Imports (lines 12–16)**:
   Update imports:
   ```python
   from config import (
       COLUMN_ALIASES, DEFAULT_FB_FILE, DEFAULT_COLL_FILE, STOCK_SEARCH_DIRS, STOCK_CSV_PATH,
       OFFICIAL_STOCK_CSV_PATH, classify_component_role, get_role_price_floor,
       tokenize_appliance_model
   )
   from database import get_connection, init_db_schema
   ```

2. **Implement `ingest_pdf_stock_catalog(csv_path=None)` (insert before `ingest_stock_file`)**:
   ```python
   def ingest_pdf_stock_catalog(csv_path=None):
       """
       Ingests the official DWP Store Wise Stock Report (vp786.pdf / data/pdf_extracted_stock_report.csv)
       directly into stock_master and parts_master.
       Establishes official retail selling prices (pdf_price) and store total_stock (bal_qty).
       Returns count of unique parts ingested.
       """
       init_db_schema()
       target_path = csv_path or OFFICIAL_STOCK_CSV_PATH
       if not target_path or not os.path.exists(target_path):
           return 0

       raw_df = safe_read(target_path)
       if raw_df.empty or 'part_no' not in raw_df.columns:
           return 0

       df = raw_df.copy()
       df['part_no'] = df['part_no'].apply(clean_val).str.upper()
       df = df[df['part_no'] != ''].copy()

       # Normalize descriptions & model
       def normalize_desc(s):
           val = clean_val(s)
           # Fix irregular spaces like GS- 18PITH1W -> GS-18PITH1W
           val = re.sub(r'\b(GS|GF|ES|EF|EW|GR|GW|WD|CX|EM)-\s+([0-9A-Za-z])', r'\1-\2', val)
           return re.sub(r'\s+', ' ', val).strip()

       df['item_desc'] = df['item_desc'].apply(normalize_desc)
       df['model'] = df['model'].apply(clean_val).str.upper()
       df['pdf_price'] = pd.to_numeric(df.get('pdf_price', 0), errors='coerce').fillna(0.0)
       df['total_stock'] = pd.to_numeric(df.get('total_stock', 0), errors='coerce').fillna(0).astype(int)

       now_str = datetime.now().strftime('%Y-%m-%d %I:%M %p')

       # 1. Populate parts_master with all model-part assignments (524 unique pairs)
       parts_rows = []
       for _, r in df.iterrows():
           m = r['model']
           pno = r['part_no']
           desc = r['item_desc']
           pr = int(round(float(r['pdf_price'])))
           if m and pno:
               parts_rows.append((m, pno, desc, pr))

       # 2. Aggregate 518 unique parts for stock_master
       agg_dict = {}
       for _, r in df.iterrows():
           pno = r['part_no']
           pr = int(round(float(r['pdf_price'])))
           stk = int(r['total_stock'])
           desc = r['item_desc']
           m = r['model']

           if pno not in agg_dict:
               agg_dict[pno] = {
                   'part_no': pno,
                   'item_desc': desc,
                   'model': m,
                   'pdf_price': pr,
                   'total_stock': stk
               }
           else:
               # Select maximum executive retail price
               if pr > agg_dict[pno]['pdf_price']:
                   agg_dict[pno]['pdf_price'] = pr
               # Sum stock balance across bins
               agg_dict[pno]['total_stock'] += stk
               # Keep longest canonical description
               if len(desc) > len(agg_dict[pno]['item_desc']):
                   agg_dict[pno]['item_desc'] = desc

       stock_rows = []
       for pno, info in agg_dict.items():
           tok = tokenize_appliance_model(info['model'])
           brand = tok.get('brand') or "Gree"
           category = tok.get('category') or "Split AC"
           capacity = tok.get('tonnage') or "1.5 Ton"
           product = "Audio Video" if category in ["LED TV", "Microwave Oven"] else "Home Appliances"
           bal_qty = info['total_stock']
           unit_price = info['pdf_price']
           amount = float(unit_price * bal_qty) if bal_qty > 0 else 0.0

           stock_rows.append((
               pno,
               "",                 # item_code
               info['item_desc'],  # item_desc
               product,            # product
               brand,              # brand
               category,           # category
               capacity,           # capacity
               bal_qty,            # bal_qty
               amount,             # amount
               unit_price,         # unit_price
               "DWP Official Price Catalog (vp786.pdf)"  # last_synced
           ))

       with get_connection() as conn:
           cursor = conn.cursor()
           # Upsert parts_master
           cursor.executemany("""
               INSERT INTO parts_master (model, part_no, part_name, price)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(model, part_no) DO UPDATE SET
                   price = excluded.price,
                   part_name = excluded.part_name
           """, parts_rows)

           # Upsert stock_master
           cursor.executemany("""
               INSERT INTO stock_master 
               (part_no, item_code, item_desc, product, brand, category, capacity, bal_qty, amount, unit_price, last_synced)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(part_no) DO UPDATE SET
                   item_desc = excluded.item_desc,
                   brand = CASE WHEN stock_master.brand IS NULL OR stock_master.brand = '' THEN excluded.brand ELSE stock_master.brand END,
                   category = CASE WHEN stock_master.category IS NULL OR stock_master.category = '' THEN excluded.category ELSE stock_master.category END,
                   capacity = CASE WHEN stock_master.capacity IS NULL OR stock_master.capacity = '' THEN excluded.capacity ELSE stock_master.capacity END,
                   product = CASE WHEN stock_master.product IS NULL OR stock_master.product = '' THEN excluded.product ELSE stock_master.product END,
                   bal_qty = excluded.bal_qty,
                   amount = excluded.amount,
                   unit_price = excluded.unit_price,
                   last_synced = excluded.last_synced
           """, stock_rows)

           # Cross-enrich parts_master with valid prices from stock_master
           cursor.execute("""
               UPDATE parts_master
               SET price = (
                   SELECT s.unit_price FROM stock_master s 
                   WHERE s.part_no = parts_master.part_no AND s.unit_price > 0
               )
               WHERE (price IS NULL OR price = 0)
                 AND EXISTS (
                   SELECT 1 FROM stock_master s 
                   WHERE s.part_no = parts_master.part_no AND s.unit_price > 0
                 )
           """)

       return len(stock_rows)
   ```

3. **In `ingest_stock_file()`**:
   - Replace lines 102–153:
   ```python
   # Load official price catalog authority
   official_prices = {}
   official_cat = OFFICIAL_STOCK_CSV_PATH if os.path.exists(OFFICIAL_STOCK_CSV_PATH) else os.path.join(BASE_DIR, "data", "pdf_extracted_stock_report.csv")
   if os.path.exists(official_cat):
       try:
           pdf_df = pd.read_csv(official_cat, dtype=str)
           pdf_df['p_clean'] = pdf_df['part_no'].apply(clean_val).str.upper()
           pdf_df['pr_clean'] = pd.to_numeric(pdf_df['pdf_price'], errors='coerce').fillna(0)
           official_prices = pdf_df.groupby('p_clean')['pr_clean'].max().to_dict()
       except Exception:
           pass

   def calculate_clean_unit_price(r):
       pno = r['part_no']
       # Master Price Authority
       if pno in official_prices and official_prices[pno] > 0:
           return int(round(float(official_prices[pno])))
       # Existing verified collection price
       if pno in existing_prices and existing_prices[pno] > 0:
           return int(existing_prices[pno])

       # Role floor protection
       desc = str(r.get('item_desc', ''))
       role = classify_component_role(desc, pno)
       cap = str(r.get('capacity', ''))
       desc_up = desc.upper()
       ton = "1.5 Ton"
       for t_str, token in [('4.0 Ton', '48'), ('3.0 Ton', '36'), ('2.0 Ton', '24'), ('1.0 Ton', '12'), ('1.5 Ton', '18')]:
           if token in desc_up or token in cap:
               ton = t_str
               break
       cat = str(r.get('category', 'Split AC'))
       return get_role_price_floor(role, ton, cat)

   df['unit_price'] = df.apply(calculate_clean_unit_price, axis=1)
   df['amount'] = df.apply(lambda r: float(r['unit_price'] * r['bal_qty']) if r['bal_qty'] > 0 else 0.0, axis=1)
   ```

4. **In `bootstrap_master_data()` (lines 188–205)**:
   ```python
   def bootstrap_master_data():
       init_db_schema()
       with get_connection() as conn:
           cursor = conn.cursor()
           cursor.execute("SELECT count(*) FROM history_master")
           hist_count = cursor.fetchone()[0]
           cursor.execute("SELECT count(*) FROM stock_master")
           stock_count = cursor.fetchone()[0]

       if hist_count == 0 and os.path.exists(DEFAULT_FB_FILE):
           coll_path = DEFAULT_COLL_FILE if os.path.exists(DEFAULT_COLL_FILE) else None
           ingest_feedback_and_pricing(DEFAULT_FB_FILE, coll_path)

       if stock_count == 0:
           latest_stock = find_latest_stock_file()
           if latest_stock:
               ingest_stock_file(latest_stock)

       # Master Price Authority: Always synchronize the official PDF catalog
       pdf_stock_path = OFFICIAL_STOCK_CSV_PATH if os.path.exists(OFFICIAL_STOCK_CSV_PATH) else os.path.join(BASE_DIR, "data", "pdf_extracted_stock_report.csv")
       if os.path.exists(pdf_stock_path):
           ingest_pdf_stock_catalog(pdf_stock_path)
   ```

---

## 6. Target Parts Verification Table

| Acceptance Target | Part Number | Canonical Description | Primary Model | Official PDF Price | Current DB Price | Proposed Post-Ingestion Price | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **3/8" Valve** | `71302395` | `Cut-off valve 3/8 71302395 GS-12PITH1W/O` | `GS-12PITH1W` | **Rs. 1,500** | Rs. 1,500 | **Rs. 1,500** | Direct & Model Verified |
| **1/4" Valve** | `7130239` | `Cut-off Valve GS-24ECH10 7130239` | `GS-24ECH10` | **Rs. 1,600** | Rs. 1,600 | **Rs. 1,600** | Direct & Model Verified |
| **1/2" Valve** | `7133774` | `Cut Off Valve Assy 1/2 7133774 GS-18VITH1` | `GS-18VITH1` | **Rs. 2,100** | **Rs. 1,600 (Flawed)** | **Rs. 2,100** | Fixed to Official Price |
| **5/8" Valve** | `7133844` | `Cutt Off Valve 5/8 24LITH11M 7133844` | `GS-24LITH11M` | **Rs. 2,200** | Rs. 2,200 | **Rs. 2,200** | Direct & Model Verified |
| **GF-36TFIH Evaporator** | `11001000602` | `Evaporator Assy GF-36TFIH 11001000602` | `GF-36TFIH` | **Rs. 58,000** | **Missing from stock** | **Rs. 58,000** | Added to `stock_master` |
| **GS-18PITH1W Evaporator** | `11001060868` | `Evaporator Assy GS-18PITH1W 11001060868` | `GS-18PITH1W` | **Rs. 26,000** | Rs. 26,000 | **Rs. 26,000** | Direct & Model Verified |
| **GS-18AITH23W-T3 Evap** | `11001062414` | `Evaporator Assy GS-18AITH23W-T3 11001062414` | `GS-18AITH23W-T3` | **Rs. 30,000** | Rs. 30,000 | **Rs. 30,000** | Direct & Model Verified |
| **GF-48FW Evaporator** | `1004169` | `Evaporater Assy 48FW 1004169` | `GF-48FW` | **Rs. 70,000** | **Missing from stock** | **Rs. 70,000** | Added to `stock_master` |
| **GF-24ISH Evaporator** | `11001060092` | `Evaporator Assy 11001060092 24ISH` | `GF-24ISH` | **Rs. 72,000** | **Missing from stock** | **Rs. 72,000** | Added to `stock_master` |
| **GF-48TF Evaporator** | `11001060521` | `Evaporator Assy GF-48TF 11001060521` | `GF-48TF` | **Rs. 75,000** | **Missing from stock** | **Rs. 75,000** | Added to `stock_master` |
| **GF-24CB Evaporator** | `100404401` | `Evaporator Assy 24CB/ 24TFIH 100404401` | `GF-24CB` | **Rs. 66,000** | **Missing from stock** | **Rs. 66,000** | Added to `stock_master` |

---

## 7. Independent Verification Commands

To verify the implementation once applied by Worker 1:
```bash
# 1. Run the system verification regression test suite
python test_system_verification.py

# 2. Verify all 518 parts are indexed in stock_master with positive prices
python -c "import sqlite3; conn = sqlite3.connect('dwp_service.db'); cur = conn.cursor(); cur.execute('SELECT count(*) FROM stock_master WHERE unit_price > 0'); print('Stock master items with price > 0:', cur.fetchone()[0]); cur.execute('SELECT count(distinct part_no) FROM parts_master WHERE price > 0'); print('Parts master unique parts with price > 0:', cur.fetchone()[0])"

# 3. Verify all 11 target parts match official prices exactly
python -c "import sqlite3; conn = sqlite3.connect('dwp_service.db'); cur = conn.cursor(); pnos = ('71302395', '7130239', '7133774', '7133844', '11001000602', '11001060868', '11001062414', '1004169', '11001060092', '11001060521', '100404401'); cur.execute('SELECT part_no, unit_price FROM stock_master WHERE part_no IN ' + str(pnos)); rows = dict(cur.fetchall()); expected = {'71302395': 1500, '7130239': 1600, '7133774': 2100, '7133844': 2200, '11001000602': 58000, '11001060868': 26000, '11001062414': 30000, '1004169': 70000, '11001060092': 72000, '11001060521': 75000, '100404401': 66000}; print('All matched?', rows == expected); print('Actual:', rows)"

# 4. Verify search_stock_global returns previously missing evaporators
python -c "from database import search_stock_global; print(search_stock_global('1004169')[['part_no', 'part_name', 'price']].to_string())"
```
