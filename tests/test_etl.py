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


    def test_sync_model_part_catalog_from_feedback(self):
        """Test syncing part catalog from feedback CSV, covering scientific notation recovery and multi-part splitting."""
        fb_csv = """COMPLAINT_NO,MODEL_NAME,HARDWARE_PART_NOS,HARDWARE_PRODUCTS,HARDWARE_BOARD_TYPES,COMPLETED_STATUS,CLOSED_DATE,PHONE,CUSTOMER_NAME,TECHNICIAN_NAME
1,MODEL-A,1234567,Compressor,Main Board,COMPLETED,2026-02-01,111,User A,Tech A
2,MODEL-B,"1111111, 2222222","Valve, Sensor","Board A, Board B",COMPLETED,2026-02-02,222,User B,Tech B
3,MODEL-C,3.00002E+11,03000021234,Control Board,COMPLETED,2026-02-03,333,User C,Tech C
4,MODEL-D,nan,Null Product,Null Board,COMPLETED,2026-02-04,444,User D,Tech D
5,MODEL-E,,Empty Product,Empty Board,COMPLETED,2026-02-05,555,User E,Tech E
"""
        fb_stream = io.BytesIO(fb_csv.encode('utf-8'))
        fb_stream.name = "feedback2.csv"

        models_count, parts_count, events_count = etl.sync_model_part_catalog_from_feedback(fb_stream, is_incremental=False)

        # models: MODEL-A, MODEL-B, MODEL-C (MODEL-D and MODEL-E skipped because of missing part nos)
        self.assertEqual(models_count, 3)
        # parts: 1234567, 1111111, 2222222, 03000021234
        self.assertEqual(parts_count, 4)
        self.assertEqual(events_count, 4)

        with database.get_connection() as conn:
            c = conn.cursor()

            # Check model_part_catalog
            c.execute("SELECT part_no FROM model_part_catalog WHERE model = 'MODEL-C'")
            res_c = c.fetchone()
            self.assertIsNotNone(res_c)
            self.assertEqual(res_c[0], "03000021234") # Recovered from scientific notation

            c.execute("SELECT part_no FROM model_part_catalog WHERE model = 'MODEL-B' ORDER BY part_no")
            res_b = c.fetchall()
            self.assertEqual(len(res_b), 2)
            self.assertEqual(res_b[0][0], "1111111")
            self.assertEqual(res_b[1][0], "2222222")

            # Check master_parts_lookup pending entries
            c.execute("SELECT part_no, is_pricing_pending FROM master_parts_lookup WHERE part_no IN ('1234567', '1111111', '2222222', '03000021234')")
            lookup_res = c.fetchall()
            self.assertEqual(len(lookup_res), 4)
            for row in lookup_res:
                self.assertEqual(row[1], 1) # pending pricing

            # Cleanup test rows
            models_to_clean = "('MODEL-A', 'MODEL-B', 'MODEL-C')"
            parts_to_clean = "('1234567', '1111111', '2222222', '03000021234')"
            c.execute(f"DELETE FROM model_part_catalog WHERE model IN {models_to_clean}")
            c.execute(f"DELETE FROM master_parts_lookup WHERE part_no IN {parts_to_clean}")
            conn.commit()

if __name__ == "__main__":
    unittest.main()
