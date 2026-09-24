# ❄️ DWP Service Field Assistant

Enterprise field logistics, parts diagnostic, live inventory tracking, cost estimation, unit historical audits, and technician KPI evaluation platform for Gree & EcoStar home appliances.

---

## 🏛️ System Architecture

The application is structured into decoupled, single-responsibility modules to ensure high throughput, fault tolerance, and zero-conflict data isolation:

```text
estimator/
├── config.py          # Business rules, pricing constants, tonnage & appliance category logic, and ERP mappings
├── database.py        # SQLite connection pooling (WAL mode), schemas (parts, stock, history, KPI), and indexed queries
├── etl.py             # Data ingestion (Feedback, Collection, STOCK_DETAIL), auto-discovery, and pricing resolution
├── app.py             # Pure Streamlit UI, responsive cards, live stock badges, interactive cart, and WhatsApp generator
├── requirements.txt   # Production dependencies (streamlit, pandas, openpyxl)
└── dwp_service.db     # High-performance local SQLite database (Auto-generated & isolated)
```

---

## 🚀 Key Modules & Capabilities

1. **🧮 Smart Cost & Live Stock Estimator**:
   - **Model-Wise Parts**: Select appliance model to view compatible parts with live stock badges (`🟢 In Stock`, `🟡 Low Stock`, `🔴 Out of Stock / NIL`).
   - **⚡ Direct Part Search**: Global instant search across warehouse inventory by Part Number or Description.
   - **🛒 Interactive Basket**: Multi-item selection with quantity selector (`Qty: 1, 2, ...`), custom miscellaneous additions, and real-time out-of-stock warnings.
   - **Dynamic Overheads**: Category-aware service charges (Split AC, Floor Standing AC, Refrigerator, Washing Machine, LED TV, Water Dispenser).
   - **📲 WhatsApp Quotation**: One-click professional estimate generator for customer dispatch.

2. **📦 Live Inventory & Stock Sync (Module 4)**:
   - 1-Click UI upload for `STOCK_DETAIL` / `Stock Balance Locator Wise` files from Oracle ERP.
   - Automatic local folder discovery from `.` and `C:\temp`.
   - Real-time stock balance (`bal_qty`) and inventory valuation tracking.

3. **🔍 Unit & Customer Service History (Module 1 & 2)**:
   - Instant search across closed complaints by Serial No, Customer Phone, or Complaint Number.

4. **📊 Technician Performance Evaluation (Module 3)**:
   - KPI metrics (Assigned, Completed, Canceled, Rejected, Nil) and completion rates across custom date ranges.