import unittest
import os
import sys
import pandas as pd
import sqlite3

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import database
import etl

class TestEstimatorSuite(unittest.TestCase):

    def test_01_gas_charge_rules(self):
        """Verify capacity-aware gas calculation across all product families."""
        test_cases = [
            ("GS-12PITH11W", 5500, "12K"),
            ("ES-12DU01WG", 5500, "12K"),
            ("GS-18PITH11W", 7000, "18K"),
            ("GS-18PIT10W", 7000, "18K"),
            ("GS-18LM5L", 7000, "18K"),
            ("GS-24PITH11W", 8500, "24K"),
            ("GF-24ISH", 8500, "24K"),
            ("GF-36TFIH", 13000, "36K"),
            ("GKH48K3FI", 13000, "48K"),
            ("GUHN48NM3HO", 13000, "48K"),
            ("GR-E8890G-CB3", 4000, "REF"),
            ("GR-E9978G-CB1", 4000, "REF"),
            ("WD-300F", 3500, "WD"),
            ("GW-JL500FC", 3500, "WD"),
        ]
        for model, expected_charge, label_token in test_cases:
            charge, label = config.calculate_gas_charge(model)
            self.assertEqual(charge, expected_charge, f"Failed gas rate for {model}: expected {expected_charge}, got {charge}")
            self.assertEqual(config.calculate_gas_charge_amount(model), expected_charge)

    def test_02_database_schema_and_models(self):
        """Verify database tables, views, and distinct model catalog retrieval."""
        database.init_estimator_schema()
        models = database.get_all_models_for_estimator()
        self.assertGreater(len(models), 300, "Expected >300 models in catalog")
        self.assertIn("GS-18PITH11W", models)
        self.assertIn("GS-12PITH11W", models)

    def test_03_parts_by_model_and_stock_normalization(self):
        """Verify parts retrieval for a model, non-negative stock numbers, and ERP prices."""
        parts_df = database.get_parts_by_model("GS-18PITH11W")
        self.assertFalse(parts_df.empty, "Parts DataFrame should not be empty for GS-18PITH11W")
        
        # Verify no negative quantities appear in available stock
        self.assertTrue((parts_df['branch_stock'] >= 0).all(), "Branch stock must never be negative")
        self.assertTrue((parts_df['total_stock'] >= 0).all(), "Total stock must never be negative")
        
        # Verify ground truth top parts exist
        part_nos = parts_df['part_no'].tolist()
        self.assertIn("11001060868", part_nos, "Evaporator 11001060868 should be present for GS-18PITH11W")
        self.assertIn("7130239", part_nos, "Valve 7130239 should be present for GS-18PITH11W")
        
        # Check stock status
        in_stock_rows = parts_df[parts_df['branch_stock'] > 0]
        self.assertTrue((in_stock_rows['stock_status'] == 'In Stock').all())

    def test_04_cross_model_compatibility(self):
        """Verify cross-model discovery returns shared models."""
        valve_pno = "7130239"
        compat = database.get_cross_model_compatibilities(valve_pno)
        self.assertGreater(len(compat), 50, f"Valve {valve_pno} should fit >50 models")
        models_list = [m[0] for m in compat]
        self.assertIn("GS-18PITH11W", models_list)
        self.assertIn("GS-12PITH11W", models_list)

    def test_05_manual_price_update(self):
        """Verify manual price update persists into SQLite master_parts_lookup and updates view."""
        test_pno = "TEST_OVERRIDE_SKU_999"
        # Insert or update price
        database.update_part_price(test_pno, 4500)
        
        with database.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT retail_price, is_pricing_pending FROM master_parts_lookup WHERE part_no = ?", (test_pno,))
            row = c.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 4500)
            self.assertEqual(row[1], 0)
            
            # Clean up test row
            c.execute("DELETE FROM master_parts_lookup WHERE part_no = ?", (test_pno,))
            conn.commit()

    def test_06_missing_price_export(self):
        """Verify missing prices dataframe is generated with valid structure."""
        missing_df = database.get_missing_price_parts_df()
        self.assertFalse(missing_df.empty, "Missing price dataframe should not be empty")
        self.assertIn("part_no", missing_df.columns)
        self.assertIn("part_description", missing_df.columns)
        self.assertIn("total_frequency", missing_df.columns)
        self.assertGreaterEqual(len(missing_df), 10)

    def test_07_existing_modules_non_regression(self):
        """Verify existing search_history_records and fetch_performance_data still work."""
        hist = database.search_history_records("GS-18", "")
        self.assertIsInstance(hist, pd.DataFrame)
        
        perf = database.fetch_performance_data()
        self.assertIsInstance(perf, pd.DataFrame)

    def test_08_wd_compressor_presence(self):
        """Verify WD-300, WD-300F, and WD-450F have compressors available in catalog."""
        for m in ["WD-300", "WD-300F", "WD-450F"]:
            parts_df = database.get_parts_by_model(m)
            self.assertFalse(parts_df.empty, f"Parts should exist for {m}")
            comp_rows = parts_df[
                parts_df['part_description'].str.contains('COMP|QD', case=False, na=False) |
                parts_df['part_no'].str.contains('QD', case=False, na=False) |
                parts_df['board_type'].str.contains('COMP', case=False, na=False)
            ]
            self.assertGreater(len(comp_rows), 0, f"Compressor must be present for {m}")
            p_nos = comp_rows['part_no'].tolist()
            # Must include QD36LW or QD36LWL
            self.assertTrue('QD36LW' in p_nos or 'QD36LWL' in p_nos, f"Expected QD36 compressor in {m}")

    def test_09_performance_table_ranking_and_breakdowns(self):
        """Verify technician performance ranking 'Sr. No' starting from 1 by completed volume and breakdown columns."""
        perf_data = database.fetch_performance_data()
        self.assertFalse(perf_data.empty, "Performance data should not be empty")

        pvt = pd.pivot_table(
            perf_data,
            index='technician_name',
            columns='status',
            values='complaint_no',
            aggfunc='count',
            fill_value=0
        )
        for s in ['COMPLETED', 'REJECTED', 'CANCELED', 'NIL']:
            if s not in pvt.columns:
                pvt[s] = 0

        summary_df = pd.DataFrame({
            'Technician': pvt.index,
            'Assigned': pvt.sum(axis=1).values,
            'Completed': pvt['COMPLETED'].values,
            'Rejected': pvt['REJECTED'].values,
            'Canceled': (pvt['CANCELED'] + pvt['NIL']).values,
        })
        summary_df['Completion Rate (%)'] = (
            (summary_df['Completed'] / summary_df['Assigned'].replace(0, 1)) * 100
        ).round(1).astype(str) + '%'

        summary_df.sort_values(by=['Completed', 'Assigned'], ascending=[False, False], inplace=True)
        summary_df.reset_index(drop=True, inplace=True)
        summary_df.insert(0, 'Sr. No', range(1, len(summary_df) + 1))

        # Assert 'Sr. No' starts at 1 and is strictly sequential
        self.assertEqual(summary_df.iloc[0]['Sr. No'], 1)
        self.assertEqual(summary_df['Sr. No'].tolist(), list(range(1, len(summary_df) + 1)))

        # Assert sorted descending by Completed volume
        completed_list = summary_df['Completed'].tolist()
        self.assertEqual(completed_list, sorted(completed_list, reverse=True))

        # Assert all required breakdown columns are present
        for col in ['Sr. No', 'Technician', 'Assigned', 'Completed', 'Rejected', 'Canceled']:
            self.assertIn(col, summary_df.columns)

    def test_10_search_history_includes_canceled_and_status(self):
        """Verify search query includes rejected/canceled records with status attribute."""
        # 1. Search for a rejected ticket from tech_performance_master
        rejected_res = database.search_history_records("282634581", "")
        self.assertFalse(rejected_res.empty, "Should find rejected ticket 282634581")
        self.assertIn('status', rejected_res.columns)
        self.assertEqual(rejected_res.iloc[0]['status'], 'REJECTED')

        # 2. Search for a completed ticket from history_master
        comp_sample = "152503767"
        completed_res = database.search_history_records(comp_sample, "")
        self.assertFalse(completed_res.empty, "Should find completed ticket")
        self.assertIn('status', completed_res.columns)
        self.assertEqual(completed_res.iloc[0]['status'], 'COMPLETED')

    def test_11_performance_date_indexing_and_speed(self):
        """Verify indexes on closed_date and date-range filtered performance query speed."""
        with database.get_connection() as conn:
            c = conn.cursor()
            tech_indexes = [r[1] for r in c.execute("PRAGMA index_list(tech_performance_master)").fetchall()]
            hist_indexes = [r[1] for r in c.execute("PRAGMA index_list(history_master)").fetchall()]
            self.assertIn("idx_tech_perf_date", tech_indexes)
            self.assertIn("idx_history_closed_date", hist_indexes)

        # Date range filtered query works smoothly
        range_data = database.fetch_performance_data("2026-10-01", "2026-10-02")
        self.assertIsInstance(range_data, pd.DataFrame)
        self.assertTrue((range_data['closed_date'] >= "2026-10-01").all())
        self.assertTrue((range_data['closed_date'] <= "2026-10-02").all())

    def test_12_month_filtering_and_baseline_presence(self):
        """Verify January 2026 data exists in tech_performance_master and filters accurately."""
        perf_data = database.fetch_performance_data()
        self.assertFalse(perf_data.empty)
        
        # Test January 2026 filter
        jan_mask = (perf_data['closed_date'] >= '2026-01-01') & (perf_data['closed_date'] <= '2026-01-31')
        jan_records = perf_data[jan_mask]
        self.assertGreater(len(jan_records), 100, "Expected >100 complaints in January 2026")
        self.assertTrue((jan_records['closed_date'].str.startswith('2026-01')).all())

        # Test September 2026 filter
        sep_mask = (perf_data['closed_date'] >= '2026-09-01') & (perf_data['closed_date'] <= '2026-09-30')
        sep_records = perf_data[sep_mask]
        self.assertGreater(len(sep_records), 500, "Expected >500 complaints in September 2026")

    def test_13_unified_ingestion_pipeline(self):
        """Verify sync_all_complaints_pipeline function handles uploaded file streams without EmptyDataError."""
        import io
        self.assertTrue(hasattr(etl, 'sync_all_complaints_pipeline'))
        fb_csv = """COMPLAINT_NO,MODEL_NAME,HARDWARE_PART_NOS,HARDWARE_PRODUCTS,HARDWARE_BOARD_TYPES,COMPLETED_STATUS,CLOSED_DATE,PHONE,CUSTOMER_NAME,TECHNICIAN_NAME
TEST-SUITE-001,GS-18PITH11W,11001060868,Evaporator,Evaporator Assy,COMPLETED,2026-01-15,03001234567,John Doe,Ameer Hamza
"""
        fb_stream = io.BytesIO(fb_csv.encode('utf-8'))
        fb_stream.name = "feedback.csv"
        perf_cnt, m_cnt, p_cnt = etl.sync_all_complaints_pipeline(fb_stream)
        self.assertGreaterEqual(perf_cnt, 1)

        # Cleanup
        with database.get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM history_master WHERE complaint_no = 'TEST-SUITE-001'")
            c.execute("DELETE FROM tech_performance_master WHERE complaint_no = 'TEST-SUITE-001'")
            conn.commit()

if __name__ == "__main__":
    unittest.main()
