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

if __name__ == "__main__":
    unittest.main()
