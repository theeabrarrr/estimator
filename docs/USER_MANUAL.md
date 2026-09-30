# User Manual: DWP Field Assistant Engine

Assalam o Alaikum! Welcome to the **DWP Field Assistant Engine**. This application is designed to help you quickly search for historical customer complaints and track technician performance (KPIs) in real-time.

Here is a step-by-step guide on how to use the application.

---

## 🚀 How to Start the App

If the app is not already running, open your terminal (or command prompt) and run:
```bash
streamlit run app.py
```
This will automatically open the application in your web browser.

---

## 🔄 Module 1: Updating System Data (Sidebar)

Before you can search for history or check performance, you must feed the system the latest data reports from the ERP.
Open the **Sidebar** on the left side of the screen by clicking the `>` arrow.

### A. Updating Technician Performance
To get the latest KPI scores:
1. Under **Module 3: Performance Sync**, you will see two upload boxes.
2. **Quality Feedback Report**: Upload the latest CSV/Excel file of quality feedback.
3. **Cancel / Nil / Transfer Report**: Upload the latest Excel file of canceled/nil jobs.
4. Click the **"📊 Update Technician Performance"** button. The system will process everything in a few seconds and update the database.

### B. Appending New Customer History (Optional)
To add new customer records to the history:
1. Under **Module 1 & 2: Archive Append**, upload the Feedback file and the Collection Pricing file.
2. Click **"➕ Append to Master History"**. The system will safely add new complaints without deleting old ones.

---

## 🔍 Module 2: Unit & Customer History (Tab 1)

This module allows you to view the service history of any AC unit or customer.

**How to Use:**
1. Click on the **"🔍 Unit & Customer History"** tab at the top.
2. In the Search Box, type one of the following:
   - **Serial Number** (e.g., `4234091238`)
   - **Customer Phone Number** (e.g., `0322...`)
   - **Complaint Number** (e.g., `2826...`)
3. Press **Enter**.
4. The system will instantly show you all matching historical records, displaying:
   - Model and Serial Number
   - Technician Name and Customer Name
   - Complaint and Closed Dates
   - Final Collection Amount (e.g. "Rs. 2,500" or "Free Under Warranty")
   - Closing Remarks left by the technician.

---

## 📊 Module 3: Technician Performance (Tab 2)

This module allows you to track branch-wide or individual technician KPIs and Completion Rates.

**How to Use:**
1. Click on the **"📊 Technician Performance"** tab at the top.
2. **Select Date Range**: Use the "From Date" and "To Date" calendars to choose the period you want to evaluate.
3. The system will automatically calculate the **Zone Efficiency** based on Assigned vs. Completed complaints. *(Note: Transferred calls are excluded).*
4. **View Individual Technician Score**: 
   - Scroll down to the dropdown menu labeled "👤 Select Technician (Personal Score)".
   - Select a specific technician's name from the list.
   - The table will update to show only that technician's stats (Completed, Canceled, Rejected, Nil, Total Assigned, and Completion Rate %).

---

## 📞 Support
Agar application mein koi ghalti, masla, ya error aa raha ho, toh screen ka Screenshot le kar rabta karein:
- **WhatsApp / Call:** `03228344755`
- **Email:** `muhammad.abrar@ecostar.com.pk`
