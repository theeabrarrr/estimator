# DWP Field Assistant Engine

The **DWP Field Assistant Engine** is a streamlined diagnostic and field operations tool built for Service Center tracking, Customer Complaint History search, and Technician Performance KPI calculations.

---

## 📚 Documentation

The documentation has been divided into two separate guides:

### 1. 🧑‍💻 [Technical Guide for Developers](docs/TECHNICAL_GUIDE.md)
Contains full documentation regarding the codebase architecture, database schema (`dwp_service.db`), ETL pipelines, and functions. If you need to modify the code or understand the logic, read this file.

### 2. 📖 [User Manual (How to Use)](docs/USER_MANUAL.md)
Contains a step-by-step guide for end-users on how to run the application, upload system files, sync data, search for unit history, and track technician efficiency scores.

---

## 🚀 Quick Start

To run the application locally, ensure you have Python installed, then run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The application will launch on your default web browser (usually `http://localhost:8501`).