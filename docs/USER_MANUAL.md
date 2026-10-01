# User Manual: DWP Field Assistant Engine

Assalam o Alaikum! Welcome to the **DWP Field Assistant Engine**. This application is an all-in-one diagnostic and field operations platform built for DWP service technicians, supervisors, and branch managers.

---

## 🚀 How to Start the App

Open your terminal or command prompt inside the project folder and run:
```bash
streamlit run app.py
```
This will automatically launch the application in your default web browser (usually at `http://localhost:8501`).

---

## 🧮 Tab 1: Spare Parts & Cost Estimator (Primary Feature)

This module allows technicians and supervisors to create instant, official service and spare parts quotations for customers.

### How to Create a Customer Estimate:
1. **Select Equipment Model**:
   Choose the customer's model from the dropdown (e.g. `GS-18PITH11W`, `GS-18FITH2W`, `WD-300`, `GR-E8890G-CB1`).
   - The app automatically detects appliance capacity and calculates the exact refrigerant gas refill charge.
2. **Review Overhead Charges & Warranty Status**:
   - Check or uncheck **Visit Charges (Rs. 600)** and **Mobility / Labour (Rs. 2,000)**.
   - Check **Gas Refill Required** if the unit requires gas charging.
   - Select Warranty Status:
     - *Cash / Out of Warranty*: Standard commercial billing.
     - *Under Warranty*: Free replacement (Customer payable: Rs. 0).
     - *Partial Warranty*: Customer pays for parts/gas; labour & visit are free.
3. **Select Spare Parts**:
   - **All Verified Parts Visible by Default**: Every compatible component is listed with its official ERP retail price.
   - **Live Stock Badges**:
     - `🟢 Karachi-2 Store: X In Stock` (available immediately)
     - `🔴 Karachi-2 Store: 0 Available` (available via procurement/indent)
     - `🤝 In Hand: Name (Qty)` (indicates if a co-technician has the part in hand)
   - **Filter Options**:
     - *Search Box*: Type any part name, SKU, or keyword (e.g. `evaporator`, `valve`, `1002`). Multi-word and dash-normalized search is supported.
     - *Sub-Assembly Category*: Filter by category (e.g. `Evaporator Assy`, `Cut Off Valve`, `Electronic PCB`, `WD Compressor`).
     - *Inventory Filter*: Toggle between "All Verified Parts" and "🟢 In-Stock Only".
   - Simply check the checkbox next to the required parts to add them to the quotation.
4. **Real-Time Quotation Summary**:
   - View the live itemized bill breakdown.
   - Fill in Customer Name, Phone, and optional Unit Serial Number.
5. **Send Official Quotation via WhatsApp**:
   - The app formats a professional DWP quotation with one click.
   - Click the copy button on the top-right of the quotation code block, or click the **"Open WhatsApp Chat"** button to open WhatsApp Web/App directly with the customer.

---

## 🔍 Tab 2: Unit & Customer History

Search the complete 1-year archive of service records:
1. Type a **Serial Number**, **Customer Phone Number**, or **Complaint Number**.
2. Press Enter to view past jobs, assigned technicians, closing remarks, and collection amounts.

---

## 📊 Tab 3: Technician Performance

Track branch-wide and technician-specific KPIs:
1. Filter by specific technician or date range.
2. View total jobs, completed complaints, cancel/nil counts, and overall completion percentage.

---

## 🔄 Updating Data via Sidebar

- **Daily Closed Complaints**: Upload newly closed complaint CSV/Excel files to incrementally append new jobs and update part usage.
- **Daily Stock & Prices**: Upload the latest Store Wise Stock Movement PDF to update Karachi-2 Store stock levels and retail prices in real time.
