import unittest
import time
from unittest.mock import patch, MagicMock
import database

class TestTursoResilience(unittest.TestCase):
    def setUp(self):
        database.reset_turso_fallback()

    def tearDown(self):
        database.reset_turso_fallback()

    def test_reset_turso_fallback(self):
        # Mutate the global state to simulate an active fallback and pending writes
        database._TURSO_FALLBACK_ACTIVE = True
        database._TURSO_LAST_FAIL_TIME = 12345.67
        database._PENDING_LOCAL_WRITES = True

        # Call the reset function
        database.reset_turso_fallback()

        # Assert that the state has been correctly reset
        self.assertFalse(database._TURSO_FALLBACK_ACTIVE)
        self.assertEqual(database._TURSO_LAST_FAIL_TIME, 0.0)
        self.assertFalse(database._PENDING_LOCAL_WRITES)

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
