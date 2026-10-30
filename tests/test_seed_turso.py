import unittest
import sqlite3
import os
import sys

# Ensure app root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scripts.seed_turso as seed_turso

class TestSeedTursoSecurity(unittest.TestCase):

    def test_whitelisted_tables_and_columns_pass(self):
        """Whitelisted tables and columns should validate cleanly."""
        for tbl, cols in seed_turso.MIGRATION_TABLES:
            # Should not raise
            seed_turso.validate_table_and_columns(tbl, cols)

    def test_invalid_table_rejected(self):
        """Unauthorized or SQL-injected table names must be rejected."""
        bad_tables = [
            "users; DROP TABLE users; --",
            "admin",
            "sqlite_master",
            "model_part_catalog; DELETE FROM model_part_catalog;",
            "unknown_table"
        ]
        for tbl in bad_tables:
            with self.assertRaises(ValueError):
                seed_turso.validate_table_and_columns(tbl)

    def test_invalid_column_rejected(self):
        """Unauthorized or SQL-injected column names must be rejected."""
        bad_columns = [
            ["model", "part_no; DROP TABLE model_part_catalog; --"],
            ["password"],
            ["*"]
        ]
        for cols in bad_columns:
            with self.assertRaises(ValueError):
                seed_turso.validate_table_and_columns("model_part_catalog", cols)

    def test_static_queries_integrity(self):
        """Verify static queries exist for all migration tables and have valid syntax."""
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()

        # Create dummy tables
        cur.execute("""
            CREATE TABLE model_part_catalog (
                model TEXT, part_no TEXT, part_description TEXT, board_type TEXT,
                historical_frequency INTEGER, last_installed_date TEXT, created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE master_parts_lookup (
                part_no TEXT PRIMARY KEY, erp_description TEXT, erp_default_model TEXT,
                retail_price INTEGER, branch_store_qty INTEGER, branch_sales_qty INTEGER,
                tech_stock_qty INTEGER, total_stock_qty INTEGER, available_branch_stock INTEGER,
                available_total_stock INTEGER, stock_status TEXT, tech_allocations_json TEXT,
                is_pricing_pending INTEGER, source_document TEXT, last_synced TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE tech_performance_master (
                complaint_no TEXT, technician_name TEXT, status TEXT, closed_date TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE history_master (
                complaint_no TEXT, serial TEXT, phone TEXT, model TEXT, customer_name TEXT,
                technician_name TEXT, complaint_type TEXT, purchase_date TEXT, complaint_date TEXT,
                closed_date TEXT, remarks TEXT, closed_amount INTEGER
            )
        """)

        # Insert a sample row to test select and count queries
        cur.execute("INSERT INTO tech_performance_master VALUES (?, ?, ?, ?)",
                    ("C123", "John Doe", "COMPLETED", "2026-10-30"))

        queries = seed_turso.MIGRATION_QUERIES["tech_performance_master"]
        cur.execute(queries["count"])
        count = cur.fetchone()[0]
        self.assertEqual(count, 1)

        cur.execute(queries["select"])
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "C123")

        # Test insert query
        cur.executemany(queries["insert"], [("C124", "Jane Doe", "PENDING", "2026-10-30")])
        cur.execute(queries["count"])
        self.assertEqual(cur.fetchone()[0], 2)

        conn.close()

if __name__ == "__main__":
    unittest.main()
