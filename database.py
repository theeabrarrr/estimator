import os
import sqlite3
import pandas as pd
import json
import re

from contextlib import contextmanager

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dwp_service.db")

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
    finally:
        conn.close()

def search_history_records(query_str, clean_phone_str):
    init_estimator_schema()
    with get_connection() as conn:
        clean_q = query_str.strip().replace('-', '').replace(' ', '').replace('=', '').replace('"', '')
        phone_param = clean_phone_str if clean_phone_str else clean_q
        phone_no_zero = phone_param.lstrip('0') if phone_param else clean_q
        
        sql = """
            SELECT complaint_no, model, serial, customer_name, phone, technician_name,
                   complaint_type, purchase_date, complaint_date, closed_date, remarks, closed_amount
            FROM history_master
            WHERE serial LIKE ? 
               OR complaint_no LIKE ? 
               OR (phone != '' AND (phone LIKE ? OR phone LIKE ? OR phone LIKE ?))
               OR customer_name LIKE ?
            ORDER BY closed_date DESC LIMIT 30
        """
        match_df = pd.read_sql_query(sql, conn, params=(
            f"%{clean_q}%", 
            f"%{clean_q}%", 
            f"%{query_str}%",
            f"%{phone_param}%",
            f"%{phone_no_zero}%",
            f"%{query_str}%"
        ))
    return match_df

def fetch_performance_data():
    init_estimator_schema()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tech_performance_master'")
        if cursor.fetchone() is None:
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM tech_performance_master", conn)

# ============================================================================
# SPARE PARTS ESTIMATOR ENGINE SCHEMA & DATA ACCESS LAYER
# ============================================================================

_IS_INITIALIZING_SCHEMA = False

def init_estimator_schema():
    """
    Ensures history_master, tech_performance_master, model_part_catalog, master_parts_lookup, and v_model_compatible_parts exist.
    """
    global _IS_INITIALIZING_SCHEMA
    if _IS_INITIALIZING_SCHEMA:
        return
    _IS_INITIALIZING_SCHEMA = True
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. History Master Table
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
                    closed_amount INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_complaint_no ON history_master (complaint_no)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_phone ON history_master (phone)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_serial ON history_master (serial)")

            # 2. Tech Performance Master Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tech_performance_master (
                    complaint_no TEXT PRIMARY KEY,
                    technician_name TEXT,
                    status TEXT,
                    closed_date TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tech_perf_tech ON tech_performance_master (technician_name)")
            
            # 3. Model-to-Part Compatibility Table
            cursor.execute("""
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
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_model ON model_part_catalog (model)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_part_no ON model_part_catalog (part_no)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_model_freq ON model_part_catalog (model, historical_frequency DESC)")

            # 4. Master Pricing & Inventory Table
            cursor.execute("""
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
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_parts_lookup_status ON master_parts_lookup (stock_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_parts_lookup_pricing_pending ON master_parts_lookup (is_pricing_pending)")

            # 5. Real-Time Estimator View
            cursor.execute("""
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
            """)
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM model_part_catalog")
            cat_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM master_parts_lookup WHERE retail_price > 0")
            priced_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM history_master")
            hist_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM history_master WHERE phone IS NOT NULL AND phone != ''")
            valid_phone_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM tech_performance_master")
            perf_count = cursor.fetchone()[0]

        if cat_count == 0 or priced_count == 0:
            try:
                import etl
                if cat_count == 0:
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

        if perf_count == 0:
            try:
                import etl
                import config
                fb_file = getattr(config, 'DEFAULT_FB_FILE', None)
                if fb_file and os.path.exists(fb_file):
                    etl.ingest_performance_pipeline(fb_file)
            except Exception as e:
                print(f"Tech performance master init error: {e}")

        # Automatically merge verified parts from baseline parts_master if present and run cross-series enrichment
        merge_parts_master_into_catalog()
        enrich_cross_series_compatibilities()
    finally:
        _IS_INITIALIZING_SCHEMA = False

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