# ❄️ DWP Service Field Assistant

Enterprise field logistics, parts diagnostic, cost estimation, unit historical audits, and technician KPI evaluation platform for Gree & EcoStar home appliances.

---

## 🏛️ System Architecture

The application is structured into decoupled, single-responsibility modules to ensure high throughput, fault tolerance, and zero-conflict data isolation:

```text
estimator/
├── config.py          # Business rules, pricing constants, tonnage logic, and ERP column mappings
├── database.py        # SQLite connection pooling (WAL mode), schemas, and indexed search queries
├── etl.py             # Data ingestion, regex phone normalization, and priority resolution pipeline
├── app.py             # Pure Streamlit UI, responsive cards, KPI metrics, and WhatsApp link generators
├── requirements.txt   # Production dependencies
└── dwp_service.db     # High-performance local SQLite database (Auto-generated)