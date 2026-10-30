#!/usr/bin/env python3
"""
Seed & Migration Tool: Local SQLite (dwp_service.db) -> Turso Cloud Database
Transfers all historical complaint records, technician KPIs, parts catalogs, and retail pricing
to your permanent Turso libSQL Cloud Database.

Usage:
    python scripts/seed_turso.py --url "libsql://dwp-service-username.turso.io" --token "your-auth-token"
Or set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in environment or .streamlit/secrets.toml:
    python scripts/seed_turso.py
"""

from __future__ import annotations
import os
import sys
import argparse
import sqlite3
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database

def validate_table_and_columns(tbl: str, cols: list[str], schema_whitelist: dict[str, list[str]]) -> None:
    """
    Validates that the provided table name and column names are in the allowed schema whitelist.
    Prevents SQL injection vulnerabilities caused by dynamic identifier interpolation.
    """
    if not isinstance(tbl, str) or tbl not in schema_whitelist:
        raise ValueError(f"Unauthorized or invalid table name for migration: {tbl!r}")

    allowed_cols = schema_whitelist[tbl]
    for c in cols:
        if not isinstance(c, str) or c not in allowed_cols:
            raise ValueError(f"Unauthorized or invalid column name '{c}' for table '{tbl}'")


def migrate_to_turso(url: str, token: str):
    local_db_path = database.DB_FILE
    if not os.path.exists(local_db_path):
        print(f"❌ Error: Local database file '{local_db_path}' not found.")
        sys.exit(1)

    print(f"🚀 Initializing migration to Turso Cloud Database...")
    print(f"📍 Turso URL: {url}")
    print(f"📍 Source DB: {local_db_path} ({os.path.getsize(local_db_path) / (1024*1024):.2f} MB)")

    # 1. Connect to Turso Cloud
    cloud_conn = database.TursoConnection(url, token)
    cloud_cursor = cloud_conn.cursor()

    # 2. Test Connection
    try:
        cloud_cursor.execute("SELECT 1")
        print("✅ Connection to Turso Cloud successful!")
    except Exception as e:
        print(f"❌ Failed to connect to Turso Cloud: {e}")
        sys.exit(1)

    # 3. Create Schema on Turso Cloud
    print("\n📦 Setting up database schema and views on Turso...")
    if hasattr(cloud_conn, "execute_batch"):
        cloud_conn.execute_batch(database.SCHEMA_DDL_STATEMENTS)
    else:
        for stmt in database.SCHEMA_DDL_STATEMENTS:
            cloud_cursor.execute(stmt)
    print("✅ Schema created successfully on Turso.")

    # 4. Migrate tables in chunks
    local_conn = sqlite3.connect(local_db_path)
    local_cursor = local_conn.cursor()

    ALLOWED_TABLES_MIGRATION_SCHEMA: dict[str, list[str]] = {
        "model_part_catalog": [
            "model", "part_no", "part_description", "board_type",
            "historical_frequency", "last_installed_date", "created_at"
        ],
        "master_parts_lookup": [
            "part_no", "erp_description", "erp_default_model", "retail_price",
            "branch_store_qty", "branch_sales_qty", "tech_stock_qty", "total_stock_qty",
            "available_branch_stock", "available_total_stock", "stock_status",
            "tech_allocations_json", "is_pricing_pending", "source_document", "last_synced"
        ],
        "tech_performance_master": [
            "complaint_no", "technician_name", "status", "closed_date"
        ],
        "history_master": [
            "complaint_no", "serial", "phone", "model", "customer_name",
            "technician_name", "complaint_type", "purchase_date", "complaint_date",
            "closed_date", "remarks", "closed_amount"
        ]
    }

    print("\n📤 Migrating tables from local SQLite to Turso Cloud...")
    for tbl, allowed_cols in ALLOWED_TABLES_MIGRATION_SCHEMA.items():
        validate_table_and_columns(tbl, allowed_cols, ALLOWED_TABLES_MIGRATION_SCHEMA)
        cols_clause = ", ".join(f'"{c}"' for c in allowed_cols)
        placeholders = ", ".join(["?"] * len(allowed_cols))
        
        local_cursor.execute(f'SELECT COUNT(*) FROM "{tbl}"')
        total_rows = local_cursor.fetchone()[0]
        
        local_cursor.execute(f'SELECT {cols_clause} FROM "{tbl}"')
        rows = local_cursor.fetchall()

        print(f"  -> Migrating '{tbl}' ({total_rows:,} records)...")
        insert_sql = f'INSERT OR REPLACE INTO "{tbl}" ({cols_clause}) VALUES ({placeholders})'
        t0 = time.time()
        cloud_cursor.executemany(insert_sql, rows)
        elapsed = time.time() - t0
        print(f"     ✅ '{tbl}' migrated ({len(rows):,} rows in {elapsed:.1f}s)")

    local_conn.close()

    print("\n🎉 MIGRATION COMPLETE! Your Turso Cloud Database is fully populated.")
    print("👉 Now, any file upload on Streamlit Cloud will permanently persist to Turso.")

def main():
    parser = argparse.ArgumentParser(description="Migrate local dwp_service.db to Turso Cloud Database")
    parser.add_argument("--url", help="Turso Database URL (e.g. libsql://... or https://...)")
    parser.add_argument("--token", help="Turso Auth Token")
    args = parser.parse_args()

    url = args.url
    token = args.token

    if not url or not token:
        cred_url, cred_token = database.get_turso_credentials()
        url = url or cred_url
        token = token or cred_token

    if not url or not token:
        print("❌ Error: Turso credentials missing.")
        print("\nPlease provide them via arguments:")
        print("  python scripts/seed_turso.py --url <TURSO_URL> --token <TURSO_TOKEN>")
        print("\nOr configure them in .streamlit/secrets.toml:")
        print('  TURSO_DATABASE_URL = "libsql://dwp-service-username.turso.io"')
        print('  TURSO_AUTH_TOKEN = "your-turso-auth-token"')
        sys.exit(1)

    migrate_to_turso(url, token)

if __name__ == "__main__":
    main()
