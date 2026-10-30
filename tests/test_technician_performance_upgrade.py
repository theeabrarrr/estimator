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

    def test_top_3_performers_ranking_and_efficiency(self):
        # Create a mock dataframe of technicians with varying completed and assigned counts
        mock_data = pd.DataFrame([
            {"complaint_no": "C1", "technician_name": "Tech Alpha", "status": "COMPLETED", "days": 1.0},
            {"complaint_no": "C2", "technician_name": "Tech Alpha", "status": "COMPLETED", "days": 2.0},
            {"complaint_no": "C3", "technician_name": "Tech Alpha", "status": "COMPLETED", "days": 0.0},
            {"complaint_no": "C4", "technician_name": "Tech Beta", "status": "COMPLETED", "days": 0.5},
            {"complaint_no": "C5", "technician_name": "Tech Beta", "status": "COMPLETED", "days": 1.5},
            {"complaint_no": "C6", "technician_name": "Tech Gamma", "status": "COMPLETED", "days": 3.0},
            {"complaint_no": "C7", "technician_name": "Tech Delta", "status": "REJECTED", "days": np.nan},
        ])
        
        all_pvt = pd.pivot_table(
            mock_data,
            index='technician_name',
            columns='status',
            values='complaint_no',
            aggfunc='count',
            fill_value=0
        )
        for s in ['COMPLETED', 'REJECTED']:
            if s not in all_pvt.columns:
                all_pvt[s] = 0
                
        summary_df = pd.DataFrame({
            'Technician': all_pvt.index,
            'Assigned': all_pvt.sum(axis=1).values,
            'Completed': all_pvt['COMPLETED'].values,
        }).sort_values(by=['Completed', 'Assigned'], ascending=[False, False]).reset_index(drop=True)
        
        top3 = summary_df[summary_df['Completed'] > 0].head(3)
        self.assertEqual(len(top3), 3)
        self.assertEqual(top3.iloc[0]['Technician'], "Tech Alpha")
        self.assertEqual(top3.iloc[0]['Completed'], 3)
        self.assertEqual(top3.iloc[1]['Technician'], "Tech Beta")
        self.assertEqual(top3.iloc[1]['Completed'], 2)
        self.assertEqual(top3.iloc[2]['Technician'], "Tech Gamma")
        self.assertEqual(top3.iloc[2]['Completed'], 1)

if __name__ == "__main__":
    unittest.main()
