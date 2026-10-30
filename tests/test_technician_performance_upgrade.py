# tests/test_technician_performance_upgrade.py
import unittest
import pandas as pd
import numpy as np
import io
import sqlite3
import database
import etl

class TestTechnicianPerformanceUpgrade(unittest.TestCase):
    def setUp(self):
        database.init_estimator_schema()

    def tearDown(self):
        try:
            with database.get_connection() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM tech_performance_master WHERE complaint_no LIKE 'TEST%'")
                conn.commit()
        except Exception:
            pass

    def test_schema_has_branch_and_days(self):
        with database.get_connection() as conn:
            c = conn.cursor()
            c.execute("PRAGMA table_info(tech_performance_master)")
            cols = [r[1] for r in c.fetchall()]
            self.assertIn("branch_name", cols)
            self.assertIn("days", cols)

    def test_ingest_performance_clamps_negative_days_and_retains_branch(self):
        csv_data = """ZONE,BRANCH_NAME,CUSTOMER_NAME,COMPLAINT_NO,TECHNICIAN_NAME,COMPLETED_STATUS,CLOSED_DATE,DAYS
KARACHI,Karachi 2 HA,Test Cust,TEST99001,Test Tech,COMPLETED,2026-10-15,-2
KARACHI,Karachi 2 HA | ASC,Test Cust 2,TEST99002,ASC Tech,COMPLETED,2026-10-16,3.5
"""
        csv_stream = io.StringIO(csv_data)
        count = etl.ingest_performance_pipeline(csv_stream)
        self.assertEqual(count, 2)

        with database.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT branch_name, days FROM tech_performance_master WHERE complaint_no = 'TEST99001'")
            row1 = c.fetchone()
            self.assertIsNotNone(row1)
            self.assertEqual(row1[0], "Karachi 2 HA")
            self.assertEqual(float(row1[1]), 0.0)  # -2 clamped to 0.0

            c.execute("SELECT branch_name, days FROM tech_performance_master WHERE complaint_no = 'TEST99002'")
            row2 = c.fetchone()
            self.assertIsNotNone(row2)
            self.assertEqual(row2[0], "Karachi 2 HA | ASC")
            self.assertEqual(float(row2[1]), 3.5)

    def test_fetch_performance_data_returns_branch_and_days(self):
        df = database.fetch_performance_data()
        self.assertFalse(df.empty)
        self.assertIn("branch_name", df.columns)
        self.assertIn("days", df.columns)

if __name__ == "__main__":
    unittest.main()
