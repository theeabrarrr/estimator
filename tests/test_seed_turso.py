import unittest
import sys
import os

# Add scripts directory or project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.seed_turso import validate_table_and_columns

class TestSeedTursoSecurity(unittest.TestCase):
    def setUp(self):
        self.whitelist = {
            "model_part_catalog": ["model", "part_no", "part_description"],
            "tech_performance_master": ["complaint_no", "technician_name"]
        }

    def test_valid_table_and_columns(self):
        # Should not raise exception
        validate_table_and_columns("model_part_catalog", ["model", "part_no"], self.whitelist)
        validate_table_and_columns("tech_performance_master", ["complaint_no"], self.whitelist)

    def test_invalid_table_name_rejected(self):
        # Table not in whitelist
        with self.assertRaises(ValueError) as ctx:
            validate_table_and_columns("unknown_table", ["col1"], self.whitelist)
        self.assertIn("Unauthorized or invalid table name", str(ctx.exception))

    def test_sql_injection_in_table_name_rejected(self):
        # Injection in table name
        injections = [
            "model_part_catalog; DROP TABLE users; --",
            "model_part_catalog WHERE 1=1",
            "history_master' OR '1'='1"
        ]
        for payload in injections:
            with self.assertRaises(ValueError) as ctx:
                validate_table_and_columns(payload, ["model"], self.whitelist)
            self.assertIn("Unauthorized or invalid table name", str(ctx.exception))

    def test_invalid_column_name_rejected(self):
        # Column not in allowed list for the valid table
        with self.assertRaises(ValueError) as ctx:
            validate_table_and_columns("model_part_catalog", ["model", "unauthorized_col"], self.whitelist)
        self.assertIn("Unauthorized or invalid column name", str(ctx.exception))

    def test_sql_injection_in_column_name_rejected(self):
        # Injection in column name
        injections = [
            "model, (SELECT password FROM users)",
            "model; DROP TABLE model_part_catalog; --",
            "model --"
        ]
        for payload in injections:
            with self.assertRaises(ValueError) as ctx:
                validate_table_and_columns("model_part_catalog", [payload], self.whitelist)
            self.assertIn("Unauthorized or invalid column name", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
