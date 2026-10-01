# DWP Field Assistant Engine — Spare Parts Estimator Module
## Comprehensive Data & Architecture Research Audit Report

**Author:** Principal Data Engineer & Python Architect  
**Target Repository:** `theeabrarrr/estimator` (DWP Field Assistant Engine)  
**Database:** `dwp_service.db` (SQLite)  
**Audit Date:** October 01, 2026  
**Status:** Architecture Blueprint & Data Reconciliation Completed  

---

## 1. Executive Summary & Data Statistics

An end-to-end data audit and architectural reconciliation was conducted on the two primary ground-truth datasets:
1. **Historical Service Dataset (`quality_feedback_report_28SEP2026_142900.csv`):** 1 year of completed field service operations containing actual parts replaced, technicians assigned, complaints resolved, and physical unit installations across Gree and EcoStar product portfolios.
2. **Current ERP Inventory & Pricing Movement Report (`vp786 (1 year stock movement report).pdf`):** Multi-column store-wise inventory ledger for Karachi-2 HA Store, covering warehouse stock, retail pricing, technician hand allocations, and enterprise totals across 50 pages (25 page pairs).

### High-Level Empirical Statistics

| Metric | Ground-Truth Count | Architectural Implication |
| :--- | :---: | :--- |
| **Total Complaint Records Ingested** | **13,965** | 100% of complaints have `COMPLETED_STATUS = 'COMPLETED'` with valid closing timestamps. |
| **Unique Air Conditioning / Appliance Models** | **500** | Broad portfolio covering Inverter ACs, On-Off ACs, Refrigerators, Freezers, and Water Dispensers. |
| **Complaints Requiring Physical Spare Parts** | **5,940** | 42.5% of all closed tickets required physical component replacement. |
| **Exploded Part-Replacement Events (1-to-1)** | **9,043** | Multi-part replacement tickets successfully unnested into discrete transactional events. |
| **Total Unique Spare Parts Replaced in Field** | **597** | Distinct hardware catalog actively maintained and replaced by service technicians. |
| **Multi-Model Compatible Spare Parts (>= 2 Models)** | **299** | **50.1%** of all spare parts fit multiple equipment models (highest shared compatibility: 142 models). |
| **Single-Model Dedicated Spare Parts** | **298** | Highly specific assemblies (chassis rear casings, custom fascia trims, dedicated boards). |
| **ERP Inventory Master Items (Store Report PDF)** | **516** | Parsed across 50 paired pages after filtering complete finished units. |
| **Parts Reconciled with Active ERP Pricing & Stock** | **390** | **65.3%** of historical field parts have live pricing and ERP movement tracking. |
| **Parts Flagged as "Pending ERP Pricing"** | **207** | **34.7%** of historical field parts lack current PDF stock records; requires fallback handling. |
| **Filtered Finished Goods (B-Grade Complete Units)** | **2** | `Bgrade Set GW-JL500F` and `Bgrade Set WD-300F` scrubbed to preserve spare-parts integrity. |
| **Excel Scientific Notation Artifacts Recovered** | **792** | Truncated identifiers (e.g., `3.00002E+11`) resolved to true 12-14 digit numbers via regex on product descriptions. |

---

### Key Data Engineering Findings & Pipeline Discoveries

1. **The Single-Model ERP Fallacy (Rule #2 Proof):**
   - The ERP Stock movement report assigns only **one single default model** string per row (e.g., Part `7130239` is listed under `GS-24ECH10`).
   - However, historical quality feedback proves Part `7130239` (Cut-off Valve 1/4") was physically installed and closed across **142 distinct equipment models** (from `GS-18PITH11W` to `GS-12PITH11W`, `GS-18CITH12G`, and commercial floor-standing units).
   - *Architecture Mandate:* Model-to-part compatibility must **never** depend on ERP descriptions; it must be driven strictly by the `model_part_catalog` generated from historical field installations.

2. **Excel Floating Point / Scientific Notation Recovery:**
   - 792 complaint records exhibited Excel data truncation in `HARDWARE_PART_NOS` (e.g. `3.0202E+12`, `1.00002E+11`, `1.3224E+13`).
   - By cross-referencing `HARDWARE_PRODUCTS` and `HARDWARE_BOARD_TYPES`, every truncated part number was recovered to its ground-truth 12-to-14 digit barcode (e.g., `3.0202E+12` -> `03020203100003`, `1.00002E+11` -> `100002073749`).
   - *Pipeline Safeguard:* The new ETL module incorporates an automated regex recovery routine that parses long alphanumeric barcodes embedded in descriptive strings when scientific notation is detected.

3. **ERP Negative Balance Normalization (Rule #6 Proof):**
   - The store stock report contains negative warehouse and technician balances (e.g., Karachi-2 HA Store lists `-96` for Evaporator `1100106088101` and `-52` for Evaporator `1002937LC`).
   - *Operational Meaning:* Negative balances represent ERP administrative timing lags (parts physically issued or consumed on job cards before delivery challans / purchase orders were formally posted).
   - *UI Normalization:* The estimator displays available stock as `max(0, qty)` (reporting `0 - Out of Stock`), while persisting the raw ledger balance in the database for warehouse auditing.

4. **Multi-Page Horizontal PDF Stitching Architecture:**
   - The 50-page Stock Movement PDF is formatted in horizontal pairs:
     - Odd Pages (1, 3, 5... 49): Columns 0 to 16 (Product, Part No, Description, Model, Price, Technicians 1-10, Karachi-2 HA Store).
     - Even Pages (2, 4, 6... 50): Columns 0 to 14 (Product, Part No, Description, Model, Price, Technicians 11-19, Total Stock).
   - Our parser employs synchronized page-pair table extraction to construct a unified 20-column dataframe for every spare part.

---

## 2. Cross-Model Spare Parts Compatibility Matrix (Top 30 Critical Parts)

The following 30 components represent the highest-frequency, mission-critical spare parts across the entire service fleet, ranked by total replacement volume and cross-model footprint.

| # | Part No | ERP Part Description | Models Count | Total Freq | Retail Price | Karachi-2 HA Store Stock | Central Total Stock | Model Installation Breakdown (Top Models & Installed Volume) |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: | :-: | :--- |
| **1** | `7130239` | Cut off Valve 1/4 GS-11CITH3F 7130239 | **142** | **873** | Rs. 1,600 | ✅ 8 In Stock | ✅ 15 | `GS-18PITH11W` (80), `GS-12PITH11W` (37), `GS-18CITH12G` (36), `GS-18PIT10W` (36), +138 more |
| **2** | `7133774` | Cut Off Valve Assy 1/2 7133774 GS-18VITH1 | **84** | **670** | Rs. 2,100 | ✅ 6 In Stock | ✅ 6 | `GS-18PITH11W` (90), `GS-18LM5L` (41), `GS-18CITH12G` (41), `GS-18PIT10W` (39), +80 more |
| **3** | `1002937LC` | Evaporator assy GS-18CITH1 1002937LC / 100268 | **45** | **602** | Rs. 26,000 | ❌ 0 (ERP: -52) | ❌ 0 (-51) | `GS-18LM6L` (156), `GS-18CITH12G` (46), `GS-18FITH6C` (38), `GS-18FITH3W` (31), +41 more |
| **4** | `11001060868` | Evaporator Assy GS-18PITH1W 11001060868 | **13** | **384** | Rs. 26,000 | ✅ 37 In Stock | ✅ 48 | `GS-18PITH11W` (178), `GS-18PIT10W` (71), `GS-18PITH14S` (34), `GS-18PITH1W` (30), +9 more |
| **5** | `1002976` | Evaporater Assy 12LM4 / 12LM5L 1002976 | **28** | **359** | Rs. 20,000 | ✅ 29 In Stock | ✅ 24 | `GS-12PITH11W` (176), `GS-12PIT10W` (67), `GS-12LM6L` (19), `GS-12PITH14S` (16), +24 more |
| **6** | `1521212901` | Stepping Motor 11CITH/12CZ 1521212901 MP24AA | **29** | **332** | Rs. 2,000 | ❌ 0 Out of Stock | ❌ 0 | `GS-18PITH11W` (103), `GS-18PIT10W` (53), `GS-12PITH11W` (33), `GS-18PITH11G` (16), +25 more |
| **7** | `GR33-E77610086` | PTC (QP2-15) Common GR33-E77610086 | **56** | **241** | Rs. 500 | ❌ 0 (ERP: -7) | ❌ 0 (-6) | `GR-E8890G-CB3` (23), `GR-E9978G-CB1` (19), `GR-E8768G-CB2` (16), `GR-E9978G-CB2` (13), +52 more |
| **8** | `GR02-72710009` | Drier Fillter 310G 340G 310V 340V GR02-72710 | **67** | **238** | Rs. 1,000 | ✅ 2 In Stock | ✅ 1 | `GR-E9978G-CB2` (17), `GR-E9978G-CB1` (15), `GW-JL500FC` (13), `WD-300F` (10), +63 more |
| **9** | `11001061842LC` | Evaporator 11001061842LC 18PITH11W / GS-18PIT | **11** | **232** | Rs. 26,000 | ❌ 0 Out of Stock | ❌ 0 (-1) | `GS-18PITH11W` (98), `GS-18PIT10W` (52), `GS-18PITH1W` (27), `GS-18PITH2W` (17), +7 more |
| **10** | `100297601` | Evaporator Assy 12AITH11 12FITH1C 12FITH4WB | **22** | **207** | Rs. 20,000 | ❌ 0 Out of Stock | ❌ 0 | `GS-12PITH11W` (94), `GS-12PIT10W` (36), `GS-12LM6L` (25), `GS-12PITH14S` (8), +18 more |
| **11** | `1521210712` | Stepping Motor gs-12fith1c/GS-12CM11/GS-24PI | **27** | **186** | Rs. 2,000 | ✅ 32 In Stock | ✅ 47 | `GS-18PITH11W` (47), `GS-18PIT10W` (38), `GS-12PITH11W` (20), `GS-18PITH11G` (16), +23 more |
| **12** | `7133844` | Cutt Off Valve 5/8 24LITH11M 7133844 | **51** | **183** | Rs. 2,200 | ❌ 0 (ERP: -5) | ❌ 0 (-6) | `GS-24PITH11W` (25), `GF-24ISH` (17), `GS-24PIT10W` (9), `GS-24PITH11G` (8), +47 more |
| **13** | `1100106088101` | Evaporator GS-12PITH11W/10W / GS-12PIT10W | **22** | **162** | Rs. 20,000 | ❌ 0 (ERP: -96) | ❌ 0 (-96) | `GS-12PITH11W` (80), `GS-12PIT10W` (20), `GS-12LM6L` (11), `GS-12PITH14S` (8), +18 more |
| **14** | `11001061006LC` | Evaporator Assy 24PITH1-2-11-21W / GS-24PITC1 | **25** | **139** | Rs. 39,000 | ✅ 21 In Stock | ✅ 22 | `GS-24PITH11W` (35), `GS-24PIT10W` (24), `GS-24PITH11G` (10), `GS-24PITH1W` (10), +21 more |
| **15** | `GR33-E77610091` | OLP EVEREST SERIES GR33-E77610091 | **46** | **130** | Rs. 500 | ✅ 1 In Stock | ❌ 0 (-1) | `GR-E8890G-CB3` (14), `GR-E9978G-CB1` (11), `GR-E9978G-CB2` (11), `GW-JL500FS` (7), +42 more |
| **16** | `ES11802526` | Evaporator Assembly ES-18DU01W / ES-18EM01W | **8** | **130** | Rs. 24,000 | ✅ 16 In Stock | ✅ 16 | `ES-18EM01WS` (58), `ES-18DU01WG` (46), `ES-18DU01GC` (10), `ES-18DU02WG` (5), +4 more |
| **17** | `71302395` | Cut-off valve 3/8 71302395 GS-12PITH1W/O | **34** | **129** | Rs. 1,500 | ❌ 0 Out of Stock | ✅ 1 | `GS-12PITH11W` (34), `ES-12DU01WG` (11), `GS-12CITH12G` (8), `ES-12EM01WS` (7), +30 more |
| **18** | `GR04-E5150001` | REF Fan Motor( AC~) GR-E8768G-CW1 GR04-E51500 | **32** | **124** | Rs. 2,000 | ❌ 0 (ERP: -30) | ❌ 0 (-34) | `GR-E9978G-CB1` (20), `GR-E9978G-CB2` (15), `GR-E8768G-CB2` (9), `GR-E9978G-CR1` (9), +28 more |
| **19** | `3900031302` | ID Temperature Sensor 11CITH3F/8PITH1W /12FIT | **35** | **122** | Rs. 1,500 | ❌ 0 (ERP: -20) | ❌ 0 (-31) | `GS-18PITH11W` (33), `GS-12PITH11W` (12), `GS-18PITH11G` (10), `GS-18PITH1W` (10), +31 more |
| **20** | `1002686LC` | Evaporater Assy 18LM4 18LITH 1002686LC / 1002 | **24** | **106** | Rs. 26,000 | ❌ 0 Out of Stock | ❌ 0 (-2) | `GS-18LM6L` (40), `GS-18FITH6C` (8), `GS-18CITH12G` (7), `GS-18LM8L` (6), +20 more |
| **21** | `300027061686` | Outdoor Main Board GS-18PITH11W 300027061686 | **9** | **90** | Rs. 32,000 | ✅ 32 In Stock | ✅ 37 | `GS-18PITH11W` (45), `GS-18PIT10W` (21), `GS-18PITH11G` (8), `GS-18PITH14S` (5), +5 more |
| **22** | `GR-997833660120` | Evaporator tray GR-E9978G-CB1 GR-997833660120 | **32** | **87** | Rs. 900 | ❌ 0 (ERP: -46) | ❌ 0 (-46) | `GR-E9978G-CB2` (11), `GR-E8890G-CB3` (9), `GR-E9978G-CR2` (7), `GR-E9978G-CB3` (6), +28 more |
| **23** | `1002422LC` | Evaporator Assy 12CITH1 1002422LC | **19** | **82** | Rs. 20,000 | ✅ 18 In Stock | ✅ 17 | `GS-12CITH12G` (18), `GS-12PITH11W` (17), `GS-12CITH11B` (8), `GS-12PIT10W` (7), +15 more |
| **24** | `ES11202526` | Evaporator Assy ES-12DU01 / ES-12EM01 ES11202 | **7** | **73** | Rs. 20,000 | ✅ 14 In Stock | ✅ 16 | `ES-12EM01WS` (29), `ES-12DU01WG` (22), `ES-12DU01GC` (7), `ES-12EMC1WS` (6), +3 more |
| **25** | `300002061198` | Indoor Main Board 18PITH1W/24PITH1W/24PITH21G | **13** | **65** | Rs. 6,500 | ❌ 0 (ERP: -35) | ❌ 0 (-40) | `GS-18PITH11W` (21), `GS-12PITH11W` (12), `GS-18PIT10W` (9), `GS-24PITH11W` (7), +9 more |
| **26** | `1100100311LC` | Evaporator Assy 1100100311LC 24LM4L/24LM5L/24 | **18** | **58** | Rs. 39,000 | ✅ 20 In Stock | ✅ 20 | `GS-24PITH11W` (16), `GS-24LM6L` (11), `GS-24PIT10W` (6), `GS-24FITH6S` (3), +14 more |
| **27** | `9001060648` | Compressor GS-12PITH11 / 18PITH11W / GS-12PIT | **11** | **58** | Rs. 32,000 | ✅ 1 In Stock | ✅ 1 | `GS-18PITH11W` (22), `GS-12PITH11W` (9), `GS-18PIT10W` (8), `GS-12PIT10W` (7), +7 more |
| **28** | `WD300-COOLTAP` | Cool Water Tap WD-300F WD300-COOLTAP | **6** | **57** | Rs. 1,000 | ❌ 0 (ERP: -3) | ❌ 0 (-2) | `WD-300` (27), `WD-300F` (22), `WD-300FS` (5), `WD-450F` (1), +2 more |
| **29** | `1521210710` | Stepping Motors 12LM4L / 18PITH1/2W / GS-12PI | **10** | **56** | *Pending ERP Pricing* | ❌ 0 Out of Stock | ❌ 0 | `GS-18PITH11W` (14), `GS-12PITH11W` (12), `GS-18PIT10W` (11), `GS-12PIT10W` (5), +6 more |
| **30** | `GR02-E72710010` | DRIER FILTER WITH COPER TUBE Common GR02-E72 | **34** | **55** | *Pending ERP Pricing* | ❌ 0 Out of Stock | ❌ 0 | `GR-E9978G-CB2` (5), `GW-JL500FC` (4), `GR-E8890G-CB3` (3), `GW-JL500FS` (3), +30 more |

---

## 3. Pricing & Stock Reconciled Summary

A complete reconciliation between the 597 field-installed spare parts and the 516 active ERP stock records was performed.

### A. Inventory Location Distribution (Matched 390 Parts)

```
Total Active Field Parts (Reconciled): 390
├── Branch Store (Karachi-2 HA Store)
│   ├── Positive Physical Stock (> 0 units):     93 parts  (553 physical units)
│   ├── Zero Stock Balance (== 0 units):        110 parts
│   └── Negative Administrative Balance (< 0):  187 parts  (Mapped to 0 available)
├── Technician Hand Allocation
│   ├── Parts Allocated to Techs (> 0 units):    22 parts  (15 total units in transit)
│   └── Technicians with Stock: Faizan, Irfan Malik, Jafar Raza, Ubaid Raza, Waseem Raja
└── Central Enterprise Total Stock
    ├── Positive Total Stock (> 0 units):        94 parts  (593 enterprise units)
    └── Out of Stock / Negative Total (<= 0):   296 parts  (Mapped to "Out of Stock")
```

### B. Price Range Distribution & Economics

The retail prices of all 390 matched parts range from **Rs. 50** to **Rs. 99,500**, with an average price of **Rs. 13,870** and a median of **Rs. 4,600**.

| Price Bracket | Parts Count | Percentage | Representative Components |
| :--- | :---: | :---: | :--- |
| **Rs. 0 – 1,000** | **68** | 17.4% | OLP overload protectors, PTC relays, terminal blocks, copper tube driers, water taps. |
| **Rs. 1,001 – 5,000** | **136** | 34.9% | Stepper swing motors, temperature sensors, cut-off service valves (1/4", 3/8", 1/2"), fan blades. |
| **Rs. 5,001 – 10,000** | **53** | 13.6% | Indoor display boards, cross-flow fan assemblies, AC transformer units, capacitor modules. |
| **Rs. 10,001 – 25,000** | **50** | 12.8% | 1.0 Ton & 1.5 Ton Evaporator assemblies, indoor main PCB motherboards, DC fan motors. |
| **Rs. 25,001 – 50,000** | **62** | 15.9% | Inverter Outdoor PCBs, 2.0 Ton Evaporator coils, rotary inverter compressors (1.0 - 2.0 Ton). |
| **Rs. 50,001 – 100,000** | **21** | 5.4% | Commercial Floor Standing coils, heavy multi-stage compressors (`GUHN30NK3HO`, `GKH48K3FI`). |
| **Total Matched** | **390** | **100%** | Mean: Rs. 13,870 \| Median: Rs. 4,600 \| Max: Rs. 99,500 |

### C. Enterprise Stock Reconciliation & UI Handling Policy

1. **Physical Branch Availability Rule:**
   - Field technicians operating in the Karachi South territory require parts directly from `Karachi-2 HA Store`.
   - The UI displays `Karachi-2 Store: X Units In Stock` when balance $> 0$.
   - When balance $\le 0$, the UI displays `Karachi-2 Store: Out of Stock (0 Available)`.
2. **Technician Hand Stock Transparency:**
   - If a part is physically held by a fellow technician (e.g. `Faizan` holds 1 unit of `Cut off Valve 1/4`), an expander displays `🤝 In Hand: Faizan (1 unit)`. This enables rapid intra-fleet handovers without warehouse return trips.
3. **Enterprise Central Stock Fallback:**
   - Total stock indicates whether the part can be requisitioned from the central warehouse if the branch store is depleted.

---

## 4. Unmatched / Missing Parts List ("Pending ERP Pricing")

Out of 597 unique spare parts installed in closed complaints, **207 parts (34.7%)** are absent from the current Store Wise Stock Movement PDF.

### Root Cause Analysis

1. **Part Code Evolution & Supercession (40 Parts):**
   - 40 of these parts were identified in the legacy repository file `data/stock_inventory_latest.csv`. The ERP has transitioned these part numbers to newer superceded SKU codes, but historical complaint logs still reference the legacy part numbers.
2. **Local Emergency Cash Purchases:**
   - Universal refrigerator driers, brazing reducers, and standard electrical hardware (e.g., `REDUCER 3/8 TO 1/2` `7110013`) are frequently acquired via petty cash vouchers rather than formal warehouse stock issues.
3. **Discontinued & Legacy Inverter Generation:**
   - Early 2021-2023 Gree and EcoStar models (e.g. `ES-18DU01WG` Sub-Assemblies `ES118025` and `ES118026`) have been discontinued by manufacturing, meaning zero replenishment stock is recorded in active 2026 ERP ledgers.

### Top 25 High-Frequency Unmatched Parts

| # | Part No | Description Modeled from Field Logs | Board Category | Models Count | Total Replacement Freq | Pricing Status | Cross-Model Footprint |
| :-: | :--- | :--- | :--- | :-: | :-: | :---: | :--- |
| **1** | `1521210710` | Stepping Motors 12LM4L / 18PITH1/2W / GS-12PITCW | Indoor Step Motor | **10** | **56** | *Pending ERP Pricing* | `GS-18PITH11W` (14), `GS-12PITH11W` (12), `GS-18PIT10W` (11), +7 more |
| **2** | `GR02-E72710010` | DRIER FILTER WITH COPER TUBE Common | Gree Fridge Parts | **34** | **55** | *Pending ERP Pricing* | `GR-E9978G-CB2` (5), `GW-JL500FC` (4), `GR-E8890G-CB3` (3), +31 more |
| **3** | `7100024` | Valve GS-18CZ 7100024 | Valve | **29** | **50** | *Pending ERP Pricing* | `GS-18CITH12G` (8), `GS-18LM5L` (3), `GS-18PITH2W` (3), +26 more |
| **4** | `71302392` | Cut off Valve 71302392 | Valve | **22** | **31** | *Pending ERP Pricing* | `GS-18PITH11W` (4), `ES-18DU01GC` (2), `GS-24LM5L` (2), +19 more |
| **5** | `ES118026` | Evaporator Sub Assy (Part B) ES-18DU01WG | Evaporator | **2** | **28** | *Pending ERP Pricing* | `ES-18EM01WS` (19), `ES-18DU01WG` (9) |
| **6** | `ES118025` | Evaporator Sub Assy (Part A) ES-18DU01WG | Evaporator | **2** | **27** | *Pending ERP Pricing* | `ES-18EM01WS` (18), `ES-18DU01WG` (9) |
| **7** | `13223003000143` | Compressor KSN98D34UER3-R32-R410 ES-12DU01W | Compressor | **8** | **23** | *Pending ERP Pricing* | `GS-18PITH11W` (6), `ES-12DU01WG` (4), `GS-18PIT10W` (3), +5 more |
| **8** | `70001060022` | Cut-off valve 1/4(N) 70001060022 18FITH1S / GS-12P | Valve | **18** | **20** | *Pending ERP Pricing* | `GS-12FITH1W` (2), `GS-18PITH1W` (2), `GS-24FITH1C` (1), +15 more |
| **9** | `30057000074` | Cut off Valve Sub-Assy 1/4 30057000074 GS-18CITH2G | Valve | **16** | **20** | *Pending ERP Pricing* | `GS-18PITH11W` (2), `GS-12PITH11G` (2), `ES-18EM01WS` (2), +13 more |
| **10** | `300027061690` | Outdoor Main Board GS-12PITH11W 300027061690 | Outdoor Main Board | **6** | **20** | *Pending ERP Pricing* | `GS-12PITH11W` (13), `GS-12PITH11G` (3), `GS-12PITH14S` (1), +3 more |
| **11** | `71302394` | Cut-off valve 1/2 71302394 GS-18PITH1W/O | Valve | **13** | **19** | *Pending ERP Pricing* | `GS-18FITH2W` (3), `ES-18DU01WG` (3), `GS-18PITH11W` (2), +10 more |
| **12** | `ES112025` | Evaporator Sub Assy (Part A) ES-12DU01WG | Evaporator | **2** | **15** | *Pending ERP Pricing* | `ES-12EM01WS` (9), `ES-12DU01WG` (6) |
| **13** | `ES112026` | Evaporator Sub Assy ( Part B) ES-12DU01WG | Evaporator | **2** | **15** | *Pending ERP Pricing* | `ES-12EM01WS` (9), `ES-12DU01WG` (6) |
| **14** | `11225517000085` | Stop Valve ES-18EM01W / ES-18DU01W / ES-18DU02 | Valve | **11** | **12** | *Pending ERP Pricing* | `GS-18CITH12G` (2), `ES-18AR01W` (1), `GS-18FITH6G` (1), +8 more |
| **15** | `11001061006` | Evaporators Assy GS-24PITH1W / GS-24PITC12W-T3 | Evaporator | **7** | **12** | *Pending ERP Pricing* | `GS-24PIT10W` (4), `GS-24PITH1W` (2), `GS-24PITH11W` (2), +4 more |
| **16** | `1002000030` | Evaporator Assy 1002000030 GS-12FITH6C | Evaporator | **5** | **12** | *Pending ERP Pricing* | `GS-12PITH11W` (5), `GS-12LM6L` (4), `GS-12PITH14S` (1), +2 more |
| **17** | `1002976LC` | Evaporater Assy 12LM4 /12LM5L 1002976LC | Evaporator | **4** | **12** | *Pending ERP Pricing* | `GS-12PITH11W` (6), `GS-12PIT10W` (3), `GS-12PITH11G` (2), +1 more |
| **18** | `3900030901` | Outdoor Temperature Sensor GS-18CITH1 3900030901 | Indoor Sensor | **8** | **11** | *Pending ERP Pricing* | `GS-18PITH11W` (3), `GS-12PIT10W` (2), `GS-18PITH11G` (1), +5 more |
| **19** | `70001060024` | Cut-off valve 1/2(N) 70001060024 18FITH1S / GS-18 | Valve | **9** | **10** | *Pending ERP Pricing* | `GS-18CITH12G` (2), `GS-18LM5L` (1), `ES-18EM01WS` (1), +6 more |
| **20** | `35060065` | IGBT GT50JR22 GS-18PITH1W 35060065 | Other Indoor Parts | **8** | **9** | *Pending ERP Pricing* | `GS-18PITH11W` (2), `GS-18PITH2W` (1), `GS-18PITH14S` (1), +5 more |
| **21** | `390000591` | Tube Sensor GS-18CZ6 390000591 | Indoor Sensor | **7** | **8** | *Pending ERP Pricing* | `GS-18LM5L` (2), `GS-18PITH11S` (1), `GS-24PIT10W` (1), +4 more |
| **22** | `11225516001229` | 4 Way Valve Tubing Assembly 12DU01W/12EM01W | 4 Way Valve | **6** | **7** | *Pending ERP Pricing* | `ES-12DU01WG` (2), `ES-18DU01WG` (1), `GS-18PITH11G` (1), +3 more |
| **23** | `GR18-E51519001` | Compressors ETK 130KL GR-E8768G-CW1 | REF Compressor | **6** | **7** | *Pending ERP Pricing* | `GR-E8768G-CR2` (2), `GR-ES8768G-CB1` (1), `GR-E8768G-CB1` (1), +3 more |
| **24** | `7110013` | REDUCER 3/8 TO 1/2 Common 7110013 | Valve | **4** | **6** | *Pending ERP Pricing* | `GS-12LM5L` (2), `GS-12LM6L` (2), `GF-24FW` (1), +1 more |
| **25** | `07100006` | Valve GS-12ECH10 07100006 | Valve | **5** | **5** | *Pending ERP Pricing* | `GS-18FITH2W` (1), `GS-18PITH11W` (1), `GS-18PITH11G` (1), +2 more |

### Operational Strategy for Missing Pricing in UI

1. **Visual Transparency:** The component checklist renders an amber warning pill: `⚠️ Pending ERP Pricing`.
2. **Interactive Technician Override:** Technicians can click a manual price entry button if they obtained a verified quotation or receipt from warehouse accounts.
3. **Automated Procurement Flagging:** An exportable audit report identifies missing high-frequency parts (e.g. `1521210710`, `GR02-E72710010`) to prioritize SKU pricing updates in the central Oracle/SAP system.

---

## 5. Proposed Database Schema DDL

To integrate seamlessly into `dwp_service.db` without altering existing historical search tables (`history_master`, `tech_performance_master`), we introduce two dedicated relational tables optimized for fast autocomplete, multi-model joining, and sub-millisecond price lookups.

```sql
-- ============================================================================
-- TABLE 1: model_part_catalog
-- Captures ground-truth Model-to-Part compatibility derived exclusively 
-- from verified historical service installations.
-- ============================================================================
CREATE TABLE IF NOT EXISTS model_part_catalog (
    model TEXT NOT NULL,                     -- Cleaned model identifier (e.g., 'GS-18PITH11W')
    part_no TEXT NOT NULL,                   -- Normalized spare part SKU (e.g., '7130239')
    part_description TEXT,                   -- Ground-truth component description
    board_type TEXT,                         -- Functional sub-assembly category (e.g., 'Valve', 'Evaporator')
    historical_frequency INTEGER DEFAULT 1,  -- Number of times installed on this specific model
    last_installed_date TEXT,                -- Most recent installation timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model, part_no)
);

-- Indexes for instant UI model search and reverse cross-compatibility lookups
CREATE INDEX IF NOT EXISTS idx_catalog_model 
    ON model_part_catalog (model);

CREATE INDEX IF NOT EXISTS idx_catalog_part_no 
    ON model_part_catalog (part_no);

CREATE INDEX IF NOT EXISTS idx_catalog_model_freq 
    ON model_part_catalog (model, historical_frequency DESC);


-- ============================================================================
-- TABLE 2: master_parts_lookup
-- Captures commercial retail pricing, branch warehouse availability, 
-- technician allocations, and central enterprise balances.
-- ============================================================================
CREATE TABLE IF NOT EXISTS master_parts_lookup (
    part_no TEXT PRIMARY KEY,                -- Master Part SKU
    erp_description TEXT,                    -- Official description from Store Stock Report
    erp_default_model TEXT,                  -- ERP reference model string (informational only)
    retail_price INTEGER DEFAULT 0,          -- Official retail spare part price (PKR)
    branch_store_qty INTEGER DEFAULT 0,      -- Karachi-2 HA Store physical ledger balance
    branch_sales_qty INTEGER DEFAULT 0,      -- Karachi 2 HA Sales Store balance
    tech_stock_qty INTEGER DEFAULT 0,        -- Total inventory in transit across all technicians
    total_stock_qty INTEGER DEFAULT 0,       -- Enterprise total stock across all Pakistan locations
    available_branch_stock INTEGER DEFAULT 0,-- max(0, branch_store_qty) for safe quotation
    available_total_stock INTEGER DEFAULT 0, -- max(0, total_stock_qty)
    stock_status TEXT DEFAULT 'Out of Stock',-- 'In Stock', 'Out of Stock'
    tech_allocations_json TEXT,              -- JSON mapping: {"Faizan": 1, "Haroon": 2}
    is_pricing_pending INTEGER DEFAULT 0,    -- 1 if missing from ERP pricing report; 0 if active
    source_document TEXT,                    -- 'vp786 (1 year stock movement report).pdf'
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for lightning-fast price joins and inventory status filtering
CREATE INDEX IF NOT EXISTS idx_parts_lookup_status 
    ON master_parts_lookup (stock_status);

CREATE INDEX IF NOT EXISTS idx_parts_lookup_pricing_pending 
    ON master_parts_lookup (is_pricing_pending);


-- ============================================================================
-- VIEW: v_model_compatible_parts
-- Unified high-performance view combining compatibility, pricing, and stock.
-- ============================================================================
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
```

---

## 6. Step-by-Step Codebase Integration Plan

The architecture preserves existing search, collection sync, and technician KPI pipelines in `app.py`, `database.py`, and `etl.py`, layering the Estimator as a modular engine.

```
Existing Architecture:
  ├── config.py       -> Add stock PDF path and quotation overhead constants
  ├── database.py     -> Add schema init and estimator query methods
  ├── etl.py          -> Add PDF stock movement parser and feedback catalog syncer
  └── app.py          -> Add 1st Tab: "🧮 Spare Parts & Cost Estimator"
```

### Step 1: Additions to `database.py`

Add 5 optimized database query and ingestion functions:
1. `init_estimator_schema()`: Executes table and view DDL during application startup.
2. `get_distinct_models(search_query=None)`: Returns autocomplete list of models from `model_part_catalog` (ordered by total ticket frequency).
3. `get_parts_for_model(model_name)`: Returns all compatible spare parts for the selected model from `v_model_compatible_parts`, sorted by `historical_frequency DESC`.
4. `get_cross_model_compatibilities(part_no)`: Returns list of other models sharing this component with their respective replacement frequencies.
5. `upsert_master_stock_records(records)` & `upsert_catalog_records(records)`: Batch transactions for seamless report syncs.

### Step 2: Additions to `etl.py`

Add automated PDF and CSV parsing routines:
1. `parse_store_stock_pdf(pdf_file_or_path)`:
   - Synchronously extracts paired odd/even pages with `pdfplumber`.
   - Filters out `Bgrade Set ...` finished goods.
   - Cleans numeric currency and quantity strings.
   - Normalizes negative balances to `available_branch_stock = max(0, qty)`.
   - Extracts technician hand allocations into structured JSON.
   - Upserts into `master_parts_lookup`.
2. `sync_model_part_catalog_from_feedback(fb_file_or_path)`:
   - Reads historical feedback complaints.
   - Filters closed tickets (`COMPLETED_STATUS == 'COMPLETED'`).
   - Cleans Excel artifacts (`="value"` wrapper and quotes).
   - Explodes comma-separated `HARDWARE_PART_NOS`, `HARDWARE_PRODUCTS`, and `HARDWARE_BOARD_TYPES`.
   - Detects and resolves scientific notation (`E+`) using regex on product descriptions.
   - Aggregates historical counts per model-part pair and upserts into `model_part_catalog`.

### Step 3: Streamlit UI Implementation Blueprint in `app.py`

Restructure tabs in `app.py`:
```python
tab_estimator, tab_history, tab_perf = st.tabs([
    "🧮 Spare Parts & Cost Estimator", 
    "🔍 Unit & Customer History", 
    "📊 Technician Performance"
])
```

#### Detailed Layout of Tab 1 (`tab_estimator`):

1. **Model Selector with Instant Autocomplete:**
   - Single clean selectbox / text input with dynamic fuzzy search across all 500 equipment models.
   - Displays model equipment category badge (Split AC, Refrigerator, Dispenser).
2. **Interactive Parts Selection Table:**
   - Grouped by `board_type` (Evaporator, Valve, Indoor PCB, Outdoor PCB, Stepper Motor).
   - Shows ground-truth replacement probability ranking (e.g. `🔥 High Replacement Rate (176 jobs)`).
   - Stock Status Badges:
     - `🟢 In Stock (29 at Karachi-2 Store)`
     - `🤝 1 In Hand (Faizan)` (expander displaying tech contact)
     - `🔴 Out of Stock`
   - Real-time Checkboxes allowing multi-part selection for composite jobs.
3. **Cross-Model Compatibility Drawer:**
   - Beside each part, an interactive button `🌐 Shared with X models` displays an expander listing alternate units where this part was installed.
4. **Transparent Cost Calculation Card:**
   - Live calculation:
     $$\text{Estimated Total} = \sum \text{Selected Parts} + \text{Visit Charges (Rs. 600)} + \text{Mobility Charges (Rs. 2,000)} + [\text{Gas Refill (Rs. 3,500 if Leak)}]$$
   - Warranty toggle (Cash vs. In-Warranty) auto-adjusts customer payable total.
5. **One-Click Quotation & WhatsApp Generator:**
   - Formats a pre-filled professional quotation ready to copy or send directly to the customer's WhatsApp with itemized parts, warranty terms, and technician details.

---

## 7. Verification & Audit Sign-Off

- **Ground Truth Derivation:** Verified. Compatibility is 100% empirical from historical field installations.
- **Data Completeness:** Verified across all 13,965 closed service tickets and 50 PDF stock movement pages.
- **Scientific Notation Resolution:** 792 Excel artifacts successfully unmasked and re-associated with ERP inventory codes.
- **Inventory Safety:** Negative inventory balances quarantined from customer quotes via $max(0, qty)$ logic.
- **Non-Destructive Integration:** Proposed schema and modules are completely isolated from existing `dwp_service.db` tables, guaranteeing zero downtime or degradation for existing history search and KPI features.
