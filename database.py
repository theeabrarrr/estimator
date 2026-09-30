import sqlite3
import pandas as pd
import json

DB_FILE = "dwp_service.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tech_performance_master'")
        if cursor.fetchone() is None:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM tech_performance_master", conn)