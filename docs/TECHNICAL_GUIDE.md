# Technical Guide for Developers & Future Agents

Welcome to the **DWP Service Field Assistant Engine** technical documentation. This guide details the codebase architecture, database schema (`dwp_service.db`), ETL pipelines, and business logic.

---

## 1. Project Architecture

The application is built using **Python 3** and **Streamlit** for the frontend, with a local **SQLite** database (`dwp_service.db`) acting as the high-speed data store.

### Key Files & Their Purposes:

- **`app.py`**:
  The main Streamlit frontend application. Contains the UI layout, session state management, and real-time computation:
  - **Tab 1: 🧮 Spare Parts & Cost Estimator** (Primary operational module for technicians and supervisors to generate job quotes, look up stock, and copy formatted WhatsApp quotations).
  - **Tab 2: 🔍 Unit & Customer History** (Wildcard search across serial numbers, customer phone numbers, and complaint IDs).
  - **Tab 3: 📊 Technician Performance** (KPI tracking, completion rates, and date-range filters).
  - **Sidebar**: Sync tools for daily closed complaints and latest Store Wise Stock Movement PDF.

- **`config.py`**:
  Application configuration and core pricing rules:
  - Base charges: `VISIT_CHARGES = 600`, `MOBILITY_CHARGES = 2000`, `BASE_FIXED_TOTAL = 2600`.
  - Capacity-aware gas charging map (`GAS_CHARGES_MAP`):
    - AC 1.0 Ton (12000 BTU): Rs. 5,500
    - AC 1.5 Ton (18000 BTU): Rs. 7,000
    - AC 2.0 Ton (24000 BTU): Rs. 8,500
    - AC 3.0 Ton / 4.0 Ton (36000 / 48000 BTU): Rs. 13,000
    - Refrigerator (`GR-` series): Rs. 4,000
    - Water Dispenser (`WD-` / `GW-` series): Rs. 3,500
  - Helper functions: `calculate_gas_charge(model_name)` and `calculate_gas_charge_amount(model_name)`.

- **`database.py`**:
  Data Access Layer for SQLite (`dwp_service.db`).
  - `init_estimator_schema()`: Ensures all tables, indexes, and views exist.
  - `get_all_models_for_estimator()`: Returns all 417 unique equipment models ordered by job frequency.
  - `get_parts_by_model(model_name)`: Returns all verified compatible parts, ERP prices, stock levels, technician allocations, and cross-model fit counts.
  - `update_part_price(part_no, new_price)`: Persists manual price overrides into `master_parts_lookup`.
  - `get_cross_model_compatibilities(part_no)`: Fetches all models where a part has been installed historically.
  - `merge_parts_master_into_catalog()`: Enriches catalog with verified parts from `parts_master` and enables cross-series coil and compressor compatibility.

- **`etl.py`**:
  Extract, Transform, Load (ETL) pipeline.
  - `parse_store_stock_pdf(pdf_source)`: Ingests the 50-page Store Wise Stock Movement PDF (`vp786`), pairs columns across paired pages, extracts retail prices, Karachi-2 Store quantities, technician in-hand stock, and filters out B-grade sets.
  - `sync_model_part_catalog_from_feedback(fb_source, is_incremental)`: Ingests Quality Feedback Reports, resolves corrupted Excel scientific notations (e.g. `3.00002E+11`), explodes comma-separated part numbers, and establishes 1-to-1 model-to-part compatibility.

- **`tests/test_estimator_suite.py`**:
  Automated unit and integration regression test suite (8 test cases covering gas rates, schema integrity, stock normalization, cross-compatibility, manual pricing, missing exports, non-regression, and WD/AC compressor/evaporator presence).

---

## 2. Database Schema (`dwp_service.db`)

### Core Tables & Views:

1. **`model_part_catalog`**:
   - `model` (TEXT, PK): Equipment model name (e.g. `GS-18PITH11W`, `WD-300`).
   - `part_no` (TEXT, PK): Unique part SKU / code.
   - `part_description` (TEXT): Physical part description.
   - `board_type` (TEXT): Sub-assembly category (e.g. `Evaporator Assy`, `Cut Off Valve`, `Electronic PCB`, `WD Compressor`).
   - `historical_frequency` (INTEGER): Number of times installed on this specific model.
   - `last_installed_date` (TEXT): Date of last closed service complaint.

2. **`master_parts_lookup`**:
   - `part_no` (TEXT, PK): Unique part SKU.
   - `erp_description` (TEXT): Official ERP stock item description.
   - `retail_price` (INTEGER): Official Karachi-2 Store retail selling price in PKR.
   - `branch_store_qty` (INTEGER): Raw stock quantity at Karachi-2 HA Store.
   - `available_branch_stock` (INTEGER): Normalized stock (`max(0, branch_store_qty)`).
   - `tech_stock_qty` (INTEGER): Sum of stock held across all field technicians.
   - `total_stock_qty` (INTEGER): Overall warehouse total stock.
   - `stock_status` (TEXT): `'In Stock'` or `'Out of Stock'`.
   - `tech_allocations_json` (TEXT): JSON breakdown of hand stock per technician.
   - `is_pricing_pending` (INTEGER): `1` if price needs manual input, `0` if confirmed.

3. **`v_model_compatible_parts` (SQL View)**:
   Joins `model_part_catalog` with `master_parts_lookup`, computing live stock, official prices, and cross-model fit counts dynamically.

4. **`history_master`**:
   Stores closed complaints, serial numbers, customer details, and final collection amounts.

5. **`tech_performance_master`**:
   Stores technician job completion, cancellation, and transfer data for KPI evaluation.

---

## 3. Ground-Truth & Business Rules

1. **Zero Hallucination Compatibility**:
   Model-to-part mappings are strictly derived from physical installations recorded in Quality Feedback Reports and the company's verified `parts_master` catalog.
2. **Estimator Visibility Architecture**:
   An Estimator is a quotation tool. All verified compatible parts are visible by default so that technicians can quote repairs regardless of whether a part is currently in the store or needs procurement.
   In-stock items are highlighted with green badges (`🟢 Karachi-2 Store: X In Stock`), while zero-stock items display (`🔴 Karachi-2 Store: 0 Available (Procurement Required)`).
   A radio filter allows viewing "In-Stock Only" when immediate dispatch is needed.
3. **Cross-Series Coil & Compressor Interchangeability**:
   - Gree 18-Series Inverter Evaporators (`11001060868`, `1002937LC`, `1002686LC`, `11001000207LC`) are cross-compatible across all 18-series inverters.
   - Gree 12-Series Inverter Evaporators (`1002976`, `1002422LC`, `1002000030`) are cross-compatible across all 12-series inverters.
   - Water Dispenser compressors (`QD36LWL`, `QD36LW`) are cross-compatible across all WD models.
4. **WhatsApp Quotation Generator**:
   Generates a one-click copyable and interactive WhatsApp message with formal itemization, technician support phone, and direct `api.whatsapp.com` link.
