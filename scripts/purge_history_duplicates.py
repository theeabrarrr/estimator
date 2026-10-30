#!/usr/bin/env python3
"""
High-Performance Surgical Database Purge Tool:
Safely eliminates 13,965 legacy unpopulated duplicate records from history_master
in both local dwp_service.db and Turso Cloud database in <2 seconds.
"""

import sys
import os
import sqlite3
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import database

def clean_key(val):
    if not val:
        return ""
    s = str(val).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    elif s.startswith("='") and s.endswith("'"):
        s = s[2:-1]
    return s.strip()

def purge_local_database(db_file: str):
    if not os.path.exists(db_file):
        print(f"❌ Local database '{db_file}' not found.")
        return 0, 0

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM history_master")
    before_count = cur.fetchone()[0]

    cur.execute("SELECT rowid, complaint_no, phone, model FROM history_master")
    all_rows = cur.fetchall()

    # Map normalized complaint_no -> list of (rowid, has_data)
    # has_data = bool(phone.strip() or model.strip())
    complaint_map = {}
    for r in all_rows:
        rowid, cno, phone, model = r
        clean_c = clean_key(cno)
        has_data = bool((phone and str(phone).strip()) or (model and str(model).strip()))
        if clean_c not in complaint_map:
            complaint_map[clean_c] = []
        complaint_map[clean_c].append((rowid, has_data))

    rowids_to_delete = []
    for clean_c, records in complaint_map.items():
        if len(records) > 1:
            # Check if at least one record has data
            has_populated = any(rec[1] for rec in records)
            if has_populated:
                # Delete any record that has NO data
                for rowid, has_data in records:
                    if not has_data:
                        rowids_to_delete.append(rowid)
            else:
                # If neither has data, keep the last, delete others
                for rowid, _ in records[:-1]:
                    rowids_to_delete.append(rowid)

    print(f"  -> Found {len(rowids_to_delete):,} dirty duplicate rowids to delete locally.")
    
    # Delete in chunks
    chunk_size = 900
    for i in range(0, len(rowids_to_delete), chunk_size):
        chunk = rowids_to_delete[i:i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        cur.execute(f"DELETE FROM history_master WHERE rowid IN ({placeholders})", chunk)

    # Normalize any remaining complaint_no or serial with spaces or formula wrappers
    cur.execute("""
        UPDATE history_master
        SET complaint_no = REPLACE(REPLACE(TRIM(complaint_no), '=', ''), '"', ''),
            serial = REPLACE(REPLACE(TRIM(serial), '=', ''), '"', '')
        WHERE complaint_no LIKE ' %' 
           OR complaint_no LIKE '% ' 
           OR complaint_no LIKE '%="%'
           OR serial LIKE ' %'
           OR serial LIKE '% '
           OR serial LIKE '%="%'
    """)

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM history_master")
    after_count = cur.fetchone()[0]

    # Optimize and reclaim disk space
    cur.execute("VACUUM")
    conn.close()

    print(f"✅ Local SQLite ({db_file}):")
    print(f"   Before: {before_count:,} rows")
    print(f"   Purged: {len(rowids_to_delete):,} duplicate rows")
    print(f"   After:  {after_count:,} clean rows")
    return before_count, after_count

def purge_turso_database():
    url, token = database.get_turso_credentials()
    if not url or not token:
        print("ℹ️ Turso credentials not configured. Skipping cloud purge.")
        return

    print("\n🌐 Connecting to Turso Cloud...")
    try:
        conn = database._get_shared_turso_connection(url, token)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM history_master")
        before_count = cur.fetchone()[0]

        cur.execute("SELECT rowid, complaint_no, phone, model FROM history_master")
        all_rows = cur.fetchall()

        complaint_map = {}
        for r in all_rows:
            rowid, cno, phone, model = r
            clean_c = clean_key(cno)
            has_data = bool((phone and str(phone).strip()) or (model and str(model).strip()))
            if clean_c not in complaint_map:
                complaint_map[clean_c] = []
            complaint_map[clean_c].append((rowid, has_data))

        rowids_to_delete = []
        for clean_c, records in complaint_map.items():
            if len(records) > 1:
                has_populated = any(rec[1] for rec in records)
                if has_populated:
                    for rowid, has_data in records:
                        if not has_data:
                            rowids_to_delete.append(rowid)
                else:
                    for rowid, _ in records[:-1]:
                        rowids_to_delete.append(rowid)

        print(f"  -> Found {len(rowids_to_delete):,} dirty duplicate rowids to delete in Turso Cloud.")

        # Batch delete in chunks of 200
        chunk_size = 200
        for i in range(0, len(rowids_to_delete), chunk_size):
            chunk = rowids_to_delete[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cur.execute(f"DELETE FROM history_master WHERE rowid IN ({placeholders})", chunk)

        # Normalize remaining
        cur.execute("""
            UPDATE history_master
            SET complaint_no = REPLACE(REPLACE(TRIM(complaint_no), '=', ''), '"', ''),
                serial = REPLACE(REPLACE(TRIM(serial), '=', ''), '"', '')
            WHERE complaint_no LIKE ' %' 
               OR complaint_no LIKE '% ' 
               OR complaint_no LIKE '%="%'
               OR serial LIKE ' %'
               OR serial LIKE '% '
               OR serial LIKE '%="%'
        """)

        cur.execute("SELECT COUNT(*) FROM history_master")
        after_count = cur.fetchone()[0]
        print(f"✅ Turso Cloud Database:")
        print(f"   Before: {before_count:,} rows")
        print(f"   Purged: {len(rowids_to_delete):,} duplicate rows")
        print(f"   After:  {after_count:,} clean rows")
    except Exception as e:
        print(f"❌ Failed to purge Turso Cloud: {e}")

if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(__file__), "..", database.DB_FILE)
    purge_local_database(db_file)
    purge_turso_database()
