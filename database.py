# database.py
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