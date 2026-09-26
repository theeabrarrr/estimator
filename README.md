# ❄️ DWP Service Field Assistant & Estimator Platform

Enterprise field logistics, parts diagnostic, live inventory tracking, cost estimation, unit historical audits, and technician KPI evaluation platform for **Gree & EcoStar** home appliances.

Deployed & Live on Streamlit Cloud.

---

## 🏛️ System Architecture & File Roles

The system is decoupled into single-responsibility modules designed for zero data collisions, high throughput, and 100% price consistency across cloud restarts:

```text
estimator/
├── config.py                 # Core business rules, overheads, tokenizer, series tokens, and role price floors
├── build_baseline.py         # Ground-truth matrix builder: processes ERP reports into high-speed baseline JSON
├── database.py               # Tiered compatibility matching (T1, T2, T3), stock queries, SQLite WAL connection pooling
├── etl.py                    # Real-time ERP ingestion (Stock, Quality Feedback, Collection), bootstrap on cold start
├── app.py                    # Streamlit frontend (Estimator UI, live stock badges, WhatsApp quote generator)
├── test_system_verification.py # Automated test suite (9 tests verifying pricing, series isolation, floors, overheads)
├── data/
│   ├── ground_truth_baseline.json # Pre-computed 354+ models, 186+ series platforms, and complete verified price book
│   └── stock_inventory_latest.csv # Authoritative in-repo ERP stock inventory balance
├── requirements.txt          # Python dependencies (streamlit, pandas, openpyxl)
└── dwp_service.db            # High-performance local SQLite database (Auto-generated on cold start)
```

---

## ⚙️ Core Technical Workflows

### 1. Ground-Truth Baseline Matrix (`build_baseline.py`)
- Reads 12,000+ historical complaint jobs from `quality_feedback_report_*.csv` and 2,400+ warranty/cash collection transactions from `Detail_Collection_*.xlsx`.
- Verifies exact customer/warranty replacement costs for 250+ distinct hardware parts (`part_verified_prices`).
- Enforces strict chassis-sensitive component isolation (Evaporators, Inverter PCBs, Indoor Main PCBs) so that unrelated series (e.g., PITH vs CITH vs ZITH) or incompatible tonnages (1.0 Ton vs 1.5 Ton) never cross-contaminate.
- Outputs `data/ground_truth_baseline.json`, ensuring the app operates with instant latency and **zero Nil/Rs. 0 pricing** even on fresh Streamlit Cloud deployments.

### 2. Tiered Compatibility Engine (`database.py`)
When a user selects a model (e.g., `GS-18ZITH1W-T3`):
- **Tier 1 (Exact Model Ground-Truth)**: Parts with field-verified job history on this exact model, scored by replacement frequency (`verified_jobs * 2 + in_stock bonus`).
- **Tier 2 (Series Platform Compatible)**: Parts matching the exact platform series key (`Brand|Category|Tonnage|Series`), e.g., `Gree|Split AC|1.5 Ton|ZITH`.
- **Tier 3 (Direct Stock Family Reference)**: Live warehouse stock items explicitly referencing the model or series family in their item description.

### 3. Authoritative Pricing Resolution
To ensure **100% price consistency** between **Model Search** and **Direct Part Search**:
1. **Verified ERP Collection Price** (`Detail_Collection` warranty claim amount, e.g., Evaporator `11001062414` = Rs. 30,000).
2. **Live Stock Master Unit Price** (`stock_master.unit_price`).
3. **Role Price Floor Protection** (`get_role_price_floor` in `config.py`): Prevents fractional FOB accounting costs (e.g. `1000106068502` at ledger fraction 12,036) from reaching the customer; floors 1.5 Ton evaporators at realistic market price (Rs. 26,000).
4. **Zero-Price Immunity**: All parts without verified job history receive category/role floor defaults.

### 4. Component Classification & Packaging Filter (`config.py`)
- Non-functional packaging (`carton`, `packing`, `tray`, `support`, `foam`, `bracket`, `box`) is filtered **before** cooling/electrical classification.
- Packing cartons for evaporators (e.g., `03010102510004`) are classified under `📦 Hardware & Components` and never pollute `❄️ Evaporator Assemblies`.

---

## 🛠️ Developer & AI Agent Reference Manual

If you need to make future changes, use this guide to identify where to start:

| Goal / Modification | Target File | What to Edit / Functions Involved |
| :--- | :--- | :--- |
| **Change Service Overheads** (Visit, Mobility) | `config.py` | Update `CATEGORY_OVERHEADS` dictionary (`visit`, `mobility`). Current standard: Mobility=Rs. 2,000, Visit=Rs. 600. |
| **Change Gas Charges** (R-410a, R-32, R-600, R-134a) | `config.py` | Update `get_tonnage_specs()` and `CATEGORY_OVERHEADS` (Ref=Rs. 4,000, Dispenser=Rs. 3,500, ACs=by tonnage). |
| **Add a New Platform Series Token** (e.g. `XITH`, `NITH`) | `config.py` & `build_baseline.py` | Add the series token to `tokenize_appliance_model` in `config.py` and `series_token_list` in `build_baseline.py`. |
| **Adjust Component Price Floors** | `config.py` | Update `get_role_price_floor(role, ton, cat)`. Floor protects major assemblies against fractional ledger ratios. |
| **Add a New Component Role Group** | `config.py` | Add to `COMPONENT_ROLE_GROUPS` list and update regex/keyword matching in `classify_component_role()`. |
| **Update Live Stock Inventory** | `data/stock_inventory_latest.csv` | Drop new CSV into `data/` or upload via Module 4 in the UI. Then run `python build_baseline.py` to regenerate baseline. |
| **Modify Matching Logic or Ranking Scores** | `database.py` | Edit `fetch_tiered_compatible_parts()`, `is_series_compatible()`, or `search_stock_global()`. |
| **Modify UI Cards / WhatsApp Quotation** | `app.py` | Look for `render_primary_card()`, `render_alternative_card()`, or `generate_whatsapp_quotation()`. |

---

## 🧪 Verification & Testing Suite

Always run the automated verification suite after making any modifications:

```bash
python test_system_verification.py
```

### Automated Checks Performed:
1. **Bootstrap & Stock Metadata**: Ensures stock master loads and counts are > 0.
2. **Strict Model Tokenizer**: Tests parsing of series, tonnages, and appliance categories.
3. **Cross-Series Isolation**: Asserts zero cross-contamination (e.g., PITH vs CITH evaporators).
4. **Zero-Price Immunity**: Validates 550+ parts across 7 appliance models are all > Rs. 0.
5. **Global Stock Search**: Tests full-text search across warehouse inventory.
6. **ZITH Evaporator Verification**: Tests `GS-18ZITH1W-T3` for primary and alternate evaporators.
7. **Overheads & Gas Pricing**: Asserts Mobility=2000, Visit=600, Ref Gas=4000, Dispenser Gas=3500.
8. **100% Price Consistency**: Asserts exact price equality between Model Search and Direct Part Search.
9. **Packaging & Floor Protection**: Asserts cartons are excluded from cooling roles and floors are enforced.

---

## 🚀 Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run automated test suite
python test_system_verification.py

# 3. Launch Streamlit application
streamlit run app.py
```