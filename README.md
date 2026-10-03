# DWP Field Assistant Engine

The **DWP Field Assistant Engine** is a streamlined diagnostic and field operations tool built for Service Center tracking, Customer Complaint History search, and Technician Performance KPI calculations.

---

## 📚 Documentation

The documentation has been divided into two separate guides:

### 1. 📜 [Ground Truth Product Requirement Document (PRD)](PRD.md)
Contains the authoritative Product Requirement Document (PRD) detailing system deliverables, business rules, pricing engines, technical challenges (masail), database schemas, and embedded AI Agent Customer Skills.

### 2. 🧑‍💻 [Technical Guide for Developers](docs/TECHNICAL_GUIDE.md)
Contains technical documentation regarding codebase architecture, database schema (`dwp_service.db`), ETL pipelines, and helper functions.

### 3. 📖 [User Manual (How to Use)](docs/USER_MANUAL.md)
Contains a step-by-step guide for end-users on how to run the application, search for unit history, and generate quotations.

---

## 🚀 Quick Start

To run the application locally, ensure you have Python installed, then run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The application will launch on your default web browser (usually `http://localhost:8501`).