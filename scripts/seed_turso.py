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
    schema_statements = [
        """
        CREATE TABLE IF NOT EXISTS history_master (
            complaint_no TEXT PRIMARY KEY,
            serial TEXT,
            phone TEXT,
            model TEXT,
            customer_name TEXT,
            technician_name TEXT,
            complaint_type TEXT,
            purchase_date TEXT,
            complaint_date TEXT,
            closed_date TEXT,
            remarks TEXT,
            closed_amount INTEGER DEFAULT 0
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_history_complaint_no ON history_master (complaint_no)",
        "CREATE INDEX IF NOT EXISTS idx_history_phone ON history_master (phone)",
        "CREATE INDEX IF NOT EXISTS idx_history_serial ON history_master (serial)",
        "CREATE INDEX IF NOT EXISTS idx_history_closed_date ON history_master (closed_date)",
        """
        CREATE TABLE IF NOT EXISTS tech_performance_master (
            complaint_no TEXT PRIMARY KEY,
            technician_name TEXT,
            status TEXT,
            closed_date TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tech_perf_tech ON tech_performance_master (technician_name)",
        "CREATE INDEX IF NOT EXISTS idx_tech_perf_date ON tech_performance_master (closed_date)",
        """
        CREATE TABLE IF NOT EXISTS model_part_catalog (
            model TEXT NOT NULL,
            part_no TEXT NOT NULL,
            part_description TEXT,
            board_type TEXT,
            historical_frequency INTEGER DEFAULT 1,
            last_installed_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (model, part_no)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_catalog_model ON model_part_catalog (model)",
        "CREATE INDEX IF NOT EXISTS idx_catalog_part_no ON model_part_catalog (part_no)",
        "CREATE INDEX IF NOT EXISTS idx_catalog_model_freq ON model_part_catalog (model, historical_frequency DESC)",
        """
        CREATE TABLE IF NOT EXISTS master_parts_lookup (
            part_no TEXT PRIMARY KEY,
            erp_description TEXT,
            erp_default_model TEXT,
            retail_price INTEGER DEFAULT 0,
            branch_store_qty INTEGER DEFAULT 0,
            branch_sales_qty INTEGER DEFAULT 0,
            tech_stock_qty INTEGER DEFAULT 0,
            total_stock_qty INTEGER DEFAULT 0,
            available_branch_stock INTEGER DEFAULT 0,
            available_total_stock INTEGER DEFAULT 0,
            stock_status TEXT DEFAULT 'Out of Stock',
            tech_allocations_json TEXT,
            is_pricing_pending INTEGER DEFAULT 0,
            source_document TEXT,
            last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_parts_lookup_status ON master_parts_lookup (stock_status)",
        "CREATE INDEX IF NOT EXISTS idx_parts_lookup_pricing_pending ON master_parts_lookup (is_pricing_pending)",
        """
        CREATE VIEW IF NOT EXISTS v_model_compatible_parts AS
        SELECT 
            c.model,
            c.part_no,
            COALESCE(p.erp_description, c.part_description) AS part_description,
            c.board_type,
            c.historical_frequency,
            COALESCE(p.retail_price, 0) AS retail_price,
            COALESCE(p.available_branch_stock, 0) AS branch_stock,
            COALESCE(p.tech_stock_qty, 0) AS tech_stock,
            COALESCE(p.available_total_stock, 0) AS total_stock,
            COALESCE(p.stock_status, 'Out of Stock') AS stock_status,
            COALESCE(p.tech_allocations_json, '{}') AS tech_allocations_json,
            COALESCE(p.is_pricing_pending, 1) AS is_pricing_pending,
            (SELECT COUNT(DISTINCT m2.model) FROM model_part_catalog m2 WHERE m2.part_no = c.part_no) AS cross_model_count
        FROM model_part_catalog c
        LEFT JOIN master_parts_lookup p ON c.part_no = p.part_no
        """
    ]

    for stmt in schema_statements:
        cloud_cursor.execute(stmt)
    print("✅ Schema created successfully on Turso.")

    # 4. Migrate tables in chunks
    local_conn = sqlite3.connect(local_db_path)
    local_cursor = local_conn.cursor()

    tables = [
        ("model_part_catalog", "model, part_no, part_description, board_type, historical_frequency, last_installed_date, created_at"),
        ("master_parts_lookup", "part_no, erp_description, erp_default_model, retail_price, branch_store_qty, branch_sales_qty, tech_stock_qty, total_stock_qty, available_branch_stock, available_total_stock, stock_status, tech_allocations_json, is_pricing_pending, source_document, last_synced"),
        ("tech_performance_master", "complaint_no, technician_name, status, closed_date"),
        ("history_master", "complaint_no, serial, phone, model, customer_name, technician_name, complaint_type, purchase_date, complaint_date, closed_date, remarks, closed_amount")
    ]

    print("\n📤 Migrating tables from local SQLite to Turso Cloud...")
    for tbl, cols in tables:
        col_list = [c.strip() for c in cols.split(",")]
        placeholders = ", ".join(["?"] * len(col_list))
        
        local_cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
        total_rows = local_cursor.fetchone()[0]
        
        local_cursor.execute(f"SELECT {cols} FROM {tbl}")
        rows = local_cursor.fetchall()

        print(f"  -> Migrating '{tbl}' ({total_rows:,} records)...")
        insert_sql = f"INSERT OR REPLACE INTO {tbl} ({cols}) VALUES ({placeholders})"
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
