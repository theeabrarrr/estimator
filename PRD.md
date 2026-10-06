# Ground Truth Product Requirement Document (PRD)
## DWP Field Assistant Engine

**Project Name:** DWP Field Assistant Engine (`estimator`)  
**Repository:** `theeabrarrr/estimator`  
**Target Organization:** Digital World Pakistan (Pvt) Ltd (DWP Group)  
**Supported Brands:** Gree & EcoStar (HVAC, Refrigeration, Water Dispensers, Washing Machines, LED TVs)  
**Database:** Local SQLite (`dwp_service.db`)  
**Document Status:** Ground Truth Standard (Active & Authoritative)  
**Version:** 2.1 (Performance & History Analytics Standard)  

---

## 1. Executive Summary & Delivery Scope

The **DWP Field Assistant Engine** is an enterprise field operations, diagnostic, and quotation platform designed specifically for DWP service center technicians, field engineers, supervisors, and branch managers across Pakistan.

### Core Value Proposition
- **Instant Quotation Generation:** Eliminates manual calculation errors, auto-calculates refrigerant gas rates based on equipment BTU capacity, and formats official WhatsApp quotations in seconds.
- **Zero-Hallucination Spare Parts Compatibility:** Maps spare parts to appliance models strictly based on empirical closed field complaint history and verified parts catalogs.
- **Real-Time ERP Stock Visibility:** Displays live stock levels at the Karachi-2 HA Store, technician in-hand stock, and enterprise warehouse totals.
- **Searchable Service History:** Provides instant wildcard search across 14,088+ historical closed complaints spanning serial numbers, customer phone numbers, and complaint IDs with dedicated status indicators (`🟢 Completed`, `🔴 Rejected/Canceled`).
- **Technician KPI Tracking:** Evaluates technician completion efficiency, assigned jobs, completed calls, cancellations, and nil calls over dynamic monthly periods or custom date ranges with sequential ranking (`Sr. No`).

---

## 2. Comprehensive System Architecture & Modules

```
                    ┌─────────────────────────────────────────────────┐
                    │            Streamlit Frontend (app.py)          │
                    └────────────────────────┬────────────────────────┘
                                             │
         ┌───────────────────────────────────┼───────────────────────────────────┐
         │                                   │                                   │
┌────────▼────────┐                 ┌────────▼────────┐                 ┌────────▼────────┐
│  Tab 1: Spare   │                 │   Tab 2: Unit   │                 │   Tab 3: Tech   │
│ Parts Estimator │                 │    & Customer   │                 │   Performance   │
│    & Quotation  │                 │     History     │                 │       KPI       │
└────────┬────────┘                 └────────┬────────┘                 └────────┬────────┘
         │                                   │                                   │
         └───────────────────────────────────┼───────────────────────────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────┐
                    │       Data Access Layer (database.py)           │
                    └────────────────────────┬────────────────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────┐
                    │     SQLite Database (dwp_service.db)            │
                    │   - model_part_catalog  - master_parts_lookup   │
                    │   - history_master      - tech_performance      │
                    │   - v_model_compatible_parts (View)             │
                    └────────────────────────┬────────────────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────┐
                    │      ETL & Ingestion Engine (etl.py)            │
                    │   - Store Stock PDF Parser (vp786)              │
                    │   - Unified Complaint & KPI Pipeline            │
                    │   - Stream-Safe Buffer & Ingestion Engine       │
                    └─────────────────────────────────────────────────┘
```

### Module 1: 🧮 Spare Parts & Cost Estimator Engine (Primary Deliverable)
1. **Model Selector Dropdown:** Access to 500+ Gree and EcoStar equipment models (e.g. `GS-18PITH11W`, `GS-12PITH11W`, `WD-300`, `GR-E8890G`), sorted by job frequency.
2. **Capacity-Aware Gas Rate Engine:** Automatically detects model BTU capacity and calculates exact refrigerant gas refill pricing.
3. **Billing & Overheads Controls:**
   - Visit Charges: **Rs. 600**
   - Mobility / Labour Charges: **Rs. 2,000**
   - Base Fixed Overheads: **Rs. 2,600**
   - Warranty Toggle: *Cash / Out of Warranty*, *Under Warranty (Free)*, *Partial Warranty (Parts Cash, Labour Free)*.
4. **Verified Spare Parts Catalog:**
   - Multi-word & SKU search filter.
   - Sub-assembly category filter (Evaporators, PCBs, Compressors, Fan Motors, Cut-off Valves, Stepping Motors, Sensors, Capacitors).
   - Inventory filter toggle (*All Verified Parts* vs. *🟢 In-Stock Only*).
   - Live inventory badges:
     - `🟢 Karachi-2 Store: X In Stock` (Immediate dispatch)
     - `🔴 Karachi-2 Store: 0 Available` (Procurement / Indent required)
     - `🤝 In Hand: Tech Name (Qty)` (Intra-fleet handover)
     - `🌐 Fits X models` (Cross-model fit count expander)
5. **Real-Time Interactive Quotation & WhatsApp Generator:**
   - Live itemized subtotal and total customer payable calculation.
   - Customer details input (Name, Phone, Unit Serial Number).
   - One-click copyable formatted markdown quotation block.
   - Direct interactive WhatsApp button (`https://api.whatsapp.com/send?phone=...`).

### Module 2: 🔍 Unit & Customer History Archive
- Wildcard search across `serial`, `phone`, `complaint_no`, and `customer_name`.
- Dual-source lookup (`history_master` UNION ALL `tech_performance_master`) ensuring 100% visibility for completed, canceled, and rejected service tickets.
- Clear status badges:
  - `🟢 Completed` (green badge)
  - `🔴 Rejected/Canceled` (red badge)
- Formatted clean complaint numbers without Excel prefix artifacts (`="`).
- Displays technician name, purchase date, complaint date, closed date, closing remarks, and collected revenue amount.

### Module 3: 📊 Technician Performance KPI Hub
- Top KPI Summary Cards:
  - `Total Assigned Jobs`
  - `Completed Complaints`
  - `Rejected Calls`
  - `Canceled Calls`
  - `Zone Completion Efficiency %`
- Sequential Ranking: Table begins with `Sr. No` (1, 2, 3...) sorted automatically by Completed complaints volume descending.
- Dynamic Evaluation Period:
  - Dropdown populated dynamically with available historical calendar months (e.g., `🗓️ January 2026`, `🗓️ September 2026`, etc.).
  - `📅 Custom Date Range...` option with dual calendar pickers for arbitrary period analysis.
- Non-destructive SQLite persistence: Preserves all historical months without wiping prior data.

### Sidebar Data Ingestion & Tools
- Unified Service & Performance Sync (`sync_all_complaints_pipeline`): Ingests Quality Feedback, Cancel/Nil/Transfer, and Detail Collection reports simultaneously.
- Stream-Safe Buffer Architecture: Auto-rewinds file pointers (`seek(0)`) to prevent `EmptyDataError` during multiple upload passes.
- Daily Store Stock PDF Sync (`parse_store_stock_pdf`).
- Download Pending ERP Prices CSV (`get_missing_price_parts_df`).

---

## 3. Database Schema (`dwp_service.db`)

```sql
-- 1. Model-to-Part Compatibility Table
CREATE TABLE IF NOT EXISTS model_part_catalog (
    model TEXT NOT NULL,
    part_no TEXT NOT NULL,
    part_description TEXT,
    board_type TEXT,
    historical_frequency INTEGER DEFAULT 1,
    last_installed_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model, part_no)
);

-- 2. Master Pricing & Inventory Table
CREATE TABLE IF NOT EXISTS master_parts_lookup (
    part_no TEXT PRIMARY KEY,
    erp_description TEXT,
    erp_default_model TEXT,
    retail_price INTEGER DEFAULT 0,
    branch_store_qty INTEGER DEFAULT 0,
    branch_sales_qty INTEGER DEFAULT 0,
    tech_stock_qty INTEGER DEFAULT 0,
    total_stock_qty INTEGER DEFAULT 0,
    available_branch_stock INTEGER DEFAULT 0,
    available_total_stock INTEGER DEFAULT 0,
    stock_status TEXT DEFAULT 'Out of Stock',
    tech_allocations_json TEXT,
    is_pricing_pending INTEGER DEFAULT 0,
    source_document TEXT,
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Live Estimator Integration View
CREATE VIEW IF NOT EXISTS v_model_compatible_parts AS
SELECT 
    c.model,
    c.part_no,
    COALESCE(p.erp_description, c.part_description) AS part_description,
    c.board_type,
    c.historical_frequency,
    COALESCE(p.retail_price, 0) AS retail_price,
    COALESCE(p.available_branch_stock, 0) AS branch_stock,
    COALESCE(p.tech_stock_qty, 0) AS tech_stock,
    COALESCE(p.available_total_stock, 0) AS total_stock,
    COALESCE(p.stock_status, 'Out of Stock') AS stock_status,
    COALESCE(p.tech_allocations_json, '{}') AS tech_allocations_json,
    COALESCE(p.is_pricing_pending, 1) AS is_pricing_pending,
    (SELECT COUNT(DISTINCT m2.model) FROM model_part_catalog m2 WHERE m2.part_no = c.part_no) AS cross_model_count
FROM model_part_catalog c
LEFT JOIN master_parts_lookup p ON c.part_no = p.part_no;

-- 4. History Master Table
CREATE TABLE IF NOT EXISTS history_master (
    complaint_no TEXT PRIMARY KEY,
    serial TEXT,
    phone TEXT,
    model TEXT,
    customer_name TEXT,
    technician_name TEXT,
    complaint_type TEXT,
    purchase_date TEXT,
    complaint_date TEXT,
    closed_date TEXT,
    remarks TEXT,
    closed_amount INTEGER DEFAULT 0
);

-- 5. Technician Performance Master Table
CREATE TABLE IF NOT EXISTS tech_performance_master (
    complaint_no TEXT PRIMARY KEY,
    technician_name TEXT,
    status TEXT,
    closed_date TEXT
);

-- 6. High-Performance B-Tree Indexes
CREATE INDEX IF NOT EXISTS idx_history_complaint_no ON history_master (complaint_no);
CREATE INDEX IF NOT EXISTS idx_history_phone ON history_master (phone);
CREATE INDEX IF NOT EXISTS idx_history_serial ON history_master (serial);
CREATE INDEX IF NOT EXISTS idx_history_closed_date ON history_master (closed_date);
CREATE INDEX IF NOT EXISTS idx_tech_perf_tech ON tech_performance_master (technician_name);
CREATE INDEX IF NOT EXISTS idx_tech_perf_date ON tech_performance_master (closed_date);
```

---

## 4. Business Rules & Ground Truth Pricing Engines

### 1. Capacity-Aware Gas Charging Map
Refrigerant gas refill rates (PKR) are calculated strictly by appliance category and BTU tonnage:

| Category / BTU Capacity | Model Pattern Match | Gas Refill Charge (PKR) | Gas Type Description |
| :--- | :--- | :---: | :--- |
| **Split AC 1.0 Ton (12000 BTU)** | `12`, `12000`, `1.0 TON` | **Rs. 5,500** | Split AC Gas Refill (1.0 Ton / 12000 BTU) |
| **Split AC 1.5 Ton (18000 BTU)** | `18`, `18000`, `1.5 TON` | **Rs. 7,000** | Split AC Gas Refill (1.5 Ton / 18000 BTU) |
| **Split AC 2.0 Ton (24000 BTU)** | `24`, `24000`, `2.0 TON` | **Rs. 8,500** | Split AC Gas Refill (2.0 Ton / 24000 BTU) |
| **Commercial AC 3.0 Ton (36000 BTU)**| `36`, `36000`, `3.0 TON` | **Rs. 13,000** | Commercial AC Gas Refill (3.0 Ton / 36000 BTU) |
| **Commercial AC 4.0 Ton (48000 BTU)**| `48`, `48000`, `4.0 TON` | **Rs. 13,000** | Commercial AC Gas Refill (4.0 Ton / 48000 BTU) |
| **Refrigerator** | Starts with `GR-` | **Rs. 4,000** | Refrigerator Gas Refill (R-600a) |
| **Water Dispenser** | Starts with `WD-` or `GW-` | **Rs. 3,500** | Water Dispenser Gas Refill (R-134a) |
| **Default Fallback** | All other Split AC models | **Rs. 5,500** | Split AC Gas Refill (Standard 1.0 Ton) |

### 2. Refrigerant Cut-Off Valve Tonnage Compatibility Constraints
Strict pairing rules apply based on empirical field installations:
- **1.0 Ton Unit:** 1/4" (Liquid line) + 3/8" (Suction line). *Reject 1/2" & 5/8"*.
- **1.5 Ton Unit:** 1/4" (Liquid line) + 1/2" (Suction line). *Reject 3/8" & 5/8"*.
- **2.0 & 3.0 Ton Unit:** 1/4" (Liquid line) + 5/8" (Suction line). *Reject 3/8" & 1/2"*.
- **4.0 & 5.0 Ton Unit:** 3/8" (Liquid line) + 5/8" (Suction line). *Reject 1/4" & 1/2"*.

### 3. Cross-Series Interchangeability Enrichment
- **Gree 18-Series Inverter Evaporators:** Coils `11001060868`, `1002937LC`, `1002686LC`, `11001000207LC` are cross-compatible across all 18-series inverter models.
- **Gree 12-Series Inverter Evaporators:** Coils `1002976`, `1002422LC`, `1002000030` are cross-compatible across all 12-series inverter models.
- **Water Dispenser Compressors:** `QD36LWL` and `QD36LW` compressors are cross-compatible across all WD models (`WD-300`, `WD-300F`, `WD-350F`, `WD-450F`).
- **Everest Refrigerator Compressors:** `GR18-E51519002`, `GR18-E51519001`, `GR18-73710005`, `GR18-73710006` are cross-compatible across all Everest `GR-` series models.

---

## 5. Identified Technical Issues & Challenges (Masail & Mitigations)

| # | Technical Challenge (Masail) | Root Cause Analysis | Ground Truth Mitigation Implemented |
| :-: | :--- | :--- | :--- |
| **1** | **34.7% Pending ERP Pricing (207 Unpriced Parts)** | Legacy SKUs, petty-cash items, or discontinued models missing from the stock movement PDF report. | • Amber `⚠️ Pending ERP Pricing` badge in UI.<br>• Manual price entry with SQLite persistence.<br>• Exportable CSV download for ERP procurement updates. |
| **2** | **Excel Scientific Notation Barcode Truncation** | Excel converts 12-14 digit SKUs into scientific notation (e.g. `3.00002E+11`). | • Automated regex extraction in `etl.py` parsing descriptions (`HARDWARE_PRODUCTS` / `HARDWARE_BOARD_TYPES`) to restore true barcodes. |
| **3** | **ERP Administrative Negative Inventory Balances** | Warehouse ledger lists negative quantities (e.g. `-96` evaporators) due to parts issued prior to PO posting. | • UI normalizes stock via `available_branch_stock = max(0, branch_store_qty)`. Displays `🔴 0 Available`. |
| **4** | **Paired Horizontal PDF Layout Spans** | 50-page stock movement report spans odd/even page pairs (Odd: items & techs 1-10; Even: techs 11-19 & total stock). | • Dual-page synchronized extraction using `pdfplumber` joining paired rows. |
| **5** | **Finished Goods Set Interference** | Complete B-grade finished units (e.g. `Bgrade Set GW-JL500F`) present in store movement report. | • Regex scrubbing in ETL (`b[- ]?grade\s+set`) to scrub non-spare-parts items. |
| **6** | **Single-Model ERP Description Fallacy** | Stock movement report lists only 1 default model string per row (e.g., valve `7130239` under `GS-24ECH10`). | • Model-part compatibility derived strictly from historical field complaints and `parts_master`, enabling true multi-model mapping (142 models for valve `7130239`). |
| **7** | **Multi-Pass Stream Buffer Exhaustion (`EmptyDataError`)** | In multi-file pipelines, Streamlit `UploadedFile` pointers hit EOF on the first read, causing subsequent readers to crash with `EmptyDataError`. | • Universal stream rewinding (`seek(0)`) implemented in `safe_read()`.<br>• `sync_all_complaints_pipeline()` pre-parses inputs into in-memory DataFrames once for 3x speed and zero stream collision. |
| **8** | **Destructive Historical Performance Wiping** | Previous ETL pipelines used destructive `DELETE FROM tech_performance_master`, wiping prior months when uploading current month records. | • Switched to non-destructive `INSERT OR REPLACE` keyed by `complaint_no`.<br>• Preserves 14,088+ multi-month baseline complaints across all past evaluation periods. |

---

## 6. Required Customer Skills & AI Agent Operating Guidelines

To ensure that any AI coding assistant or developer working on this repository operates strictly according to project standards, the following **4 Required Customer Skills** are permanently embedded into this PRD:

---

### 🛠️ CUSTOMER SKILL 1: `dwp-catalog-sync-and-etl`
**Purpose:** Instructions for executing daily stock movement PDF parsing and daily closed complaint CSV/Excel merging without corrupting baseline historical data.

#### Execution Protocol:
1. **PDF Stock Ingestion (`etl.parse_store_stock_pdf`):**
   - Always open PDF using `pdfplumber.open()`.
   - Process pages in pairs (`step=2`): Page `N` (Odd) paired with Page `N+1` (Even).
   - Filter out rows matching `re.search(r'b[- ]?grade\s+set', text, re.IGNORECASE)`.
   - Calculate `available_branch_stock = max(0, branch_store_qty)` and `available_total_stock = max(0, total_stock_qty)`.
   - Extract technician hand stock allocations from columns and serialize to JSON (`tech_allocations_json`).
   - Upsert into `master_parts_lookup` with `is_pricing_pending = 0`.
2. **Quality Feedback Ingestion (`etl.sync_model_part_catalog_from_feedback`):**
   - Standardize dataframe column aliases via `etl.standardize_columns()`.
   - Filter tickets where `COMPLETED_STATUS == 'COMPLETED'`.
   - Strip Excel wrappers `="value"`.
   - Resolve scientific notation (`E+`) using regex `[0-9A-Z\-]{7,15}` against product description.
   - Explode comma-separated part numbers, product names, and board types.
   - Insert new catalog pairs or increment installation counts using SQLite `ON CONFLICT(model, part_no) DO UPDATE SET historical_frequency = historical_frequency + excluded.historical_frequency`.

---

### 🛠️ CUSTOMER SKILL 2: `dwp-estimator-pricing-and-rules`
**Purpose:** Business logic and calculation constraints for creating service quotations.

#### Execution Protocol:
1. **Gas Refill Calculation (`config.calculate_gas_charge`):**
   - Always evaluate model name with `.upper().strip()`.
   - Match category prefixes: `GR-` -> Refrigerator (Rs. 4,000), `WD-`/`GW-` -> Water Dispenser (Rs. 3,500).
   - Match tonnage tokens: `48`/`4.0 TON` -> Rs. 13,000; `36`/`3.0 TON` -> Rs. 13,000; `24`/`2.0 TON` -> Rs. 8,500; `18`/`1.5 TON` -> Rs. 7,000; `12`/`1.0 TON` -> Rs. 5,500. Default: Rs. 5,500.
2. **Warranty Logic:**
   - *Cash / Out of Warranty:* `Payable = Parts + Visit (600) + Labour (2000) + Gas`.
   - *Under Warranty:* `Payable = 0`.
   - *Partial Warranty:* `Payable = Parts + Gas`. (Visit & Labour free).
3. **Cut-Off Valve Tonnage Rules (`config.is_valve_tonnage_compatible`):**
   - 1.0 Ton: Reject 1/2" & 5/8". Accept 1/4" & 3/8".
   - 1.5 Ton: Reject 3/8" & 5/8". Accept 1/4" & 1/2".
   - 2.0 & 3.0 Ton: Reject 3/8" & 1/2". Accept 1/4" & 5/8".
   - 4.0 & 5.0 Ton: Reject 1/4" & 1/2". Accept 3/8" & 5/8".

---

### 🛠️ CUSTOMER SKILL 3: `dwp-zero-hallucination-compatibility-verifier`
**Purpose:** Rules enforcing zero-hallucination component compatibility for appliance models.

#### Execution Protocol:
1. **Source of Truth Hierarchy:**
   - **Level 1:** Historical closed complaint installations (`quality_feedback_report`).
   - **Level 2:** Baseline verified `parts_master` table.
   - **Level 3:** Cross-series coil & compressor interchangeability rules (`database.merge_parts_master_into_catalog`).
2. **Prohibited Actions:**
   - NEVER create a model-to-part mapping based solely on ERP stock report descriptions (`erp_default_model`).
   - NEVER suggest unverified spare parts for an appliance without explicit historical installation or cross-series compatibility approval.

---

### 🛠️ CUSTOMER SKILL 4: `dwp-sqlite-schema-and-query-engine`
**Purpose:** Data access layer rules for querying `dwp_service.db`.

#### Execution Protocol:
1. **Thread-Safe Context Manager:**
   - Always access database using `with database.get_connection() as conn:`.
2. **Estimator Queries:**
   - To fetch compatible parts for a model, query the view:
     `SELECT * FROM v_model_compatible_parts WHERE model = ? ORDER BY historical_frequency DESC, part_no ASC`.
   - To query cross-model compatibility:
     `SELECT model, historical_frequency FROM model_part_catalog WHERE part_no = ? ORDER BY historical_frequency DESC`.
3. **Manual Price Overrides:**
   - Persist price updates in `master_parts_lookup` with `is_pricing_pending = 0` and timestamp `last_synced = CURRENT_TIMESTAMP`.

---

### 🛠️ CUSTOMER SKILL 5: `dwp-ui-design-system`
**Purpose:** UI/UX design system, pure #FFFFFF (White) & #000000 (Black) high-contrast theme, Dark Mode compatibility, typography hierarchy, and progressive 4-step disclosure layout for DWP Field Assistant Engine.

#### Execution Protocol:
1. **Strict Pure White & Black Palette (`#FFFFFF` & `#000000`):**
   - **White (`#FFFFFF`):** Light mode surface background, dark mode high-contrast text.
   - **Black (`#000000`):** Dark mode surface background, light mode high-contrast text, borders, headers.
   - **Adaptive CSS Theme Variables (`var(--text-color)`, `var(--secondary-background-color)`):** All custom cards, badges, step boxes, and table cells MUST use adaptive CSS variables so text never clashes or overlaps when switching between Light Mode and Dark Mode.
2. **Dark Mode & Light Mode Contract:**
   - **Light Mode:** White `#FFFFFF` background, Black `#000000` text, neutral borders.
   - **Dark Mode:** Dark `#000000` / `#0E1117` background, White `#FFFFFF` text, neutral borders.
   - Never hardcode dark static text inside HTML containers without adaptive theme variables.
3. **Progressive 4-Step Layout Flow:**
   - **Step 1:** Appliance Model Selection (`selected_model` dropdown).
   - **Step 2:** Category & Sub-Assembly Explorer (selectbox with `format_func` preserving exact category keys, top floating cart, bounded scroll container `st.container(height=450)` to prevent endless page scrolling).
   - **Step 3:** Base Overhead Controls (Visit, Mobility/Labour, Refrigerant Gas) & Warranty Status.
   - **Step 4:** Real-Time Itemized Bill Card & Pre-formatted WhatsApp Quotation.

---

## 7. Verification & Compliance Sign-Off

- **Ground Truth Baseline:** Fully reconciled against 14,088+ historical service complaints and 50 PDF stock movement pages across 21 months.
- **Automated Regression Suite:** All 13 unit tests in `tests/test_estimator_suite.py` must pass cleanly before any code commit:
  - Test 01: Capacity-aware gas charge calculation
  - Test 02: Database schema and distinct models retrieval
  - Test 03: Parts retrieval and stock quantity normalization
  - Test 04: Cross-model compatibility
  - Test 05: Manual price override persistence
  - Test 06: Missing ERP price export
  - Test 07: Refrigerant valve tonnage constraints
  - Test 08: Stock movement PDF parser validation
  - Test 09: Sequential ranking (`Sr. No`) by completed complaints volume
  - Test 10: Multi-source search query with status badges (`🟢 Completed`, `🔴 Rejected/Canceled`)
  - Test 11: Date indexing on `closed_date` for high-speed date range queries
  - Test 12: Dynamic month-filtering (e.g., January 2026, September 2026) without baseline wipe
  - Test 13: Stream-safe unified ingestion pipeline (`sync_all_complaints_pipeline`)
- **User Interface Standards:** Streamlit UI must adhere to `dwp-ui-design-system` (#FFFFFF & #000000 palette, seamless Light & Dark Mode contrast, 4-step progressive disclosure, and one-click WhatsApp quote formatting).


