import unittest
import os
import sys
import pandas as pd
import sqlite3
import tempfile


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


    def test_sync_to_local_sqlite(self):
        """Test syncing data to local SQLite mirror with both single and multiple statements."""
        original_db_file = database.DB_FILE
        temp_db = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                temp_db = tmp.name

            database.DB_FILE = temp_db

            with sqlite3.connect(temp_db) as conn:
                conn.execute("CREATE TABLE test_sync (id INTEGER PRIMARY KEY, name TEXT)")

            database.sync_to_local_sqlite("INSERT INTO test_sync (name) VALUES ('test1')")

            with sqlite3.connect(temp_db) as conn:
                row = conn.execute("SELECT name FROM test_sync WHERE id = 1").fetchone()
                self.assertEqual(row[0], 'test1')

            database.sync_to_local_sqlite("INSERT INTO test_sync (name) VALUES (?)", [('test2',), ('test3',)])

            with sqlite3.connect(temp_db) as conn:
                rows = conn.execute("SELECT name FROM test_sync ORDER BY id").fetchall()
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[1][0], 'test2')
                self.assertEqual(rows[2][0], 'test3')

            database.sync_to_local_sqlite("INVALID SQL QUERY")
        finally:
            database.DB_FILE = original_db_file
            if os.path.exists(temp_db):
                os.remove(temp_db)

if __name__ == "__main__":
    unittest.main()
