# Ground Truth Product Requirement Document (PRD)
## DWP Field Assistant Engine

**Project Name:** DWP Field Assistant Engine (`estimator`)  
**Repository:** `theeabrarrr/estimator`  
**Target Organization:** Digital World Pakistan (Pvt) Ltd (DWP Group)  
**Supported Brands:** Gree & EcoStar (HVAC, Refrigeration, Water Dispensers, Washing Machines, LED TVs)  
**Database Architecture:** Dual-Engine: **Turso Cloud Database (libSQL over HTTP Pipeline API)** (Primary Cloud Persistence) with transparent fallback to **Local SQLite (`dwp_service.db`)** (Local/Offline)  
**Document Status:** Ground Truth Standard (Active & Authoritative)  
**Version:** 2.4 (Branch-Level Multi-Center Filtering, Turnaround Time Avg Days Tracking, and Dynamic Technician Personal Scorecards)  

---

## 0. Mandatory Continuous PRD Maintenance & Versioning Policy

> [!IMPORTANT]
> **Strict Operational Governance Protocol:**
> 1. **Mandatory Documentation Synchronization**: Whenever any new feature, service rate, architectural layer, database schema change, or UI/UX modification is introduced, `PRD.md` **MUST** be updated immediately in the same git branch before merging.
> 2. **Sequential Version Numbering**: Every release or structural change must increment the version number (e.g., v2.0 -> v2.1 -> v2.2 -> v2.3).
> 3. **Ground Truth Authority**: The PRD is the single source of truth for all business logic, technical architecture, and UI/UX standards across human developers and AI pair-programming agents.

---

## 1. Executive Summary & Delivery Scope

The **DWP Field Assistant Engine** is an enterprise field operations, diagnostic, cost estimation, and technician performance tracking platform designed specifically for DWP service center technicians, field engineers, supervisors, and branch managers across Pakistan.

### Core Value Proposition
- **Instant Quotation Generation:** Eliminates manual calculation errors, auto-calculates refrigerant gas refill rates based on equipment BTU tonnage/capacity, supports additional service operations (4-way valve bypass, AC service charges), and formats official, copyable WhatsApp quotations in seconds.
- **Sleek Corporate Claymorphism:** High-contrast 3D tactile interface featuring inflated matte surfaces, smooth double-layer shadows, physical button press micro-interactions, and 100% adaptive Light/Dark mode compatibility.
- **High-Productivity 2-Column Split Dashboard:** Eliminates vertical scrolling by placing the Parts Catalog on the left and a Live Sticky Checkout & Quotation Generator on the right.
- **Ultra-Compact High-Density Parts Rows:** 65% vertical space reduction (~48px per item) allowing 5–8 components to be visible simultaneously without bulky expanders.
- **Zero-Hallucination Spare Parts Compatibility:** Maps spare parts to appliance models strictly based on empirical closed field complaint history and verified parts catalogs.
- **Real-Time ERP Stock Visibility:** Displays live stock levels at the Karachi-2 HA Store, technician in-hand stock, and enterprise warehouse totals.
- **Permanent Cloud Data Persistence:** Built on Turso Cloud Database (libSQL). Daily browser uploads (service complaints, feedback, store stock movements) are committed directly to cloud storage, permanently surviving Streamlit Community Cloud container restarts and sleep cycles with zero manual git pushes.
- **Searchable Service History Archive:** Provides instant wildcard search across **27,930+ historical closed complaints** spanning serial numbers, customer phone numbers, and complaint IDs with dedicated status badges (`🟢 Completed`, `🔴 Rejected`, `🟠 Canceled`).
- **Technician KPI Tracking Hub:** Evaluates technician completion efficiency, assigned jobs, completed calls, cancellations, and nil calls over dynamic monthly periods or custom date ranges across **18,156+ KPI performance records** with sequential ranking (`Sr. No`).

---

## 2. Comprehensive System Architecture & Modules

```
                    ┌─────────────────────────────────────────────────────────┐
                    │               Streamlit Frontend (app.py)               │
                    │   - Layout: Wide (2-Column Split Layout in Tab 1)       │
                    │   - Design: Sleek Corporate Claymorphism Theme          │
                    │   - Top-Level Query Caching (@st.cache_data ttl=3600)   │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
             ┌───────────────────────────────────┼───────────────────────────────────┐
             │                                   │                                   │
    ┌────────▼────────┐                 ┌────────▼────────┐                 ┌────────▼────────┐
    │  Tab 1: Spare   │                 │   Tab 2: Unit   │                 │   Tab 3: Tech   │
    │ Parts Estimator │                 │    & Customer   │                 │   Performance   │
    │   & Quotation   │                 │     History     │                 │       KPI       │
    └────────┬────────┘                 └────────┬────────┘                 └────────┬────────┘
             │                                   │                                   │
             └───────────────────────────────────┼───────────────────────────────────┘
                                                 │
                        ┌────────────────────────▼────────────────────────┐
                        │        Data Access Layer (database.py)          │
                        │   - Dual-Engine Connection Router               │
                        │   - Persistent HTTP Keep-Alive Connection Pool  │
                        └────────────────────────┬────────────────────────┘
                                                 │
                         ┌───────────────────────┴───────────────────────┐
                         │                                               │
             [Credentials Present]                             [Credentials Absent]
                         │                                               │
            ┌────────────▼─────────────┐                    ┌────────────▼─────────────┐
            │   Turso Cloud Database   │                    │      Local SQLite        │
            │   (libSQL /v2/pipeline)  │                    │     (dwp_service.db)     │
            │   Permanent Multi-Tenant │                    │     Local Dev & Offline  │
            └────────────┬─────────────┘                    └────────────┬─────────────┘
                         │                                               │
                         └───────────────────────┬───────────────────────┘
                                                 │
                        ┌────────────────────────▼────────────────────────┐
                        │         ETL & Ingestion Engine (etl.py)         │
                        │   - Store Stock PDF Parser (vp786)              │
                        │   - Unified Complaint & KPI Pipeline            │
                        │   - Stream-Safe Buffer & Ingestion Engine       │
                        └─────────────────────────────────────────────────┘
```

### Module 1: 🧮 Spare Parts & Cost Estimator Engine (Primary Deliverable)
1. **2-Column Split Dashboard Architecture:**
   - **Left Column (Parts Explorer):**
     - Step 1: Model Selection Dropdown (500+ Gree and EcoStar models).
     - Step 2: Sub-Assembly Category Explorer, SKU/Name Search, and Branch Inventory Scope toggle.
     - Bounded Scroll Catalog Container (`st.container(height=560)`) presenting ultra-compact 2-line rows.
   - **Right Column (Sticky Live Checkout & WhatsApp Generator):**
     - Live Selected Parts Cart with one-click `❌` removal and `Clear All` button.
     - Step 3: Service & Labour Charges controls with clean non-truncating checkboxes.
     - Step 4: Customer Details inputs (Name, Phone, Unit Serial Number).
     - Official Estimate Breakdown Receipt Card with real-time total calculation.
     - Formatted WhatsApp Quotation box with green clay `📲 Open WhatsApp Chat` button.

2. **Ultra-Compact 2-Line Spare Parts Catalog Rows (~48px per item):**
   - **Line 1 (Primary):** Checkbox + Bold Part Description + Bold Retail Price (`Rs. X,XXX` or `⚠️ Pending`).
   - **Line 2 (Metadata Row):** Monospace `SKU` + `[Category]` badge + Stock status pill (`🟢 Karachi-2: X` / `⚪ 0`) + Historical Frequency (`🔥 X jobs`) + Fits pill (`🌐 Fits X models`).
   - **Zero-Space Hover Tooltip:** The bulky `st.expander` has been eliminated; compatible models display via native HTML hover tooltips on the `🌐 Fits X models` pill.

3. **Billing & Service Charges Rates (PKR):**
   - Visit Charges: **Rs. 600**
   - Mobility / Labour Charges: **Rs. 2,000**
   - 4-Way Valve Bypass Charges: **Rs. 1,500** [NEW in v2.3]
   - AC General Service Charges: **Rs. 3,500** [NEW in v2.3]
   - Capacity-Aware Gas Refill:
     - 1.0 Ton AC (12,000 BTU): **Rs. 5,500**
     - 1.5 Ton AC (18,000 BTU): **Rs. 7,000**
     - 2.0 Ton AC (24,000 BTU): **Rs. 8,500**
     - 3.0 Ton / 4.0 Ton AC (36K/48K BTU): **Rs. 13,000**
     - Refrigerator (GR-Series): **Rs. 4,000**
     - Water Dispenser (WD-Series): **Rs. 3,500**
   - *Customer Warranty Status Selector removed in v2.3* (Estimates reflect commercial field jobs).

4. **Real-Time Interactive Quotation & WhatsApp Generator:**
   - Real-time subtotal, overheads, and grand total customer payable calculation.
   - Pre-formatted Markdown quotation template with official DWP header, terms, and warranty terms (45 days).
   - One-click WhatsApp link formatted with internationalized phone prefix (`92...`).

### Module 2: 🔍 Unit & Customer History Archive
- Wildcard search across `serial`, `phone`, `complaint_no`, and `customer_name`.
- Dual-source lookup (`history_master` UNION ALL `tech_performance_master`) ensuring 100% visibility for completed, canceled, and rejected service tickets.
- Clear 3D status badges:
  - `🟢 Completed` (green clay pill)
  - `🔴 Rejected` (red clay pill)
  - `🟠 Canceled` (amber clay pill)
- Clean complaint numbers without Excel prefix artifacts (`="`).
- Visual loading indicator (`st.spinner`) providing instant UI feedback.
- Displays technician name, purchase date, complaint date, closed date, closing remarks, and collected revenue amount.

### Module 3: 📊 Technician Performance KPI Hub
- **Branch & Evaluation Period Scope:**
  - Branch Selector placed alongside Evaluation Period, defaulting to `Karachi 2 HA`, with support for `-- All Branches --` (Enterprise View).
  - Monthly periods dynamically extracted from `closed_date`, Full Year Baseline, or Custom Date Range.
  - Informative scope banner indicating selected Branch, Date Range, and status exclusion notes.
- **Dynamic 5 KPI Metric Cards:**
  - `Total Assigned Jobs`
  - `Completed Complaints`
  - `Rejected Calls`
  - `Canceled / Nil Calls`
  - `Branch Efficiency (%)` (Renamed from Zone Efficiency; dynamically switches to `Personal Efficiency` or `Enterprise Efficiency`).
  - **Dynamic State Switching:** When an individual technician is selected in the personal score dropdown, all 5 top cards instantly switch to display that specific technician's metrics.
- **Technician Personal Scorecard & Ranking Table:**
  - Full ranking table sorted by completed volume descending with sequential ranking (`Sr. No`).
  - Columns: `Sr. No` | `Technician` | `Assigned` | `Completed` | `Rejected` | `Canceled` | `Avg Days`.
  - Replaced Completion Rate with **`Avg Days`** (Turnaround Time from complaint registration to closure; clamped at minimum 0 days for same-day closures).
  - **Ghost Row Elimination:** Blank technician records are cleanly excluded from the ranking table while counted in branch totals.
  - **Visual Highlighting:** The selected technician's row is highlighted with high-contrast clay accent styling while keeping the full branch ranking visible for supervisor context.

---

## 3. Database Architecture & Turso Cloud Integration

### Dual-Engine Design:
1. **Turso Cloud Database (libSQL over HTTP Pipeline API):**
   - Active when `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are provided in environment or `.streamlit/secrets.toml`.
   - Permanent cloud persistence across Streamlit container sleep cycles.
   - Single shared `requests.Session()` with TCP Keep-Alive connection pooling (`HTTPAdapter(pool_connections=10, pool_maxsize=20)`).
2. **Local SQLite (`dwp_service.db`):**
   - Fallback engine for local development and offline environments.

### Core Schema Tables:
1. `parts_pricing`: Spare parts catalog, retail prices, store stock, and pricing status.
2. `model_part_catalog`: Cross-model compatibility map and replacement frequencies.
3. `history_master`: Closed service complaints archive (27,930+ records).
4. `tech_performance_master`: Technician KPI performance tracking with `branch_name` and `days` columns (19,124+ records).
5. `branch_store_stock`: Karachi-2 HA Store inventory parsed from Store Movement PDFs.

---

## 4. UI/UX Design System: Sleek Corporate Claymorphism

Enforced by authoritative skill [`dwp-ui-design-system`](file:///.agents/skills/dwp-ui-design-system/SKILL.md).

### Visual Tokens & Standards:
1. **Inflated 3D Matte Surfaces:**
   - Outer soft drop shadow: `6px 6px 16px rgba(0,0,0,0.06)`
   - Inner inset bevel highlights: `inset 2px 2px 4px rgba(255,255,255,0.22), inset -2px -2px 4px rgba(0,0,0,0.05)`
2. **Rounded Clay Geometry:**
   - Cards & Step Containers: `border-radius: 18px - 20px;`
   - Compact Part Rows: `border-radius: 12px;`
   - Badges & Pills: `border-radius: 9999px;`
   - Inputs & Selectboxes: `border-radius: 12px;`
3. **Tactile Micro-Interactions:**
   - Button Hover: Gentle lift (`transform: translateY(-2px);`) with expanded soft shadow.
   - Button Active Press: Physical clay compression (`transform: translateY(1px);`).
4. **Light & Dark Theme Adaptability:**
   - Seamless dynamic inheritance using Streamlit theme variables (`var(--text-color)`, `var(--secondary-background-color)`, `var(--dwp-border)`).
   - Zero text contrast clashing across themes.
5. **Checkbox Label Wrapping:** Full text wrap enabled without truncation or ellipsis.
6. **Sidebar Footer Contact Box:** Operations & Support help relocated to the sidebar footer to keep the primary dashboard clean and distraction-free.

---

## 5. Verification & Compliance Sign-Off

- **Ground Truth Baseline:** Fully reconciled against 27,930+ service complaints, 18,156+ KPI performance records, and 50 PDF stock movement pages.
- **Live Browser Verification:** Verified in browser subagent testing on `http://localhost:8501`:
  - 2-Column Split Estimator layout verified.
  - Ultra-compact 2-line spare parts rows (~48px height) verified.
  - 4-Way Valve Bypass (Rs. 1,500) and AC Service Charges (Rs. 3,500) real-time calculation verified.
  - Official Estimate Breakdown receipt and WhatsApp quotation generation verified.
- **Python Syntax Compilation:** `python -m py_compile app.py config.py database.py etl.py` verified with 0 errors.

---

## 6. Revision History & Version Changelog

| Version | Date | Key Changes & Milestones |
| :--- | :--- | :--- |
| **v2.0** | Sep 2026 | Initial baseline with Master History, KPI Evaluation, and PDF Store Stock parsing. |
| **v2.1** | Oct 2026 | Added missing ERP price exports, cross-model compatibilities, and sequential rankings. |
| **v2.2** | Oct 2026 | Integrated Turso Cloud Database persistence (libSQL over HTTP), TCP Keep-Alive connection pooling, and Streamlit query caching. |
| **v2.3** | Oct 2026 | **Sleek Corporate Claymorphism UI Overhaul:**<br>• Converted Estimator to 2-Column Split Dashboard (Catalog Left, Checkout Right).<br>• Implemented Ultra-Compact 2-Line Spare Parts rows (~48px height, 65% space reduction).<br>• Eliminated bulky expander boxes; introduced hover tooltips for cross-model fits.<br>• Added 4-Way Valve Bypass (Rs. 1,500) and AC Service Charges (Rs. 3,500).<br>• Removed redundant Customer Warranty Status selector.<br>• Relocated Operations & Support help box to the Sidebar footer.<br>• Formalized Mandatory Continuous PRD Maintenance & Versioning Policy. |
| **v2.4** | Oct 2026 | **Technician Performance Hub Upgrade (Module 3):**<br>• Added multi-branch filtering (defaulting to `Karachi 2 HA` with `-- All Branches --` option).<br>• Dynamically updated 5 top KPI cards to switch between Branch metrics and individual Technician Personal Score.<br>• Renamed Zone Efficiency to `Branch Efficiency` (and `Personal Efficiency` for individual technicians).<br>• Replaced Completion Rate in ranking table with `Avg Days` (turnaround time, clamping negative days to 0 for same-day closures).<br>• Eliminated ghost blank technician rows from the table while retaining unassigned jobs in branch totals.<br>• Implemented visual row highlighting for the selected technician in the full ranking table.<br>• Upgraded `tech_performance_master` schema in Turso Cloud and local SQLite with `branch_name` and `days`. |
