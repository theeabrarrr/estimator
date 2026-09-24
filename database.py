# database.py
import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import sqlite3
import pandas as pd
from config import DB_NAME

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db_schema():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parts_master (
                model TEXT,
                part_no TEXT,
                part_name TEXT,
                price INTEGER,
                PRIMARY KEY (model, part_no)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_master (
                part_no TEXT PRIMARY KEY,
                item_code TEXT,
                item_desc TEXT,
                product TEXT,
                brand TEXT,
                category TEXT,
                capacity TEXT,
                bal_qty INTEGER DEFAULT 0,
                amount REAL DEFAULT 0.0,
                unit_price INTEGER DEFAULT 0,
                last_synced TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_pno ON stock_master(part_no)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_desc ON stock_master(item_desc)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_cat ON stock_master(category)")

        cursor.execute("""
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
                closed_amount INTEGER
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_search ON history_master(serial, phone, complaint_no)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_model ON history_master(model)")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tech_performance_master (
                complaint_no TEXT PRIMARY KEY,
                technician_name TEXT,
                status TEXT,
                closed_date TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tp ON tech_performance_master(technician_name, status, closed_date)")

def fetch_parts_and_models():
    init_db_schema()
    with get_connection() as conn:
        parts_df = pd.read_sql_query("SELECT * FROM parts_master", conn)
        h_models = pd.read_sql_query("SELECT DISTINCT model FROM history_master WHERE model != '' AND model != 'NAN'", conn)['model'].tolist()
        p_models = parts_df['model'].dropna().unique().tolist() if not parts_df.empty else []
        all_models = sorted(list(set([m for m in (h_models + p_models) if len(m) > 1])))
    return parts_df, all_models

def fetch_parts_with_live_stock(selected_model):
    init_db_schema()
    import re
    with get_connection() as conn:
        # Match model and family code
        fam_match = re.match(r"^([A-Z0-9]+-[0-9]{2}[A-Z]+)", selected_model)
        family_code = fam_match.group(1) if fam_match else selected_model[:7]

        sql = """
            SELECT 
                p.model,
                p.part_no,
                p.part_name,
                p.price as hist_price,
                COALESCE(s.bal_qty, 0) as bal_qty,
                COALESCE(s.unit_price, 0) as stock_price,
                s.category,
                s.brand,
                s.item_desc
            FROM parts_master p
            LEFT JOIN stock_master s ON UPPER(TRIM(p.part_no)) = UPPER(TRIM(s.part_no))
            WHERE p.model = ? OR p.model LIKE ?
        """
        df = pd.read_sql_query(sql, conn, params=(selected_model, f"{family_code}%"))

        # Also search stock_master directly for any parts tagged with this model or family code
        stock_extra_sql = """
            SELECT 
                ? as model,
                s.part_no,
                s.item_desc as part_name,
                0 as hist_price,
                s.bal_qty,
                s.unit_price as stock_price,
                s.category,
                s.brand,
                s.item_desc
            FROM stock_master s
            WHERE UPPER(s.item_desc) LIKE ? OR UPPER(s.item_desc) LIKE ?
        """
        extra_df = pd.read_sql_query(stock_extra_sql, conn, params=(
            selected_model, 
            f"%{selected_model.upper()}%", 
            f"%{family_code.upper()}%"
        ))

        combined = pd.concat([df, extra_df], ignore_index=True)
        if combined.empty:
            return pd.DataFrame()

        combined.drop_duplicates(subset=['part_no'], inplace=True)
        
        # Decide effective price: priority to hist_price if > 0, then stock_price
        combined['price'] = combined.apply(
            lambda r: int(r['hist_price']) if r['hist_price'] > 0 else int(r['stock_price']),
            axis=1
        )
        combined['bal_qty'] = pd.to_numeric(combined['bal_qty'], errors='coerce').fillna(0).astype(int)
        
        return combined

def search_stock_global(query_str, limit=60):
    init_db_schema()
    q = f"%{query_str.strip()}%"
    with get_connection() as conn:
        sql = """
            SELECT 
                part_no,
                item_desc as part_name,
                brand,
                category,
                capacity,
                bal_qty,
                unit_price as price
            FROM stock_master
            WHERE part_no LIKE ? OR UPPER(item_desc) LIKE UPPER(?) OR UPPER(category) LIKE UPPER(?)
            ORDER BY bal_qty DESC, item_desc ASC
            LIMIT ?
        """
        return pd.read_sql_query(sql, conn, params=(q, q, q, limit))

def get_stock_metadata():
    init_db_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*), SUM(CASE WHEN bal_qty > 0 THEN 1 ELSE 0 END), MAX(last_synced) FROM stock_master")
        row = cursor.fetchone()
        if not row or row[0] == 0:
            return {'total_items': 0, 'in_stock_items': 0, 'last_synced': 'Never'}
        return {
            'total_items': row[0] or 0,
            'in_stock_items': row[1] or 0,
            'last_synced': row[2] or 'Synced'
        }

def search_history_records(query_str, clean_phone_str):
    with get_connection() as conn:
        sql = """
            SELECT complaint_no, model, serial, customer_name, phone, technician_name,
                   complaint_type, purchase_date, complaint_date, closed_date, remarks, closed_amount
            FROM history_master
            WHERE serial LIKE ? 
               OR complaint_no LIKE ? 
               OR (phone != '' AND phone LIKE ?)
            ORDER BY closed_date DESC LIMIT 30
        """
        match_df = pd.read_sql_query(sql, conn, params=(
            f"%{query_str}%", 
            f"%{query_str}%", 
            f"%{clean_phone_str if clean_phone_str else query_str}%"
        ))
    return match_df

def fetch_performance_data():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='tech_performance_master'")
        if cursor.fetchone()[0] == 0:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM tech_performance_master", conn)