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


    def test_enrich_cross_series_compatibilities(self):
        """Test enrichment of cross-series compatibilities in model_part_catalog."""
        test_models = [
            ("GS-18FITH1", "TEST_PART_18"),
            ("GS-12CITH2", "TEST_PART_12"),
            ("WD-300F", "TEST_PART_WD"),
            ("GR-E9978G", "TEST_PART_REF"),
            ("UNRELATED-MODEL", "TEST_PART_UN")
        ]

        try:
            with database.get_connection() as conn:
                cursor = conn.cursor()
                for m, p in test_models:
                    cursor.execute(
                        "INSERT OR IGNORE INTO model_part_catalog (model, part_no) VALUES (?, ?)",
                        (m, p)
                    )
                conn.commit()

            # Run enrichment
            database.enrich_cross_series_compatibilities()

            with database.get_connection() as conn:
                cursor = conn.cursor()

                # Verify 18-series
                evap_18_rows = cursor.execute(
                    "SELECT part_no FROM model_part_catalog WHERE model = 'GS-18FITH1' AND part_no = '11001060868'"
                ).fetchall()
                self.assertEqual(len(evap_18_rows), 1)

                # Verify 12-series
                evap_12_rows = cursor.execute(
                    "SELECT part_no FROM model_part_catalog WHERE model = 'GS-12CITH2' AND part_no = '1002976'"
                ).fetchall()
                self.assertEqual(len(evap_12_rows), 1)

                # Verify WD-series
                wd_rows = cursor.execute(
                    "SELECT part_no FROM model_part_catalog WHERE model = 'WD-300F' AND part_no = 'QD36LWL'"
                ).fetchall()
                self.assertEqual(len(wd_rows), 1)

                # Implicit WD models verify
                wd_implicit_rows = cursor.execute(
                    "SELECT part_no FROM model_part_catalog WHERE model = 'WD-350F' AND part_no = 'QD36LWL'"
                ).fetchall()
                self.assertEqual(len(wd_implicit_rows), 1)

                # Verify REF-series
                ref_rows = cursor.execute(
                    "SELECT part_no FROM model_part_catalog WHERE model = 'GR-E9978G' AND part_no = 'GR18-E51519002'"
                ).fetchall()
                self.assertEqual(len(ref_rows), 1)

                # Verify Unrelated not enriched incorrectly
                unrelated_rows = cursor.execute(
                    "SELECT part_no FROM model_part_catalog WHERE model = 'UNRELATED-MODEL'"
                ).fetchall()
                self.assertEqual(len(unrelated_rows), 1)
                self.assertEqual(unrelated_rows[0][0], "TEST_PART_UN")

        finally:
            with database.get_connection() as conn:
                cursor = conn.cursor()
                # Clean up ONLY the specific test parts we inserted
                for m, p in test_models:
                    cursor.execute("DELETE FROM model_part_catalog WHERE model = ? AND part_no = ?", (m, p))

                # Clean up the parts inserted by enrichment for our test models,
                # but DO NOT delete implicitly added models that are expected by test_estimator_suite!
                # Note: `WD-350F` might be needed by other tests.
                # Actually, test_08 EXPECTS QD36LWL / QD36LW to be present for WD-300F!
                # If we delete them, test_08 will fail.
                # So we should ONLY delete things for models that ONLY this test uses, or just delete NOTHING of enrichment
                # because enrichment is meant to be permanent.
                # Let's clean up our dummy test models explicitly.
                for m in ["GS-18FITH1", "GS-12CITH2", "GR-E9978G", "UNRELATED-MODEL"]:
                    cursor.execute("DELETE FROM model_part_catalog WHERE model = ?", (m,))

                # For WD-300F, we ONLY delete "TEST_PART_WD" (done above).
                # We leave the QD36LW / QD36LWL alone because test_08 needs them.
                conn.commit()


if __name__ == "__main__":
    unittest.main()
