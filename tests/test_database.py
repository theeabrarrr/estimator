import unittest
import os
import sys
import pandas as pd

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database

class TestDatabaseModule(unittest.TestCase):

    def setUp(self):
        # Isolate database tests from configured application credentials to protect live database
        self.orig_get_turso_creds = database.get_turso_credentials
        database.get_turso_credentials = lambda: (None, None)
        database.init_estimator_schema()

    def tearDown(self):
        database.get_turso_credentials = self.orig_get_turso_creds

    def test_database_status(self):
        """Test database connection status function."""
        status = database.get_database_status()
        self.assertIn(status, ["LOCAL_ONLY", "TURSO_ONLINE", "TURSO_FALLBACK_LOCAL"])

    def test_schema_ready(self):
        """Test is_schema_ready returns True when schema is initialized."""
        with database.get_connection() as conn:
            self.assertTrue(database.is_schema_ready(conn))

    def test_get_all_models_for_estimator(self):
        """Test retrieving all models returns list of models."""
        models = database.get_all_models_for_estimator()
        self.assertGreater(len(models), 100)
        self.assertIsInstance(models[0], str)

    def test_get_parts_by_model(self):
        """Test parts retrieval for a valid model."""
        model = "GS-18PITH11W"
        parts = database.get_parts_by_model(model)
        self.assertFalse(parts.empty)
        self.assertIn("part_no", parts.columns)
        self.assertIn("retail_price", parts.columns)

        # Non-existent model returns empty DataFrame
        empty_parts = database.get_parts_by_model("NON_EXISTENT_MODEL_999")
        self.assertTrue(empty_parts.empty)

    def test_update_part_price_and_missing_export(self):
        """Test manual part price override and missing price DataFrame generator."""
        p_no = "DB_TEST_SKU_123"
        try:
            success = database.update_part_price(p_no, 12500)
            self.assertTrue(success)

            # Verify updated price in database
            with database.get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT retail_price, is_pricing_pending FROM master_parts_lookup WHERE part_no = ?", (p_no,))
                row = c.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], 12500)
                self.assertEqual(row[1], 0)
        finally:
            with database.get_connection() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM master_parts_lookup WHERE part_no = ?", (p_no,))
                conn.commit()

        # Missing price dataframe structure
        missing_df = database.get_missing_price_parts_df()
        self.assertIsInstance(missing_df, pd.DataFrame)

    def test_search_history_records(self):
        """Test searching closed history records by query or phone."""
        df = database.search_history_records("GS-18", "")
        self.assertIsInstance(df, pd.DataFrame)

    def test_fetch_performance_data(self):
        """Test fetching performance data with optional date range."""
        df_all = database.fetch_performance_data()
        self.assertIsInstance(df_all, pd.DataFrame)

        df_ranged = database.fetch_performance_data("2026-01-01", "2026-01-31")
        self.assertIsInstance(df_ranged, pd.DataFrame)


    def test_merge_parts_master_into_catalog(self):
        """Test enriching catalog with parts from baseline parts_master."""
        with database.get_connection() as conn:
            cursor = conn.cursor()

            # Setup: Create parts_master table and insert diverse sample data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS parts_master (
                    model TEXT,
                    part_no TEXT,
                    part_name TEXT,
                    price TEXT
                )
            ''')

            cursor.execute("DELETE FROM parts_master")

            sample_data = [
                # Normal valid part (WD Compressor) - pass as string to bypass the bug if any
                ("WD-MODEL1", "COMP-001", "WD Compressor 1HP", "15000"),
                # B-grade set (should be skipped)
                ("WD-MODEL2", "B-GRADE-1", "B-Grade Set Comp", "10000"),
                # Cut Off Valve
                ("AC-MODEL1", "VALVE-01", "Expansion Valve", "2500"),
                # Electronic PCB
                ("AC-MODEL2", "PCB-MAIN-01", "Main Board Module", "5000"),
                # Missing price
                ("FR-MODEL1", "MOTOR-01", "Fan Motor", None),
                # Missing model (should be skipped)
                (None, "PART-NO-MODEL", "Desc", "100"),
                # Missing part no (should be skipped)
                ("MODEL-NO-PART", None, "Desc", "100"),
                # Invalid price
                ("AC-MODEL3", "COND-01", "Condenser Unit", "InvalidPrice")
            ]

            cursor.executemany("INSERT INTO parts_master VALUES (?, ?, ?, ?)", sample_data)

            # Pre-insert existing record to test duplication logic
            cursor.execute('''
                INSERT INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                VALUES ('AC-MODEL2', 'PCB-MAIN-01', 'Old Desc', 'Electronic PCB', 1, '')
            ''')
            conn.commit()

        try:
            # Action
            processed = database.merge_parts_master_into_catalog()

            # Assertions
            with database.get_connection() as conn:
                cursor = conn.cursor()

                # Check catalog insertions
                catalog = cursor.execute("SELECT model, part_no, board_type FROM model_part_catalog WHERE part_no IN ('COMP-001', 'B-GRADE-1', 'VALVE-01', 'PCB-MAIN-01', 'MOTOR-01', 'PART-NO-MODEL', 'COND-01')").fetchall()
                catalog_set = set((r[0], r[1], r[2]) for r in catalog)

                # Assert insertions and board type classification
                self.assertIn(("WD-MODEL1", "COMP-001", "WD Compressor"), catalog_set)
                self.assertIn(("AC-MODEL1", "VALVE-01", "Cut Off Valve"), catalog_set)
                self.assertIn(("AC-MODEL2", "PCB-MAIN-01", "Electronic PCB"), catalog_set) # Existing
                self.assertIn(("FR-MODEL1", "MOTOR-01", "Fan Motor"), catalog_set)
                self.assertIn(("AC-MODEL3", "COND-01", "Condenser"), catalog_set)

                # Assert skipped parts
                models_in_catalog = [r[0] for r in catalog]
                self.assertNotIn("WD-MODEL2", models_in_catalog) # B-grade skipped
                self.assertNotIn("MODEL-NO-PART", models_in_catalog) # missing part no

                # Check lookup upserts (prices)
                lookup = cursor.execute("SELECT part_no, retail_price FROM master_parts_lookup WHERE part_no IN ('COMP-001', 'B-GRADE-1', 'VALVE-01', 'PCB-MAIN-01', 'MOTOR-01', 'PART-NO-MODEL', 'COND-01')").fetchall()
                lookup_dict = {r[0]: r[1] for r in lookup}

                self.assertEqual(lookup_dict.get("COMP-001"), 15000)
                self.assertEqual(lookup_dict.get("VALVE-01"), 2500)

        finally:
            # Teardown
            with database.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS parts_master")
                cursor.execute("DELETE FROM model_part_catalog WHERE part_no IN ('COMP-001', 'B-GRADE-1', 'VALVE-01', 'PCB-MAIN-01', 'MOTOR-01', 'PART-NO-MODEL', 'COND-01')")
                cursor.execute("DELETE FROM master_parts_lookup WHERE part_no IN ('COMP-001', 'B-GRADE-1', 'VALVE-01', 'PCB-MAIN-01', 'MOTOR-01', 'PART-NO-MODEL', 'COND-01')")
                conn.commit()

if __name__ == "__main__":
    unittest.main()
