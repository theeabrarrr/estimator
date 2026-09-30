# Original User Request

## 2026-09-29T09:36:19Z

Use a full team of agents to build a 100% autonomous, high-accuracy spare parts estimator and pricing engine that establishes the official DWP Karachi Store Stock Report (vp786.pdf / data/pdf_extracted_stock_report.csv) as the master price catalog, seamlessly fused with ERP closed-complaint field records (quality_feedback_report_28SEP2026_142900.csv and Detail_Collection_28SEP26_023634PM.xlsx).

Working directory: c:\Users\PC\Desktop\estimator  
Branch: feature/autonomous-official-pricing-engine  
Integrity mode: development

## Requirements

### R1. Official DWP Store-Wise Stock & Price Ingestion Pipeline
Automate the extraction and normalization of vp786.pdf (Store Wise Stock Report from 01-Jan-26 to 30-Sep-26, 518 unique parts) into the database:
1. Ingest part_no, canonical item_desc, designated primary model, official retail price, and live store total_stock.
2. Permanently replace the flawed accounting ledger valuation formula (AMOUNT / BAL_QTY) in stock_master with the official executive-approved retail selling prices from the report.

### R2. Autonomous Triangular Ground-Truth Engine
Unify three distinct data sources into an autonomous, non-hardcoded resolution pipeline:
1. Master Price Authority: Official selling price from vp786.pdf.
2. Field Verification Authority: 13,965 closed complaints and 6,150 customer collection receipts to verify real-world field billing rates, quantity multiples, and historical compatibility.
3. Chassis & Model Authority: Appliance model tokenization (Brand, Category, Tonnage, Platform Series) ensuring 0% cross-series and cross-category contamination.

### R3. Autonomous Multi-Tier Spare Parts Resolution
When a technician or user inputs any appliance model (Split AC, Floor Standing, Refrigerator, Washing Machine, Water Dispenser):
1. Tier 1 (Exact Model Match): Return genuine components historically replaced on this model or assigned to this model in the official catalog, priced at the official rate with 100% field descriptions.
2. Tier 2 (Platform Series Match): Return platform-compatible components for the same series and capacity.
3. Tier 3 (Store In-Stock Fallback): Return live in-stock store items with strict physical line/capacity constraints (e.g. 1.0T -> 3/8" + 1/4"; 1.5T -> 1/2" + 1/4"; 2.0T/3.0T -> 5/8" + 1/4"; 4.0T -> 5/8" + 3/8").

### R4. Fully Autonomous Self-Healing & Verification Engine
Build an automated regression and verification suite:
1. Systematically validates pricing and compatibility across all appliance categories.
2. Tests for zero-pricing immunity (no part ever shows Rs. 0).
3. Verifies that no corrupted accounting costs leak into user estimates.

## Acceptance Criteria

### Master Price Catalog Accuracy
- All 518 parts from vp786.pdf are indexed with their official selling prices in stock_master and parts_master.
- 3/8" Valve (71302395) displays Rs. 1,500 across all 1.0 Ton AC models and direct searches.
- 1/4" Valve (7130239) displays Rs. 1,600 across all models and direct searches.
- 1/2" Valve (7133774) displays Rs. 2,100 across all 1.5 Ton models.
- 5/8" Valve (7133844) displays Rs. 2,200 across all 2.0 Ton and 3.0 Ton models (including GF-36TFIH).
- Evaporator prices match the official price list (GF-36TFIH = Rs. 58,000; GS-18PITH1W = Rs. 26,000; GS-18AITH23W-T3 = Rs. 30,000; GF-48FW = Rs. 70,000; GF-24ISH = Rs. 72,000; GF-48TF = Rs. 75,000; GF-24CB = Rs. 66,000).

### Physical Compatibility & Zero Contamination
- GF-36TFIH returns ONLY genuine 3.0T Evaporator 11001000602, 5/8" Suction Valve 7133844 (Rs. 2,200), and 1/4" Liquid Valve 7130239 (Rs. 1,600). Zero leakage of 24ISH or 48FW evaporators.
- Every AC model displays exactly its physically compatible valve pair with zero clutter of unrelated valve sizes.

### Automated Verification
- python test_system_verification.py executes all automated test cases and completes with 100% pass rate and 0 errors.

## 2026-09-29T13:14:58Z

The user accidentally stopped you earlier. Please resume your work exactly from where you left off. The 14 system tests are currently passing. Proceed with the remaining milestones (Milestone 2 and 3).

## 2026-09-30T08:11:26Z

The server was restarted, which paused your progress. Please resume your work exactly from where you left off yesterday (Milestone 2/3). Also, please provide a short progress report in your reply so I can show the user a progress bar (e.g. what percentage is done).
