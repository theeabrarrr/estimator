# Technical Guide for Developers & Technicians

Welcome to the **DWP Service Field Assistant Engine** technical documentation. This guide explains the codebase structure, database architecture, and data pipelines. 

*(Note: The Cost & Stock Estimator module was completely removed from the application as per business requirements. The app now strictly handles Historical Service Records and Technician Performance KPIs).*

---

## 1. Project Architecture

The application is built using **Python 3** and **Streamlit** for the frontend, with a local **SQLite** database (`dwp_service.db`) acting as the data store.

### Key Files & Their Purposes:

- **`app.py`**: 
  The main Streamlit frontend application. It contains the UI logic, tabs layout, and rendering code.
  - *Tab 1*: Unit & Customer History (Search closed complaints).
  - *Tab 2*: Technician Performance (KPI, Date filters, Completion Rates).
  - *Sidebar*: Tools to upload CSV/Excel files and sync data.

- **`database.py`**:
  The Data Access Layer. Handles all direct interaction with the SQLite database.
  - `get_connection()`: Connects to `dwp_service.db`.
  - `search_history_records(query, phone)`: Performs wildcard `LIKE` SQL queries against the `history_master` table to find past complaints based on serial numbers, complaint numbers, or phone numbers.
  - `fetch_performance_data()`: Retrieves the full dataset from `tech_performance_master` for KPI evaluation.

- **`etl.py`**:
  The Extract, Transform, Load (ETL) pipeline. Contains all the logic for cleaning raw Excel/CSV data and inserting it into the database safely.
  - `standardize_columns(df)`: Normalizes column headers (lowercase, snake_case).
  - `normalize_phone(ph)`: Cleans customer phone numbers to a standard 11-digit format starting with `0`.
  - `ingest_feedback_and_pricing()`: Takes raw Closed Complaints files and Customer Collection files, cleans the data, and writes to the `history_master` table.
  - `ingest_performance_pipeline()`: Combines Quality Feedback and Cancel/Nil reports, removes transferred jobs, assigns status priorities, and populates the `tech_performance_master` table.

- **`dwp_service.db`**:
  The local SQLite database generated dynamically when ETL pipelines run. It contains two main tables:
  - `history_master`: Stores customer details, model/serial info, dates, remarks, and final billing amounts.
  - `tech_performance_master`: Stores technician job statuses for KPI calculations.

---

## 2. Data Flow & Execution

1. **Ingestion**: When a user uploads a `.csv` or `.xlsx` file via the Streamlit sidebar, `app.py` passes the file object to the respective function in `etl.py`.
2. **Transformation**: `etl.py` uses `pandas` to read the file, normalize strings, handle missing dates, and standardize formats.
3. **Storage**: The cleaned `pandas.DataFrame` is converted into a list of tuples and inserted into the SQLite database using `cursor.executemany` with `INSERT OR REPLACE` to prevent duplication on primary keys (Complaint Number).
4. **Retrieval**: When a user searches for a serial number, `app.py` calls `database.py`, which executes a `SELECT` query and returns a `pandas.DataFrame` that is then rendered natively in the UI.

## 3. Extending the Codebase

If you need to add a new module in the future:
1. Create a new data ingestion function in `etl.py`.
2. Create data fetching functions in `database.py`.
3. Add a new `st.tab` in `app.py`.
4. Ensure you do not block the main thread; use `st.spinner` when running ETL jobs.
