# tests/test_history_dedup.py
import unittest
import sqlite3
import pandas as pd
import database
import etl

class TestHistoryDeduplicationAndTimeline(unittest.TestCase):
    def setUp(self):
        self.orig_get_turso_creds = database.get_turso_credentials
        database.get_turso_credentials = lambda: (None, None)
        database.init_estimator_schema()

    def tearDown(self):
        database.get_turso_credentials = self.orig_get_turso_creds

    def test_01_serial_search_has_no_duplicates(self):
        """Serial A1021618DD0023350624 should return exactly 3 distinct service visits with populated model and phone."""
        df = database.search_history_records("A1021618DD0023350624", "")
        self.assertFalse(df.empty, "Should find service records for A1021618DD0023350624")
        self.assertEqual(len(df), 3, f"Expected exactly 3 records, got {len(df)}")

        # Ensure all complaint numbers are unique
        complaints = df['complaint_no'].tolist()
        self.assertEqual(len(complaints), len(set(complaints)), "Complaint numbers must be strictly unique")
        
        # Ensure model and phone are populated
        for _, row in df.iterrows():
            self.assertEqual(row['model'], 'GS-18PITH11W')
            self.assertEqual(row['phone'], '03212836038')

    def test_02_complaint_search_returns_single_complete_record(self):
        """Complaint 2272500362 must return exactly 1 complete card with model and phone."""
        df = database.search_history_records("2272500362", "")
        self.assertEqual(len(df), 1, f"Expected 1 record for complaint 2272500362, got {len(df)}")
        rec = df.iloc[0]
        self.assertEqual(rec['complaint_no'], '2272500362')
        self.assertEqual(rec['model'], 'GS-18PITH11W')
        self.assertEqual(rec['phone'], '03212836038')
        self.assertEqual(rec['technician_name'], 'Frost Edge Cooling')

    def test_03_database_contains_zero_duplicate_complaints(self):
        """dwp_service.db history_master table must have zero duplicate complaints."""
        conn = sqlite3.connect(database.DB_FILE)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT REPLACE(REPLACE(TRIM(complaint_no), '=', ''), '"', '') as clean_cno, COUNT(*)
                FROM history_master
                GROUP BY clean_cno
                HAVING COUNT(*) > 1
            """)
            dupes = cur.fetchall()
            self.assertEqual(len(dupes), 0, f"Found {len(dupes)} duplicate complaints in history_master: {dupes[:5]}")
        finally:
            conn.close()

    def test_04_defensive_deduplication_prefers_populated_fields(self):
        """search_history_records should drop dirty duplicate rows if they ever appear."""
        test_cno = "TEST_DEDUP_9988"
        # Temporarily inject dirty + clean test records into local database
        conn = sqlite3.connect(database.DB_FILE)
        try:
            cur = conn.cursor()
            # Clean record
            cur.execute("""
                INSERT OR REPLACE INTO history_master (complaint_no, serial, phone, model, customer_name, technician_name, complaint_type, closed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (test_cno, "TEST_SERIAL_9988", "03001234567", "GS-18PITH11W", "Test Cust", "Test Tech", "Warranty", "2026-10-31"))
            # Dirty record with spaces and empty model/phone
            cur.execute("""
                INSERT OR REPLACE INTO history_master (complaint_no, serial, phone, model, customer_name, technician_name, complaint_type, closed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (f" {test_cno} ", f" TEST_SERIAL_9988 ", "", "", "Test Cust", "Test Tech", "Warranty", "2026-10-31"))
            conn.commit()

            df = database.search_history_records("TEST_SERIAL_9988", "")
            self.assertEqual(len(df), 1, f"Expected 1 record after deduplication, got {len(df)}")
            self.assertEqual(df.iloc[0]['model'], 'GS-18PITH11W')
            self.assertEqual(df.iloc[0]['phone'], '03001234567')
        finally:
            cur.execute("DELETE FROM history_master WHERE complaint_no LIKE '%TEST_DEDUP_9988%'")
            conn.commit()
            conn.close()

if __name__ == "__main__":
    unittest.main()
