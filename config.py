# config.py
from __future__ import annotations
import re
import os
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "dwp_service.db")

def find_latest_feedback_file():
    candidates = []
    for pattern in ["quality_feedback_report_*.csv", "*feedback*.csv"]:
        for f in glob.glob(os.path.join(BASE_DIR, pattern)):
            candidates.append((os.path.getmtime(f), f))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return os.path.join(BASE_DIR, "quality_feedback_report_28SEP2026_142900.csv")

def find_latest_collection_file():
    candidates = []
    for pattern in ["Detail_Collection_*.xlsx", "*Collection*.xlsx", "*collection*.xlsx"]:
        for f in glob.glob(os.path.join(BASE_DIR, pattern)):
            if not os.path.basename(f).startswith('~$'):
                candidates.append((os.path.getmtime(f), f))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return os.path.join(BASE_DIR, "Detail_Collection_28SEP26_023634PM.xlsx")

DEFAULT_FB_FILE = find_latest_feedback_file()
DEFAULT_COLL_FILE = find_latest_collection_file()

def find_latest_stock_pdf():
    for f in ["vp786.pdf", "vp786 (1 year stock movement report).pdf"]:
        p = os.path.join(BASE_DIR, f)
        if os.path.exists(p):
            return p
    return os.path.join(BASE_DIR, "vp786.pdf")

DEFAULT_STOCK_PDF = find_latest_stock_pdf()

VISIT_CHARGES = 600
MOBILITY_CHARGES = 2000
VALVE_BYPASS_CHARGES = 1500
AC_SERVICE_CHARGES = 3500
BASE_FIXED_TOTAL = VISIT_CHARGES + MOBILITY_CHARGES

# Capacity-Aware Gas Charging Engine Rates (PKR)
GAS_CHARGES_MAP = {
    '12K': 5500,   # AC 12000 BTU (1.0 Ton)
    '18K': 7000,   # AC 18000 BTU (1.5 Ton)
    '24K': 8500,   # AC 24000 BTU (2.0 Ton)
    '36K': 13000,  # AC 36000 BTU (3.0 Ton)
    '48K': 13000,  # AC 48000 BTU (4.0 Ton)
    'REF': 4000,   # Refrigerator (Model starts with 'GR-')
    'WD': 3500,    # Water Dispenser (Model starts with 'WD-')
    'DEFAULT': 5500
}

def calculate_gas_charge(model_name: str) -> tuple[int, str]:
    """
    Auto-determine gas refill charge (PKR) and capacity description based on model name.
    """
    if not model_name:
        return GAS_CHARGES_MAP['DEFAULT'], "Standard AC Gas (1.0 Ton)"
    
    m = str(model_name).upper().strip()
    if m.startswith('GR-'):
        return GAS_CHARGES_MAP['REF'], "Refrigerator Gas Refill (R-600a)"
    if m.startswith('WD-') or m.startswith('GW-'):
        return GAS_CHARGES_MAP['WD'], "Water Dispenser Gas Refill (R-134a)"
    
    if any(k in m for k in ['48', '48000', '4.0 TON', '4 TON']):
        return GAS_CHARGES_MAP['48K'], "Commercial AC Gas Refill (4.0 Ton / 48000 BTU)"
    if any(k in m for k in ['36', '36000', '3.0 TON', '3 TON']):
        return GAS_CHARGES_MAP['36K'], "Commercial AC Gas Refill (3.0 Ton / 36000 BTU)"
    if any(k in m for k in ['24', '24000', '2.0 TON', '2 TON']):
        return GAS_CHARGES_MAP['24K'], "Split AC Gas Refill (2.0 Ton / 24000 BTU)"
    if any(k in m for k in ['18', '18000', '1.5 TON']):
        return GAS_CHARGES_MAP['18K'], "Split AC Gas Refill (1.5 Ton / 18000 BTU)"
    if any(k in m for k in ['12', '12000', '1.0 TON', '1 TON']):
        return GAS_CHARGES_MAP['12K'], "Split AC Gas Refill (1.0 Ton / 12000 BTU)"
        
    return GAS_CHARGES_MAP['DEFAULT'], "Split AC Gas Refill (Standard 1.0 Ton)"

def calculate_gas_charge_amount(model_name: str) -> int:
    return calculate_gas_charge(model_name)[0]

COLUMN_ALIASES = {
    'COMPLAINT NO': 'complaint_no',
    'COMPLAINT_NO': 'complaint_no',
    'C_NO': 'complaint_no',
    'SERIAL': 'serial',
    'SERIAL_NO': 'serial',
    'SERIAL NO': 'serial',
    'PHONE_NO': 'phone',
    'PHONE': 'phone',
    'MOBILE': 'phone',
    'CONTACT': 'phone',
    'MODEL_NAME': 'model',
    'MODEL': 'model',
    'ITEM_DESC': 'item_desc',
    'ITEM DESC': 'item_desc',
    'PART_NO': 'part_no',
    'PART NO': 'part_no',
    'PART_NUMBER': 'part_no',
    'ITEM_CODE': 'item_code',
    'ITEM CODE': 'item_code',
    'BAL_QTY': 'bal_qty',
    'BAL QTY': 'bal_qty',
    'BALANCE_QTY': 'bal_qty',
    'BALANCE QTY': 'bal_qty',
    'AMOUNT': 'amount',
    'OPEN_QTY': 'open_qty',
    'RECEIVED_QTY': 'received_qty',
    'ISSUE_QTY': 'issue_qty',
    'UOM': 'uom',
    'PRODUCT': 'product',
    'BRAND': 'brand',
    'BRAND_NAME': 'brand',
    'CATEGORY': 'category',
    'CAPACITY': 'capacity',
    'CUSTOMER_NAME': 'customer_name',
    'TECHNICIAN_NAME': 'technician_name',
    'COMPLAINT_TYPE': 'complaint_type',
    'PURCHASE_DATE': 'purchase_date',
    'COMPLAINT_DATE': 'complaint_date',
    'CLOSED_DATE': 'closed_date',
    'COMPLETE_DATE': 'complete_date',
    'FEEDBACK_REMARKS': 'remarks',
    'REMARKS': 'remarks',
    'CLOSING_REMARKS': 'remarks',
    'NET COLLECTION': 'net_collection',
    'NET_COLLECTION': 'net_collection',
    'PART CASH': 'part_cash',
    'PART WARRANTY': 'part_warranty',
    'HARDWARE_PART_NOS': 'part_nos',
    'HARDWARE_PRODUCTS': 'products',
    'STATUS': 'status',
    'COMPLETED_STATUS': 'status'
}


COMPONENT_ROLE_GROUPS = [
    ("❄️ Evaporator Assemblies", ["Evaporator Assembly"]),
    ("⚡ Outdoor Inverter PCBs", ["Outdoor Inverter PCB"]),
    ("🔌 Indoor Main PCBs", ["Indoor Main PCB"]),
    ("⚡ Circuit Boards (Other)", ["Circuit Board (PCB)"]),
    ("🔄 Compressors & Fittings", ["Compressor & Fittings"]),
    ("💨 Fan Motors (Indoor & Outdoor)", ["Indoor Fan Motor", "Outdoor Fan Motor", "Fan Motor"]),
    ("🔄 Stepping & Swing Motors", ["Stepping / Swing Motor"]),
    ("🔩 Cut-off & Service Valves", ["Cut-Off Valve (1/2\")", "Cut-Off Valve (3/8\")", "Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")", "Service Valve"]),
    ("🔀 4-Way Valve Assemblies", ["4-Way Valve Assembly"]),
    ("🌡️ Temperature Sensors", ["Temperature Sensor"]),
    ("🔋 Capacitors", ["Capacitor"]),
    ("📺 LED TV Modules", ["LED TV Module"]),
    ("⚙️ Gear Boxes & Drives", ["Gear Box"]),
    ("📦 Hardware & Components", ["Component Hardware", "Remote Control"])
]

def classify_component_role(part_name, part_no=""):
    nl = (str(part_name) + " " + str(part_no)).lower()
    
    # Exclude non-functional packaging, cartons, trays, and supports from cooling/electrical roles
    if any(k in nl for k in ['carton', 'caton', 'packing', 'tray', 'support', 'bracket', 'foam', 'box', 'panel', 'cover']):
        return "Component Hardware"
        
    if any(k in nl for k in ['evap', 'evaporator', 'indoor coil']):
        return "Evaporator Assembly"
    elif any(k in nl for k in ['outdoor pcb', 'pcb odu', 'odu pcb', 'inverter board', 'outdoor board', 'pcb outdoor', '300027', '11222031']):
        return "Outdoor Inverter PCB"
    elif any(k in nl for k in ['indoor main board', 'main board indoor', 'pcb idu', 'indoor pcb', 'pcb indoor', 'display board', '300002', '300001']):
        return "Indoor Main PCB"
    elif any(k in nl for k in ['pcb', 'board', 'circuit']):
        return "Circuit Board (PCB)"
    elif any(k in nl for k in ['compressor']):
        return "Compressor & Fittings"
    elif any(k in nl for k in ['step motor', 'stepping motor', 'swing motor', 'mp24', '1521212', '1521210']):
        return "Stepping / Swing Motor"
    elif any(k in nl for k in ['indoor motor', 'fan motor indoor', 'motor idu', 'cross flow motor']):
        return "Indoor Fan Motor"
    elif any(k in nl for k in ['outdoor motor', 'fan motor outdoor', 'motor odu', 'propeller motor']):
        return "Outdoor Fan Motor"
    elif any(k in nl for k in ['motor']):
        return "Fan Motor"
    elif any(k in nl for k in ['4-way', '4 way', 'reversing valve']):
        return "4-Way Valve Assembly"
    # Strict Valve Sizing Classification (Historical closed complaints are canonical ground truth)
    elif (any(k in nl for k in ['3/8', 'three eighth']) and 'valve' in nl) or any(p in nl for p in ['71302395', '7133474']):
        return "Cut-Off Valve (3/8\")"
    elif (any(k in nl for k in ['5/8', 'five eighth']) and 'valve' in nl) or any(p in nl for p in ['7133844', '7135142']):
        return "Cut-Off Valve (5/8\")"
    elif (any(k in nl for k in ['1/2', 'half']) and 'valve' in nl) or any(p in nl for p in ['7133774', '11225517000085']):
        return "Cut-Off Valve (1/2\")"
    elif (any(k in nl for k in ['1/4', 'quarter']) and 'valve' in nl) or any(p in nl for p in ['7130239', '71302392', '71302393', '71302391', '30057000074']):
        return "Cut-Off Valve (1/4\")"
    elif any(k in nl for k in ['valve']):
        return "Service Valve"
    elif any(k in nl for k in ['sensor', 'temp sensor', 'thermistor', 'probe', 'ambient sensor', 'tube sensor']):
        return "Temperature Sensor"
    elif any(k in nl for k in ['capacitor', 'cap 50uf', 'cap 35uf', 'cap 60uf', 'cbb65']):
        return "Capacitor"
    elif any(k in nl for k in ['remote', 'controller']):
        return "Remote Control"
    elif any(k in nl for k in ['gear box', 'gearbox']):
        return "Gear Box"
    elif any(k in nl for k in ['t-con', 'glassboard', 'light bar', 'speaker', 'led panel']):
        return "LED TV Module"
    return "Component Hardware"


FLOOR_STANDING_CAPACITIES = {
    '60': '5.0 Ton', '5TON': '5.0 Ton',
    '48': '4.0 Ton', '4TON': '4.0 Ton',
    '36': '3.0 Ton', '3TON': '3.0 Ton',
    '24': '2.0 Ton', '26': '2.0 Ton', '2TON': '2.0 Ton'
}

SPLIT_AC_CAPACITIES = {
    '60': '5.0 Ton',
    '48': '4.0 Ton',
    '36': '3.0 Ton',
    '24': '2.0 Ton', '26': '2.0 Ton',
    '18': '1.5 Ton', '16': '1.5 Ton',
    '12': '1.0 Ton', '11': '1.0 Ton', '10': '1.0 Ton'
}

FLOOR_STANDING_SERIES = ['TFIH', 'FWITH', 'VTIH', 'TF', 'FW', 'ISH', 'CD', 'CB', 'IPH', 'PITH', 'CITH']
SPLIT_AC_SERIES = ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'FWITH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'ISH', 'FW', 'TF', 'CD', 'CB']

def tokenize_appliance_model(model_str):

    m = str(model_str).strip().replace('=', '').replace('"', '').upper()
    
    brand = "Gree" if m.startswith(('GS-', 'GR-', 'GF-', 'GW-')) else ("EcoStar" if m.startswith(('ES-', 'EW-', 'CX-', 'EM-')) else "Other")
    cat = "Split AC"
    ton = "1.5 Ton"
    series = "STANDARD"
    
    if any(k in m for k in ['GR-', 'REF-', 'REFRIGERATOR']):
        cat = "Refrigerator"
        ton = "Domestic Ref"
        series = "REF"
    elif any(k in m for k in ['EW-', 'WM-', 'WASHING', 'SPIN']):
        cat = "Washing Machine"
        ton = "Standard Unit"
        series = "WM"
    elif any(k in m for k in ['GW-', 'WD-', 'DISPENSER']):
        cat = "Water Dispenser"
        ton = "Dispenser"
        series = "WD"
    elif any(k in m for k in ['CX-', 'U57', 'U87', 'UD96', 'QD8', 'LED', 'TV']):
        cat = "LED TV"
        ton = "Standard Unit"
        series = "LED"
    elif any(k in m for k in ['EM-', 'MW-', 'OVEN', 'MICROWAVE']):
        cat = "Microwave Oven"
        ton = "Standard Unit"
        series = "MW"
    elif m.startswith(('GF-', 'EF-')) or any(k in m for k in ['FLOOR', 'STANDING']):
        cat = "Floor Standing AC"
        # Determine Floor Standing Capacity
        ton = next((v for k, v in FLOOR_STANDING_CAPACITIES.items() if k in m), "3.0 Ton")
            
        # Determine Floor Standing Series
        series = next((s for s in FLOOR_STANDING_SERIES if s in m), "FLOOR")
    else:
        cat = "Split AC"
        cap_match = re.search(r'-(10|11|12|16|18|24|26|36|48|60)', m)
        if cap_match:
            ton = SPLIT_AC_CAPACITIES.get(cap_match.group(1), "1.5 Ton")
            
        # Strict Platform Series Tokenizer
        series = next((s for s in SPLIT_AC_SERIES if s in m), series)
                
    return {
        'model': m,
        'brand': brand,
        'category': cat,
        'tonnage': ton,
        'series': series,
        'series_key': f"{brand}|{cat}|{ton}|{series}"
    }


def is_valve_tonnage_compatible(role, part_name, target_tonnage, target_cat="Split AC"):
    """
    Validates physical line pairing and tonnage compatibility for Refrigerant Cut-Off & Service Valves.
    Strict pairing standards based on empirical closed complaint history:
      - 1.0 Ton: Strictly 1/4" (Liquid) + 3/8" (Suction Gas). Reject 1/2" and 5/8".
      - 1.5 Ton: Strictly 1/4" (Liquid) + 1/2" (Suction Gas). Reject 3/8" and 5/8".
      - 2.0 Ton: Strictly 1/4" (Liquid) + 5/8" (Suction Gas). Reject 3/8" and 1/2".
      - 3.0 Ton: Strictly 1/4" (Liquid) + 5/8" (Suction Gas). Reject 3/8" and 1/2".
      - 4.0 Ton: Strictly 3/8" (Liquid) + 5/8" (Suction Gas). Reject 1/4" and 1/2".
    """
    if target_cat not in ['Split AC', 'Floor Standing AC', 'Air Conditioner']:
        return True
        
    valve_roles = [
        "Cut-Off Valve (1/4\")", "Cut-Off Valve (3/8\")", 
        "Cut-Off Valve (1/2\")", "Cut-Off Valve (5/8\")", 
        "Cut-Off Valve (3/8\" - 5/8\")", "Service Valve"
    ]
    if role not in valve_roles and 'valve' not in str(part_name).lower():
        return True
        
    if role == "4-Way Valve Assembly" or any(k in str(part_name).lower() for k in ['4-way', '4 way', 'reversing']):
        return True

    pn = str(part_name).lower()
    
    size_1_4 = (role == "Cut-Off Valve (1/4\")") or ('1/4' in pn) or ('quarter' in pn) or ('7130239' in pn and '71302395' not in pn)
    size_3_8 = (role == "Cut-Off Valve (3/8\")") or ('3/8' in pn) or ('71302395' in pn) or ('7133474' in pn)
    size_1_2 = (role == "Cut-Off Valve (1/2\")") or ('1/2' in pn) or ('half' in pn) or ('7133774' in pn)
    size_5_8 = (role == "Cut-Off Valve (5/8\")") or ('5/8' in pn) or ('7133844' in pn) or ('7135142' in pn)
    
    if target_tonnage == '1.0 Ton':
        if size_1_2 or size_5_8:
            return False
        if size_1_4 or size_3_8:
            return True
        return True
        
    elif target_tonnage == '1.5 Ton':
        if size_3_8 or size_5_8:
            return False
        if size_1_4 or size_1_2:
            return True
        return True
        
    elif target_tonnage in ['2.0 Ton', '3.0 Ton']:
        if size_3_8 or size_1_2:
            return False
        if size_1_4 or size_5_8:
            return True
        return True
        
    elif target_tonnage in ['4.0 Ton', '5.0 Ton']:
        if size_1_4 or size_1_2:
            return False
        if size_3_8 or size_5_8:
            return True
        return True
        
    return True

def get_tonnage_valve_pairing(target_tonnage):
    """
    Returns the tuple of (suction_role, liquid_role) for a given tonnage:
      - 1.0 Ton: ("Cut-Off Valve (3/8\")", "Cut-Off Valve (1/4\")")
      - 1.5 Ton: ("Cut-Off Valve (1/2\")", "Cut-Off Valve (1/4\")")
      - 2.0 Ton: ("Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")")
      - 3.0 Ton: ("Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")")
      - 4.0 Ton / 5.0 Ton: ("Cut-Off Valve (5/8\")", "Cut-Off Valve (3/8\")")
    """
    if target_tonnage == '1.0 Ton':
        return "Cut-Off Valve (3/8\")", "Cut-Off Valve (1/4\")"
    elif target_tonnage == '1.5 Ton':
        return "Cut-Off Valve (1/2\")", "Cut-Off Valve (1/4\")"
    elif target_tonnage in ['2.0 Ton', '3.0 Ton']:
        return "Cut-Off Valve (5/8\")", "Cut-Off Valve (1/4\")"
    elif target_tonnage in ['4.0 Ton', '5.0 Ton']:
        return "Cut-Off Valve (5/8\")", "Cut-Off Valve (3/8\")"
    return "Cut-Off Valve (1/2\")", "Cut-Off Valve (1/4\")"


