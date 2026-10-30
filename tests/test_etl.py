import unittest
import os
import sys
import io
import pandas as pd
from unittest.mock import patch, MagicMock

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


class TestETLSyncModelPartCatalog(unittest.TestCase):

    @patch('etl.safe_read')
    @patch('database.upsert_model_catalog')
    @patch('database.append_model_catalog')
    @patch('etl.get_connection')
    @patch('database.sync_to_local_sqlite')
    @patch('database.is_turso_active', return_value=False)
    def test_sync_model_part_catalog_from_feedback_basic(self, mock_is_turso_active, mock_sync_to_local, mock_get_conn, mock_append, mock_upsert, mock_safe_read):
        # Setup mock DataFrame
        df = pd.DataFrame({
            'COMPLETED_STATUS': ['COMPLETED', 'PENDING'],
            'MODEL_NAME': ['MODEL_A', 'MODEL_B'],
            'HARDWARE_PART_NOS': ['PART1,PART2', 'PART3'],
            'HARDWARE_PRODUCTS': ['PROD1,PROD2', 'PROD3'],
            'HARDWARE_BOARD_TYPES': ['BOARD1,BOARD2', 'BOARD3'],
            'CLOSED_DATE': ['2023-01-01', '2023-01-02']
        })
        mock_safe_read.return_value = df

        # Setup DB connection mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        # Call function
        models, parts, events = etl.sync_model_part_catalog_from_feedback('dummy.csv', is_incremental=False)

        # Only 'COMPLETED' row is processed
        self.assertEqual(models, 1) # MODEL_A
        self.assertEqual(parts, 2) # PART1, PART2
        self.assertEqual(events, 2) # 2 parts from the completed row

        # Verify DB updates
        mock_upsert.assert_called_once()
        catalog_records = mock_upsert.call_args[0][0]
        self.assertEqual(len(catalog_records), 2)
        # Check record content ('MODEL_A', 'PART1', 'PROD1', 'BOARD1', 1, '2023-01-01')
        self.assertIn(('MODEL_A', 'PART1', 'PROD1', 'BOARD1', 1, '2023-01-01'), catalog_records)
        self.assertIn(('MODEL_A', 'PART2', 'PROD2', 'BOARD2', 1, '2023-01-01'), catalog_records)

        mock_append.assert_not_called()

        # Verify master parts lookup insertion
        mock_cursor.executemany.assert_called_once()

    @patch('etl.safe_read')
    @patch('database.upsert_model_catalog')
    @patch('etl.get_connection')
    @patch('database.sync_to_local_sqlite')
    @patch('database.is_turso_active', return_value=False)
    def test_sync_model_part_catalog_from_feedback_scientific_notation(self, mock_is_turso_active, mock_sync_to_local, mock_get_conn, mock_upsert, mock_safe_read):
        # Setup DB connection mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value.__enter__.return_value = mock_conn

        df = pd.DataFrame({
            'COMPLETED_STATUS': ['COMPLETED'],
            'MODEL_NAME': ['MODEL_C'],
            'HARDWARE_PART_NOS': ['3.00002E+11'],
            'HARDWARE_PRODUCTS': ['Description 30000200000-A']
        })
        mock_safe_read.return_value = df

        models, parts, events = etl.sync_model_part_catalog_from_feedback('dummy.csv', is_incremental=False)

        self.assertEqual(models, 1)
        self.assertEqual(parts, 1)

        mock_upsert.assert_called_once()
        catalog_records = mock_upsert.call_args[0][0]
        self.assertEqual(len(catalog_records), 1)
        # Should resolve '3.00002E+11' to '30000200000-A' based on description
        self.assertEqual(catalog_records[0][1], '30000200000-A')

    @patch('etl.safe_read')
    def test_sync_model_part_catalog_from_feedback_empty(self, mock_safe_read):
        df = pd.DataFrame()
        mock_safe_read.return_value = df

        models, parts, events = etl.sync_model_part_catalog_from_feedback('dummy.csv')
        self.assertEqual(models, 0)
        self.assertEqual(parts, 0)
        self.assertEqual(events, 0)

if __name__ == "__main__":
    unittest.main()
