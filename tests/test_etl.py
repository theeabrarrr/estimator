import unittest
import os
import sys
import io
import pandas as pd

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import etl
import database

class TestETLModule(unittest.TestCase):

    def test_clean_val(self):
        """Test clean_val handles string trimming and Excel prefix symbols ="" and ='"""
        self.assertEqual(etl.clean_val('="2826010"'), "2826010")
        self.assertEqual(etl.clean_val("='03001234567'"), "03001234567")
        self.assertEqual(etl.clean_val("  Hello World  "), "Hello World")
        self.assertEqual(etl.clean_val(None), "")
        self.assertEqual(etl.clean_val(pd.NA), "")

    def test_normalize_phone(self):
        """Test phone number normalization to clean 11-digit local format."""
        self.assertEqual(etl.normalize_phone("+923001234567"), "03001234567")
        self.assertEqual(etl.normalize_phone("923001234567"), "03001234567")
        self.assertEqual(etl.normalize_phone("0300-1234567"), "03001234567")
        self.assertEqual(etl.normalize_phone("='0300 123 4567'"), "03001234567")

    def test_standardize_columns(self):
        """Test column standardization and alias renaming."""
        raw_df = pd.DataFrame({
            'COMPLAIN_NO': ['282601'],
            'MODEL_NO': ['GS-18PITH11W'],
            'CUSTOMER_PHONE': ['03001234567'],
            'JOB_STATUS': ['COMPLETED'],
            'TECH_NAME': ['Ameer Hamza']
        })
        std_df = etl.standardize_columns(raw_df)
        self.assertIn('complaint_no', std_df.columns)
        self.assertIn('model', std_df.columns)
        self.assertIn('phone', std_df.columns)
        self.assertIn('status', std_df.columns)
        self.assertIn('technician_name', std_df.columns)

    def test_safe_read(self):
        """Test safe_read handles DataFrames, CSV streams, and missing input gracefully."""
        self.assertTrue(etl.safe_read(None).empty)

        df_input = pd.DataFrame({'a': ['1', '2']})
        self.assertEqual(len(etl.safe_read(df_input)), 2)

        csv_str = "col1,col2\nval1,val2\n"
        csv_stream = io.BytesIO(csv_str.encode('utf-8'))
        csv_stream.name = "test.csv"
        df_csv = etl.safe_read(csv_stream)
        self.assertEqual(len(df_csv), 1)
        self.assertEqual(df_csv.iloc[0]['col1'], 'val1')

    def test_sync_all_complaints_pipeline_and_cleanup(self):
        """Test unified sync pipeline ingests complaint feedback correctly."""
        fb_csv = """COMPLAINT_NO,MODEL_NAME,HARDWARE_PART_NOS,HARDWARE_PRODUCTS,HARDWARE_BOARD_TYPES,COMPLETED_STATUS,CLOSED_DATE,PHONE,CUSTOMER_NAME,TECHNICIAN_NAME
999001122,GS-18PITH11W,11001060868,Evaporator,Evaporator Assy,COMPLETED,2026-02-01,03009998877,Test User,Test Tech
"""
        fb_stream = io.BytesIO(fb_csv.encode('utf-8'))
        fb_stream.name = "feedback.csv"

        perf_cnt, m_cnt, p_cnt = etl.sync_all_complaints_pipeline(fb_stream)
        self.assertGreaterEqual(perf_cnt, 1)

        # Verify ingested record in history_master and tech_performance_master
        res_hist = database.search_history_records("999001122", "")
        self.assertFalse(res_hist.empty)
        self.assertEqual(res_hist.iloc[0]['model'], "GS-18PITH11W")

        # Cleanup test row
        with database.get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM history_master WHERE complaint_no = '999001122'")
            c.execute("DELETE FROM tech_performance_master WHERE complaint_no = '999001122'")
            conn.commit()


    def test_ingest_performance_pipeline(self):
        """Test ingest_performance_pipeline processing with feedback and cancel sources."""
        # Note: the code renames columns using standardize_columns which might require specific naming or just rely on standard mappings.
        # standardize_columns renames 'COMPLAIN_NO' or similar to 'complaint_no', 'TECH_NAME' -> 'technician_name', 'JOB_STATUS' -> 'status'

        fb_df = pd.DataFrame({
            'COMPLAIN_NO': ['111222333', '444555666'],
            'TECH_NAME': ['Tech A', 'Tech B'],
            'BRANCH_NAME': ['Branch X', 'Karachi 2 HA'],
            'DAYS': [2, -1],  # -1 should become 0.0
            'JOB_STATUS': ['COMPLETED', 'TRANSFERED'], # TRANSFERED should be dropped
            'CLOSED_DATE': ['2026-03-01', '2026-03-02']
        })

        cancel_df = pd.DataFrame({
            'COMPLAIN_NO': ['111222333', '777888999'], # 111222333 is in both, cancel has priority 1, fb has 2. 'last' is kept, so it might be FB if ordered by priority asc.
            'TECH_NAME': ['Tech A', 'Tech C'],
            'BRANCH_NAME': ['Branch X', 'Branch Y'],
            'DAYS': [3, 1],
            'JOB_STATUS': ['CANCELED', 'CANCELED'],
            'CLOSED_DATE': ['2026-03-03', '2026-03-04']
        })

        # the code: comb = comb.sort_values(by=['complaint_no', '_priority'], ascending=[True, True])
        # keep='last'.
        # cancel has _priority 1, fb has _priority 2.
        # 1 comes before 2. keep='last' means 2 (fb) will be kept!
        # So 111222333 should actually have STATUS = COMPLETED from fb_df!

        perf_cnt = etl.ingest_performance_pipeline(fb_df, cancel_df)
        self.assertGreaterEqual(perf_cnt, 2) # Expecting 2 valid records

        with database.get_connection() as conn:
            c = conn.cursor()

            # Check 111222333 (from fb due to keep='last' on ascending priority sort)
            c.execute("SELECT status, days, closed_date FROM tech_performance_master WHERE complaint_no = '111222333'")
            res1 = c.fetchone()
            self.assertIsNotNone(res1)
            self.assertEqual(res1[0], 'COMPLETED')
            self.assertEqual(res1[1], 2)
            self.assertEqual(res1[2], '2026-03-01')

            # Check 777888999 (from cancel)
            c.execute("SELECT status, branch_name FROM tech_performance_master WHERE complaint_no = '777888999'")
            res2 = c.fetchone()
            self.assertIsNotNone(res2)
            self.assertEqual(res2[0], 'CANCELED')
            self.assertEqual(res2[1], 'Branch Y')

            # Ensure TRANSFERED is absent
            c.execute("SELECT * FROM tech_performance_master WHERE complaint_no = '444555666'")
            res3 = c.fetchone()
            self.assertIsNone(res3)

            # Cleanup
            c.execute("DELETE FROM tech_performance_master WHERE complaint_no IN ('111222333', '444555666', '777888999')")
            conn.commit()

if __name__ == "__main__":
    unittest.main()
