from __future__ import annotations
import os
import sqlite3
import pandas as pd
import json
import re
import base64
import requests
import warnings
from contextlib import contextmanager

# Suppress harmless pandas DBAPI UserWarning when using custom Turso connection wrappers
warnings.filterwarnings('ignore', category=UserWarning, message='.*pandas only supports SQLAlchemy connectable.*')

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dwp_service.db")

def get_turso_credentials():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if not url and "TURSO_DATABASE_URL" in st.secrets:
                    url = str(st.secrets["TURSO_DATABASE_URL"])
                if not token and "TURSO_AUTH_TOKEN" in st.secrets:
                    token = str(st.secrets["TURSO_AUTH_TOKEN"])
        except Exception:
            pass
    return (url.strip() if url else None), (token.strip() if token else None)

_TURSO_FALLBACK_ACTIVE = False

def is_turso_active() -> bool:
    url, token = get_turso_credentials()
    return bool(url and token and not _TURSO_FALLBACK_ACTIVE)

def get_database_status() -> str:
    url, token = get_turso_credentials()
    if not url or not token:
        return "LOCAL_ONLY"
    if _TURSO_FALLBACK_ACTIVE:
        return "TURSO_FALLBACK_LOCAL"
    return "TURSO_ONLINE"

def reset_turso_fallback() -> None:
    global _TURSO_FALLBACK_ACTIVE
    _TURSO_FALLBACK_ACTIVE = False

class TursoCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []
        self._idx = 0
        self.rowcount = -1
        self.lastrowid = None

    def _format_arg(self, val):
        if val is None or pd.isna(val):
            return {"type": "null"}
        elif isinstance(val, bool):
            return {"type": "integer", "value": "1" if val else "0"}
        elif isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        elif isinstance(val, float):
            return {"type": "float", "value": val}
        elif isinstance(val, (bytes, bytearray)):
            return {"type": "blob", "base64": base64.b64encode(val).decode("ascii")}
        else:
            return {"type": "text", "value": str(val)}

    def _parse_val(self, item):
        t = item.get("type")
        if t == "null":
            return None
        elif t == "integer":
            return int(item.get("value", 0))
        elif t == "float":
            return float(item.get("value", 0.0))
        elif t == "text":
            return item.get("value", "")
        elif t == "blob":
            return base64.b64decode(item.get("base64", ""))
        return item.get("value")

    def execute(self, sql, params=()):
        if params is None:
            params = ()
        elif not isinstance(params, (list, tuple)):
            params = (params,)

        stmt = {
            "sql": sql,
            "args": [self._format_arg(p) for p in params]
        }
        payload = {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"}
            ]
        }
        res = self.conn._post(payload)
        first_res = res.get("results", [{}])[0]
        if first_res.get("type") == "error":
            err = first_res.get("error", {})
            raise sqlite3.OperationalError(f"Turso Error: {err.get('message', 'Unknown error')}")

        exec_res = first_res.get("response", {}).get("result", {})
        cols = [c["name"] for c in exec_res.get("cols", [])]
        self.description = [(c, None, None, None, None, None, None) for c in cols] if cols else None
        
        raw_rows = exec_res.get("rows", [])
        self._rows = [tuple(self._parse_val(cell) for cell in row) for row in raw_rows]
        self._idx = 0
        self.rowcount = exec_res.get("affected_row_count", len(self._rows))
        self.lastrowid = exec_res.get("last_insert_rowid")
        return self

    def executemany(self, sql, seq_of_params):
        if not seq_of_params:
            return self
        batch_size = 200
        param_list = list(seq_of_params)
        for i in range(0, len(param_list), batch_size):
            chunk = param_list[i:i + batch_size]
            requests_list = []
            for row in chunk:
                if row is None:
                    row = ()
                elif not isinstance(row, (list, tuple)):
                    row = (row,)
                stmt = {
                    "sql": sql,
                    "args": [self._format_arg(p) for p in row]
                }
                requests_list.append({"type": "execute", "stmt": stmt})
            requests_list.append({"type": "close"})
            res = self.conn._post({"requests": requests_list})
            for r in res.get("results", []):
                if r.get("type") == "error":
                    err = r.get("error", {})
                    raise sqlite3.OperationalError(f"Turso Batch Error: {err.get('message', 'Unknown error')}")
        return self

    def fetchone(self):
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        if self._idx < len(self._rows):
            rows = self._rows[self._idx:]
            self._idx = len(self._rows)
            return rows
        return []

    def close(self):
        pass

class TursoConnection:
    def __init__(self, url, token):
        base = re.sub(r"^libsql://", "https://", url.strip()).rstrip("/")
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "https://" + base
        self.pipeline_url = f"{base}/v2/pipeline"
        self.token = token.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        })

    def _post(self, payload, timeout=6):
        import time
        max_retries = 2
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = self.session.post(self.pipeline_url, json=payload, timeout=timeout)
                if resp.status_code != 200:
                    raise sqlite3.OperationalError(f"Turso HTTP {resp.status_code}: {resp.text}")
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    global _TURSO_FALLBACK_ACTIVE
                    _TURSO_FALLBACK_ACTIVE = True
                    _reset_shared_turso_connection()
                    raise sqlite3.OperationalError(f"Turso Network Error after {max_retries} attempts: {last_err}")

    def execute_batch(self, sql_statements: list[str], timeout=15):
        """
        Executes a batch of SQL statements in a single atomic /v2/pipeline HTTP request.
        """
        requests_list = []
        for sql in sql_statements:
            s = sql.strip()
            if s:
                requests_list.append({"type": "execute", "stmt": {"sql": s, "args": []}})
        if not requests_list:
            return
        requests_list.append({"type": "close"})
        res = self._post({"requests": requests_list}, timeout=timeout)
        for r in res.get("results", []):
            if r.get("type") == "error":
                err = r.get("error", {})
                raise sqlite3.OperationalError(f"Turso Batch Error: {err.get('message', 'Unknown error')}")

    def cursor(self):
        return TursoCursor(self)

    def commit(self):
        pass

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    def rollback(self):
        pass

_SHARED_TURSO_CONN = None

def _get_shared_turso_connection(url: str, token: str) -> TursoConnection:
    global _SHARED_TURSO_CONN
    if _SHARED_TURSO_CONN is None:
        _SHARED_TURSO_CONN = TursoConnection(url, token)
    return _SHARED_TURSO_CONN

def _reset_shared_turso_connection():
    global _SHARED_TURSO_CONN
    if _SHARED_TURSO_CONN is not None:
        try:
            _SHARED_TURSO_CONN.close()
        except Exception:
            pass
        _SHARED_TURSO_CONN = None

@contextmanager
def get_connection():
    global _TURSO_FALLBACK_ACTIVE
    url, token = get_turso_credentials()
    if url and token and not _TURSO_FALLBACK_ACTIVE:
        try:
            conn = _get_shared_turso_connection(url, token)
            yield conn
        except Exception as e:
            warnings.warn(f"Turso Cloud connection failed ({e}). Falling over to local high-speed SQLite database.")
            _TURSO_FALLBACK_ACTIVE = True
            _reset_shared_turso_connection()
            conn = sqlite3.connect(DB_FILE)
            try:
                yield conn
            finally:
                conn.close()
    else:
        conn = sqlite3.connect(DB_FILE)
        try:
            yield conn
        finally:
            conn.close()

def sync_to_local_sqlite(sql: str, params_seq=None):
    """Mirrors database mutations to local dwp_service.db snapshot for instant offline readiness."""
    try:
        with sqlite3.connect(DB_FILE) as local_conn:
            c = local_conn.cursor()
            if params_seq:
                c.executemany(sql, params_seq)
            else:
                c.execute(sql)
            local_conn.commit()
    except Exception:
        pass

def search_history_records(query_str, clean_phone_str):
    init_estimator_schema()
    with get_connection() as conn:
        clean_q = query_str.strip().replace('-', '').replace(' ', '').replace('=', '').replace('"', '')
        phone_param = clean_phone_str if clean_phone_str else clean_q
        phone_no_zero = phone_param.lstrip('0') if phone_param else clean_q
        
        sql = """
            SELECT 
                h.complaint_no, 
                h.model, 
                h.serial, 
                h.customer_name, 
                h.phone, 
                COALESCE(t.technician_name, h.technician_name) AS technician_name,
                h.complaint_type, 
                h.purchase_date, 
                h.complaint_date, 
                COALESCE(h.closed_date, t.closed_date) AS closed_date, 
                h.remarks, 
                h.closed_amount,
                COALESCE(t.status, 'COMPLETED') AS status
            FROM history_master h
            LEFT JOIN tech_performance_master t 
                ON (h.complaint_no = t.complaint_no OR REPLACE(REPLACE(h.complaint_no, '=', ''), '"', '') = t.complaint_no)
            WHERE h.serial LIKE ? 
               OR h.complaint_no LIKE ? 
               OR (h.phone != '' AND (h.phone LIKE ? OR h.phone LIKE ? OR h.phone LIKE ?))
               OR h.customer_name LIKE ?

            UNION ALL

            SELECT 
                t.complaint_no,
                'N/A' AS model,
                'N/A' AS serial,
                'N/A' AS customer_name,
                '' AS phone,
                t.technician_name,
                'Service Call' AS complaint_type,
                '' AS purchase_date,
                '' AS complaint_date,
                t.closed_date,
                'Logged in performance/canceled logs (' || t.status || ')' AS remarks,
                0 AS closed_amount,
                t.status AS status
            FROM tech_performance_master t
            WHERE t.status IN ('REJECTED', 'CANCELED', 'NIL')
              AND NOT EXISTS (
                  SELECT 1 FROM history_master h 
                  WHERE h.complaint_no = t.complaint_no 
                     OR REPLACE(REPLACE(h.complaint_no, '=', ''), '"', '') = t.complaint_no
              )
              AND (t.complaint_no LIKE ? OR t.technician_name LIKE ?)

            ORDER BY closed_date DESC LIMIT 30
        """
        match_df = pd.read_sql_query(sql, conn, params=(
            f"%{clean_q}%", 
            f"%{clean_q}%", 
            f"%{query_str}%",
            f"%{phone_param}%",
            f"%{phone_no_zero}%",
            f"%{query_str}%",
            f"%{clean_q}%",
            f"%{query_str}%"
        ))
    return match_df

def fetch_performance_data(start_date=None, end_date=None):
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tech_performance_master'")
        if cursor.fetchone() is None:
            return pd.DataFrame()
        if start_date and end_date:
            s_str = str(start_date)
            e_str = str(end_date)
            return pd.read_sql_query(
                "SELECT * FROM tech_performance_master WHERE closed_date >= ? AND closed_date <= ? ORDER BY closed_date DESC",
                conn,
                params=(s_str, e_str)
            )
        return pd.read_sql_query("SELECT * FROM tech_performance_master ORDER BY closed_date DESC", conn)

# ============================================================================
# SPARE PARTS ESTIMATOR ENGINE SCHEMA & DATA ACCESS LAYER
# ============================================================================

_SCHEMA_INITIALIZED = False

SCHEMA_DDL_STATEMENTS = [
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
        COALESCE(xm.cross_model_count, 1) AS cross_model_count
    FROM model_part_catalog c
    LEFT JOIN master_parts_lookup p ON c.part_no = p.part_no
    LEFT JOIN (
        SELECT part_no, COUNT(DISTINCT model) AS cross_model_count
        FROM model_part_catalog
        GROUP BY part_no
    ) xm ON c.part_no = xm.part_no
    """
]

def is_schema_ready(conn) -> bool:
    """Fast non-blocking verification if catalog tables exist and are populated."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM model_part_catalog LIMIT 1")
        row = cursor.fetchone()
        return row is not None
    except Exception:
        return False

def init_estimator_schema(force: bool = False):
    """
    Ensures history_master, tech_performance_master, model_part_catalog, master_parts_lookup, and v_model_compatible_parts exist.
    Fast-paths in <100ms if tables already exist, eliminating 17 sequential remote network calls.
    """
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED and not force:
        return
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Fast-path check: if schema is already healthy, exit instantly
            if not force and is_schema_ready(conn):
                _SCHEMA_INITIALIZED = True
                return

            if force:
                try:
                    cursor.execute("DROP VIEW IF EXISTS v_model_compatible_parts")
                    conn.commit()
                except Exception:
                    pass

            # Execute schema DDL statements (single batched HTTP request for Turso)
            if hasattr(conn, "execute_batch"):
                conn.execute_batch(SCHEMA_DDL_STATEMENTS)
            else:
                for stmt in SCHEMA_DDL_STATEMENTS:
                    cursor.execute(stmt)
                conn.commit()

            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM model_part_catalog),
                    (SELECT COUNT(*) FROM master_parts_lookup WHERE retail_price > 0),
                    (SELECT COUNT(*) FROM history_master),
                    (SELECT COUNT(*) FROM history_master WHERE phone IS NOT NULL AND phone != ''),
                    (SELECT COUNT(*) FROM tech_performance_master)
            """)
            counts_row = cursor.fetchone()
            cat_count = counts_row[0] if counts_row else 0
            priced_count = counts_row[1] if counts_row else 0
            hist_count = counts_row[2] if counts_row else 0
            valid_phone_count = counts_row[3] if counts_row else 0
            perf_count = counts_row[4] if counts_row else 0

        if cat_count == 0:
            try:
                import etl
                etl.sync_model_part_catalog_from_feedback()
                etl.parse_store_stock_pdf()
            except Exception as e:
                print(f"Catalog init error: {e}")

        if hist_count == 0 or valid_phone_count == 0:
            try:
                import etl
                import config
                fb_file = getattr(config, 'DEFAULT_FB_FILE', 'quality_feedback_report_28SEP2026_142900.csv')
                coll_file = getattr(config, 'DEFAULT_COLL_FILE', 'Detail_Collection_28SEP26_023634PM.xlsx')
                if fb_file and os.path.exists(fb_file):
                    etl.ingest_feedback_and_pricing(fb_file, coll_file)
            except Exception as e:
                print(f"History master init error: {e}")

        if perf_count < 1000:
            try:
                import etl
                import config
                fb_file = getattr(config, 'DEFAULT_FB_FILE', None)
                if fb_file and os.path.exists(fb_file):
                    etl.ingest_performance_pipeline(fb_file)
            except Exception as e:
                print(f"Tech performance master init error: {e}")

        # Automatically merge verified parts from baseline parts_master if present and run cross-series enrichment on initial seed
        if cat_count == 0:
            merge_parts_master_into_catalog()
            enrich_cross_series_compatibilities()

        _SCHEMA_INITIALIZED = True
    except Exception as e:
        _SCHEMA_INITIALIZED = False
        raise e

def enrich_cross_series_compatibilities() -> None:
    """
    Enriches model_part_catalog with cross-series evaporators, compressors, and coils.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. 18-Series Inverter Evaporators (Interchangeable 1.5 Ton coils)
        evap_18 = [
            ('11001060868', 'Evaporator Assy GS-18PITH1W 11001060868', 'Evaporator Assy'),
            ('1002937LC', 'Evaporator assy GS-18CITH1 1002937LC / 1002686', 'Evaporator Assy'),
            ('1002686LC', 'Evaporater Assy 18LM4 18LITH 1002686LC / 1002937', 'Evaporator Assy'),
            ('11001000207LC', 'Evaporaters Assy 18AITH11 18FITH1 11001000207LC', 'Evaporator Assy')
        ]
        m18_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog 
            WHERE model LIKE 'GS-18FITH%' OR model LIKE 'GS-18CITH%' OR model LIKE 'GS-18PITH%' OR model LIKE 'GS-18AITH%' OR model LIKE 'GS-18LITH%'
        """).fetchall()
        for (m_name,) in m18_rows:
            for p_no, desc, board in evap_18:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        # 2. 12-Series Inverter Evaporators (Interchangeable 1.0 Ton coils)
        evap_12 = [
            ('1002976', 'Evaporater Assy 12LM4 / 12LM5L 1002976', 'Evaporator Assy'),
            ('1002422LC', 'Evaporator Assy 12CITH1 1002422LC', 'Evaporator Assy'),
            ('1002000030', 'Evaporator Assy 1002000030 GS-12FITH6C', 'Evaporator Assy')
        ]
        m12_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog 
            WHERE model LIKE 'GS-12FITH%' OR model LIKE 'GS-12CITH%' OR model LIKE 'GS-12PITH%' OR model LIKE 'GS-12LITH%'
        """).fetchall()
        for (m_name,) in m12_rows:
            for p_no, desc, board in evap_12:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        # 3. Water Dispenser Compressors
        wd_comps = [
            ('QD36LWL', 'WD Compressor WD-300F / WD-350F /WD-450F QD36LWL', 'WD Compressor'),
            ('QD36LW', 'Compressor For WD-300F/WD- 350F/WD-450F (66625) QD36LW', 'WD Compressor')
        ]
        m_wd_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog WHERE model LIKE 'WD-%' OR model LIKE 'GW-%'
        """).fetchall()
        wd_models_set = set([r[0] for r in m_wd_rows] + ['WD-300', 'WD-300F', 'WD-350F', 'WD-450F', 'GW-JL500FC', 'GW-JL500FS'])
        for m_name in wd_models_set:
            for p_no, desc, board in wd_comps:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        # 4. Refrigerator Compressors (Interchangeable across Everest series)
        ref_comps = [
            ('GR18-E51519002', 'Compressors ENK150KL GR-E9978G-CW1 GR18-E51519002', 'REF Compressor'),
            ('GR18-E51519001', 'Compressors ETK 130KL GR-E8768G-CW1 GR18-E51519001', 'REF Compressor'),
            ('GR18-73710005', 'COMPRESSOR - 95AT 310 GR18-73710005', 'REF Compressor'),
            ('GR18-73710006', 'COMPRESSOR - 12AT 360 GR18-73710006', 'REF Compressor')
        ]
        m_ref_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog WHERE model LIKE 'GR-%'
        """).fetchall()
        for (m_name,) in m_ref_rows:
            for p_no, desc, board in ref_comps:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        conn.commit()

def merge_parts_master_into_catalog() -> int:
    """
    Enriches model_part_catalog and master_parts_lookup with verified parts
    from the company's baseline parts_master table.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='parts_master'")
        if not cursor.fetchone():
            return 0
        
        pm_rows = cursor.execute("""
            SELECT model, part_no, part_name, price 
            FROM parts_master 
            WHERE model IS NOT NULL AND part_no IS NOT NULL
        """).fetchall()
        
        if not pm_rows:
            return 0

        existing = cursor.execute("SELECT model, part_no FROM model_part_catalog").fetchall()
        existing_pairs = set((m, p) for m, p in existing)
        
        catalog_to_insert = []
        lookup_to_upsert = []
        
        for m, p_no, p_name, price in pm_rows:
            m = str(m).strip().upper()
            p_no = str(p_no).strip()
            desc = str(p_name).strip() if p_name else ""
            
            if not m or not p_no:
                continue
            
            # Rule 7: Skip B-grade sets
            if re.search(r'b[- ]?grade\s+set', p_no + ' ' + desc, re.IGNORECASE):
                continue
                
            # Classify board type
            text = (p_no + ' ' + desc).upper()
            if 'COMP' in text or 'QD' in text:
                board = 'WD Compressor' if m.startswith('WD') else 'Compressor'
            elif 'VALVE' in text:
                board = 'Cut Off Valve'
            elif 'PCB' in text or 'BOARD' in text or 'MODULE' in text:
                board = 'Electronic PCB'
            elif 'MOTOR' in text:
                board = 'Fan Motor'
            elif 'EVAPORATOR' in text:
                board = 'Evaporator Assy'
            elif 'CONDEN' in text:
                board = 'Condenser'
            elif 'THERMOSTAT' in text:
                board = 'WD Thermostat'
            elif 'DRIER' in text or 'FILTER' in text:
                board = 'Filter Drier'
            elif m.startswith('WD'):
                board = 'WD Parts'
            else:
                board = 'Spare Part'
                
            if (m, p_no) not in existing_pairs:
                catalog_to_insert.append((m, p_no, desc, board, 1, ''))
                existing_pairs.add((m, p_no))
                
            try:
                p_price = int(price) if price and str(price).isdigit() else 0
            except Exception:
                p_price = 0
                
            lookup_to_upsert.append((p_no, desc, p_price))
            
        if catalog_to_insert:
            cursor.executemany("""
                INSERT OR IGNORE INTO model_part_catalog (
                    model, part_no, part_description, board_type, historical_frequency, last_installed_date
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, catalog_to_insert)
            
        # Ensure master_parts_lookup has prices from parts_master for parts where price is missing/0
        for p_no, desc, price in lookup_to_upsert:
            cursor.execute("SELECT retail_price, is_pricing_pending FROM master_parts_lookup WHERE part_no = ?", (p_no,))
            row = cursor.fetchone()
            if row is None:
                is_pend = 0 if price > 0 else 1
                cursor.execute("""
                    INSERT INTO master_parts_lookup (
                        part_no, erp_description, retail_price, is_pricing_pending, stock_status, last_synced
                    ) VALUES (?, ?, ?, ?, 'Out of Stock', CURRENT_TIMESTAMP)
                """, (p_no, desc, price, is_pend))
            elif (row[0] == 0 or row[1] == 1) and price > 0:
                cursor.execute("""
                    UPDATE master_parts_lookup 
                    SET retail_price = ?, is_pricing_pending = 0 
                    WHERE part_no = ? AND (retail_price = 0 OR is_pricing_pending = 1)
                """, (price, p_no))
                
        # Cross-Series Coil & Compressor Interchangeability Enrichment
        # 1. 18-Series Inverter Evaporators (Interchangeable 1.5 Ton coils)
        evap_18 = [
            ('11001060868', 'Evaporator Assy GS-18PITH1W 11001060868', 'Evaporator Assy'),
            ('1002937LC', 'Evaporator assy GS-18CITH1 1002937LC / 1002686', 'Evaporator Assy'),
            ('1002686LC', 'Evaporater Assy 18LM4 18LITH 1002686LC / 1002937', 'Evaporator Assy'),
            ('11001000207LC', 'Evaporaters Assy 18AITH11 18FITH1 11001000207LC', 'Evaporator Assy')
        ]
        m18_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog 
            WHERE model LIKE 'GS-18FITH%' OR model LIKE 'GS-18CITH%' OR model LIKE 'GS-18PITH%' OR model LIKE 'GS-18AITH%' OR model LIKE 'GS-18LITH%'
        """).fetchall()
        for (m_name,) in m18_rows:
            for p_no, desc, board in evap_18:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        # 2. 12-Series Inverter Evaporators (Interchangeable 1.0 Ton coils)
        evap_12 = [
            ('1002976', 'Evaporater Assy 12LM4 / 12LM5L 1002976', 'Evaporator Assy'),
            ('1002422LC', 'Evaporator Assy 12CITH1 1002422LC', 'Evaporator Assy'),
            ('1002000030', 'Evaporator Assy 1002000030 GS-12FITH6C', 'Evaporator Assy')
        ]
        m12_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog 
            WHERE model LIKE 'GS-12FITH%' OR model LIKE 'GS-12CITH%' OR model LIKE 'GS-12PITH%' OR model LIKE 'GS-12LITH%'
        """).fetchall()
        for (m_name,) in m12_rows:
            for p_no, desc, board in evap_12:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        # 3. Water Dispenser Compressors
        wd_comps = [
            ('QD36LWL', 'WD Compressor WD-300F / WD-350F /WD-450F QD36LWL', 'WD Compressor'),
            ('QD36LW', 'Compressor For WD-300F/WD- 350F/WD-450F (66625) QD36LW', 'WD Compressor')
        ]
        m_wd_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog WHERE model LIKE 'WD-%' OR model LIKE 'GW-%'
        """).fetchall()
        wd_models_set = set([r[0] for r in m_wd_rows] + ['WD-300', 'WD-300F', 'WD-350F', 'WD-450F', 'GW-JL500FC', 'GW-JL500FS'])
        for m_name in wd_models_set:
            for p_no, desc, board in wd_comps:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        # 4. Refrigerator Compressors (Interchangeable across Everest series)
        ref_comps = [
            ('GR18-E51519002', 'Compressors ENK150KL GR-E9978G-CW1 GR18-E51519002', 'REF Compressor'),
            ('GR18-E51519001', 'Compressors ETK 130KL GR-E8768G-CW1 GR18-E51519001', 'REF Compressor'),
            ('GR18-73710005', 'COMPRESSOR - 95AT 310 GR18-73710005', 'REF Compressor'),
            ('GR18-73710006', 'COMPRESSOR - 12AT 360 GR18-73710006', 'REF Compressor')
        ]
        m_ref_rows = cursor.execute("""
            SELECT DISTINCT model FROM model_part_catalog WHERE model LIKE 'GR-%'
        """).fetchall()
        for (m_name,) in m_ref_rows:
            for p_no, desc, board in ref_comps:
                cursor.execute("""
                    INSERT OR IGNORE INTO model_part_catalog (model, part_no, part_description, board_type, historical_frequency, last_installed_date)
                    VALUES (?, ?, ?, ?, 1, '')
                """, (m_name, p_no, desc, board))

        conn.commit()
        return len(catalog_to_insert)

def get_all_models_for_estimator() -> list[str]:
    """
    Returns all unique models available in model_part_catalog ordered by frequency of jobs.
    """
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = """
            SELECT model, SUM(historical_frequency) as total_freq
            FROM model_part_catalog
            GROUP BY model
            ORDER BY total_freq DESC, model ASC
        """
        rows = cursor.execute(sql).fetchall()
        return [r[0] for r in rows if r[0]]

def get_parts_by_model(model_name: str) -> pd.DataFrame:
    """
    Fetches all compatible parts, live prices, stock levels, and cross-compatibility for a given model.
    """
    init_estimator_schema()
    if not model_name:
        return pd.DataFrame()
    m = str(model_name).strip().upper()
    with get_connection() as conn:
        sql = """
            SELECT 
                model,
                part_no,
                part_description,
                board_type,
                historical_frequency,
                retail_price,
                branch_stock,
                tech_stock,
                total_stock,
                stock_status,
                tech_allocations_json,
                is_pricing_pending,
                cross_model_count
            FROM v_model_compatible_parts
            WHERE model = ?
            ORDER BY historical_frequency DESC, part_no ASC
        """
        return pd.read_sql_query(sql, conn, params=(m,))

def get_cross_model_compatibilities(part_no: str) -> list[tuple[str, int]]:
    """
    Returns list of (model, frequency) pairs for a specific part number across all models.
    """
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = """
            SELECT model, historical_frequency
            FROM model_part_catalog
            WHERE part_no = ?
            ORDER BY historical_frequency DESC, model ASC
        """
        return cursor.execute(sql, (str(part_no).strip(),)).fetchall()

def get_all_cross_model_compatibilities_map() -> dict[str, list[tuple[str, int]]]:
    """
    Returns a complete mapping of part_no -> list of (model, frequency) pairs.
    Fetches all model-part associations in a single bulk query to eliminate N+1 latency.
    """
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = """
            SELECT part_no, model, historical_frequency
            FROM model_part_catalog
            ORDER BY historical_frequency DESC, model ASC
        """
        rows = cursor.execute(sql).fetchall()
        result: dict[str, list[tuple[str, int]]] = {}
        for p_no, model, freq in rows:
            clean_p = str(p_no).strip()
            if clean_p not in result:
                result[clean_p] = []
            result[clean_p].append((str(model).strip(), int(freq) if freq else 1))
        return result

def update_part_price(part_no: str, new_price: float | int) -> bool:
    """
    Persists a manual price override for an unpriced or existing part into master_parts_lookup.
    """
    init_estimator_schema()
    clean_pno = str(part_no).strip()
    price_val = int(round(float(new_price)))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT part_no FROM master_parts_lookup WHERE part_no = ?", (clean_pno,))
        row = cursor.fetchone()
        if row:
            cursor.execute("""
                UPDATE master_parts_lookup
                SET retail_price = ?,
                    is_pricing_pending = 0,
                    last_synced = CURRENT_TIMESTAMP
                WHERE part_no = ?
            """, (price_val, clean_pno))
        else:
            cursor.execute("""
                INSERT INTO master_parts_lookup 
                (part_no, erp_description, retail_price, is_pricing_pending, stock_status, last_synced)
                VALUES (?, 'Manual Price Entry', ?, 0, 'Out of Stock', CURRENT_TIMESTAMP)
            """, (clean_pno, price_val))
        conn.commit()
    if is_turso_active():
        sync_to_local_sqlite("""
            INSERT INTO master_parts_lookup (part_no, erp_description, retail_price, is_pricing_pending, stock_status, last_synced)
            VALUES (?, 'Manual Price Entry', ?, 0, 'Out of Stock', CURRENT_TIMESTAMP)
            ON CONFLICT(part_no) DO UPDATE SET retail_price=excluded.retail_price, is_pricing_pending=0, last_synced=CURRENT_TIMESTAMP
        """, [(clean_pno, price_val)])
    return True

def get_missing_price_parts_df() -> pd.DataFrame:
    """
    Returns dataframe of all parts where pricing is pending for CSV download.
    """
    init_estimator_schema()
    with get_connection() as conn:
        sql = """
            SELECT 
                c.part_no,
                c.part_description,
                c.board_type,
                COUNT(DISTINCT c.model) AS models_count,
                SUM(c.historical_frequency) AS total_frequency,
                COALESCE(p.retail_price, 0) AS current_price,
                COALESCE(p.stock_status, 'Out of Stock') AS stock_status
            FROM model_part_catalog c
            LEFT JOIN master_parts_lookup p ON c.part_no = p.part_no
            WHERE p.is_pricing_pending = 1 OR p.retail_price IS NULL OR p.retail_price = 0
            GROUP BY c.part_no
            ORDER BY total_frequency DESC, models_count DESC
        """
        return pd.read_sql_query(sql, conn)

def upsert_master_parts(records: list[tuple]) -> int:
    """
    Batch inserts or replaces records into master_parts_lookup.
    """
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO master_parts_lookup (
                part_no, erp_description, erp_default_model, retail_price,
                branch_store_qty, branch_sales_qty, tech_stock_qty, total_stock_qty,
                available_branch_stock, available_total_stock, stock_status,
                tech_allocations_json, is_pricing_pending, source_document, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, records)
        conn.commit()
    if is_turso_active():
        sync_to_local_sqlite("""
            INSERT OR REPLACE INTO master_parts_lookup (
                part_no, erp_description, erp_default_model, retail_price,
                branch_store_qty, branch_sales_qty, tech_stock_qty, total_stock_qty,
                available_branch_stock, available_total_stock, stock_status,
                tech_allocations_json, is_pricing_pending, source_document, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, records)
    return len(records)

def upsert_model_catalog(records: list[tuple]) -> int:
    """
    Batch inserts or replaces records into model_part_catalog (used for baseline sync).
    """
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO model_part_catalog (
                model, part_no, part_description, board_type, historical_frequency, last_installed_date
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
    if is_turso_active():
        sync_to_local_sqlite("""
            INSERT OR REPLACE INTO model_part_catalog (
                model, part_no, part_description, board_type, historical_frequency, last_installed_date
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, records)
    return len(records)

def append_model_catalog(records: list[tuple]) -> int:
    """
    Incrementally appends daily closed complaints into model_part_catalog.
    Adds new models/parts or increments existing installation frequencies without losing baseline.
    """
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO model_part_catalog (
                model, part_no, part_description, board_type, historical_frequency, last_installed_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(model, part_no) DO UPDATE SET
                historical_frequency = model_part_catalog.historical_frequency + excluded.historical_frequency,
                last_installed_date = CASE 
                    WHEN excluded.last_installed_date != '' THEN excluded.last_installed_date 
                    ELSE model_part_catalog.last_installed_date 
                END
        """, records)
        conn.commit()
    return len(records)