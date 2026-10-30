import unittest
import time
import tempfile
import sqlite3
import os
from unittest.mock import patch, MagicMock
import database

class TestTursoResilience(unittest.TestCase):
    def setUp(self):
        database.reset_turso_fallback()

    def tearDown(self):
        database.reset_turso_fallback()


    def test_record_local_mutation(self):
        # When fallback is active, local mutation should be recorded
        database._TURSO_FALLBACK_ACTIVE = True
        database._PENDING_LOCAL_WRITES = False
        database.record_local_mutation()
        self.assertTrue(database._PENDING_LOCAL_WRITES)

        # When fallback is inactive, local mutation should not be recorded
        database._TURSO_FALLBACK_ACTIVE = False
        database._PENDING_LOCAL_WRITES = False
        database.record_local_mutation()
        self.assertFalse(database._PENDING_LOCAL_WRITES)


    def test_reconcile_local_writes(self):
        # Create a temporary database and set it as DB_FILE
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        # We need the patch to actually replace database.DB_FILE with our path
        # But we're patching the string, let's just modify the variable directly for the test
        original_db_file = database.DB_FILE
        database.DB_FILE = db_path

        try:
            # Set up the temporary sqlite DB with the required table and a row
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('''
                CREATE TABLE master_parts_lookup (
                    part_no TEXT PRIMARY KEY,
                    erp_description TEXT,
                    retail_price REAL,
                    is_pricing_pending INTEGER,
                    stock_status TEXT,
                    last_synced TEXT
                )
            ''')
            # Insert a row that should be picked up (last_synced >= 1 day ago)
            c.execute('''
                INSERT INTO master_parts_lookup
                (part_no, erp_description, retail_price, is_pricing_pending, stock_status, last_synced)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            ''', ('TEST-PART-1', 'Test Part', 99.99, 1, 'IN_STOCK'))
            conn.commit()

            # Fetch the row to know exactly what should be passed to executemany
            c.execute("SELECT part_no, erp_description, retail_price, is_pricing_pending, stock_status, last_synced FROM master_parts_lookup")
            expected_rows = c.fetchall()
            conn.close()

            # Set pending writes to True
            database._PENDING_LOCAL_WRITES = True

            # Mock the cloud connection
            mock_cloud_conn = MagicMock()
            mock_cloud_cursor = MagicMock()
            mock_cloud_conn.cursor.return_value = mock_cloud_cursor

            # Run reconciliation
            result = database.reconcile_local_writes_to_turso(mock_cloud_conn)

            # Assertions
            self.assertTrue(result)
            self.assertFalse(database._PENDING_LOCAL_WRITES)

            # Check that executemany was called with our expected rows
            self.assertTrue(mock_cloud_cursor.executemany.called)
            call_args = mock_cloud_cursor.executemany.call_args
            self.assertEqual(len(call_args[0][1]), 1)  # one row
            self.assertEqual(call_args[0][1][0][0], 'TEST-PART-1') # part_no matches

        finally:
            database.DB_FILE = original_db_file
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_database_status_reporting(self):
        status = database.get_database_status()
        self.assertIn(status, ["TURSO_ONLINE", "TURSO_FALLBACK_LOCAL", "LOCAL_ONLY"])

    @patch('database.get_turso_credentials')
    @patch('database._get_shared_turso_connection')
    def test_try_reconnect_turso_success(self, mock_get_conn, mock_creds):
        mock_creds.return_value = ("libsql://test.turso.io", "dummy_token")
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        database._TURSO_FALLBACK_ACTIVE = True
        success, msg = database.try_reconnect_turso()
        self.assertTrue(success)
        self.assertFalse(database._TURSO_FALLBACK_ACTIVE)
        self.assertEqual(database._TURSO_LAST_FAIL_TIME, 0.0)

    @patch('database.get_turso_credentials')
    @patch('database._get_shared_turso_connection')
    def test_try_reconnect_turso_failure(self, mock_get_conn, mock_creds):
        mock_creds.return_value = ("libsql://test.turso.io", "dummy_token")
        mock_get_conn.side_effect = Exception("Connection timeout")

        database._TURSO_FALLBACK_ACTIVE = False
        success, msg = database.try_reconnect_turso()
        self.assertFalse(success)
        self.assertTrue(database._TURSO_FALLBACK_ACTIVE)
        self.assertGreater(database._TURSO_LAST_FAIL_TIME, 0.0)

    @patch('database.try_reconnect_turso')
    @patch('database.get_turso_credentials')
    def test_get_connection_auto_recovery_triggers_after_cooldown(self, mock_creds, mock_reconnect):
        mock_creds.return_value = ("libsql://test.turso.io", "dummy_token")
        database._TURSO_FALLBACK_ACTIVE = True
        # Set fail time to 100 seconds ago (greater than 90s cooldown)
        database._TURSO_LAST_FAIL_TIME = time.time() - 100

        mock_reconnect.return_value = (True, "Connected")
        
        # When get_connection is called, it should invoke try_reconnect_turso()
        with database.get_connection() as conn:
            pass

        mock_reconnect.assert_called_once()

    @patch('database.try_reconnect_turso')
    @patch('database.get_turso_credentials')
    def test_get_connection_auto_recovery_does_not_trigger_before_cooldown(self, mock_creds, mock_reconnect):
        mock_creds.return_value = ("libsql://test.turso.io", "dummy_token")
        database._TURSO_FALLBACK_ACTIVE = True
        # Set fail time to 10 seconds ago (< 90s cooldown)
        database._TURSO_LAST_FAIL_TIME = time.time() - 10

        with database.get_connection() as conn:
            pass

        mock_reconnect.assert_not_called()

if __name__ == '__main__':
    unittest.main()
