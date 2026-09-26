# config.py
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "dwp_service.db")
DEFAULT_FB_FILE = os.path.join(BASE_DIR, "quality_feedback_report_14SEP2026_170840.csv")
DEFAULT_COLL_FILE = os.path.join(BASE_DIR, "Detail_Collection_14SEP26_052528PM.xlsx")
STOCK_SEARCH_DIRS = [os.path.join(BASE_DIR, "data"), BASE_DIR, ".", r"C:\temp", "/tmp"]

VISIT_CHARGES = 600
MOBILITY_CHARGES = 2000

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

BASELINE_JSON_PATH = os.path.join(BASE_DIR, "data", "ground_truth_baseline.json")
STOCK_CSV_PATH = os.path.join(BASE_DIR, "data", "stock_inventory_latest.csv")

# Standard Service Overheads per Category
CATEGORY_OVERHEADS = {
    'Split AC': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': True,
        'gas_name': 'Refrigerant Gas',
        'label': 'Split AC'
    },
    'Floor Standing AC': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': True,
        'gas_name': 'Commercial Refrigerant Gas',
        'gas_default': 13000,
        'label': 'Floor Standing AC'
    },
    'Refrigerator': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': True,
        'gas_name': 'R-600 Gas',
        'gas_default': 4000,
        'label': 'Refrigerator'
    },
    'Washing Machine': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': False,
        'label': 'Washing Machine'
    },
    'Water Dispenser': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': True,
        'gas_name': 'R-134a Gas',
        'gas_default': 3500,
        'label': 'Water Dispenser'
    },
    'LED TV': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': False,
        'label': 'LED TV'
    },
    'Microwave Oven': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': False,
        'label': 'Microwave Oven'
    },
    'General': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': False,
        'label': 'General Appliance'
    }
}

COMPONENT_ROLE_GROUPS = [
    ("❄️ Evaporator Assemblies", ["Evaporator Assembly"]),
    ("⚡ Outdoor Inverter PCBs", ["Outdoor Inverter PCB"]),
    ("🔌 Indoor Main PCBs", ["Indoor Main PCB"]),
    ("⚡ Circuit Boards (Other)", ["Circuit Board (PCB)"]),
    ("🔄 Compressors & Fittings", ["Compressor & Fittings"]),
    ("💨 Fan Motors (Indoor & Outdoor)", ["Indoor Fan Motor", "Outdoor Fan Motor", "Fan Motor"]),
    ("🔄 Stepping & Swing Motors", ["Stepping / Swing Motor"]),
    ("🔩 Cut-off & Service Valves", ["Cut-Off Valve (1/4\")", "Cut-Off Valve (1/2\")", "Cut-Off Valve (3/8\" - 5/8\")", "Service Valve"]),
    ("🔀 4-Way Valve Assemblies", ["4-Way Valve Assembly"]),
    ("🌡️ Temperature Sensors", ["Temperature Sensor"]),
    ("🔋 Capacitors", ["Capacitor"]),
    ("📺 LED TV Modules", ["LED TV Module"]),
    ("⚙️ Gear Boxes & Drives", ["Gear Box"]),
    ("📦 Hardware & Components", ["Component Hardware", "Remote Control"])
]

def classify_component_role(part_name, part_no=""):
    nl = (str(part_name) + " " + str(part_no)).lower()
    
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
    elif any(k in nl for k in ['1/4', 'quarter']) and 'valve' in nl:
        return "Cut-Off Valve (1/4\")"
    elif any(k in nl for k in ['1/2', 'half']) and 'valve' in nl:
        return "Cut-Off Valve (1/2\")"
    elif any(k in nl for k in ['3/8', '5/8']) and 'valve' in nl:
        return "Cut-Off Valve (3/8\" - 5/8\")"
    elif any(k in nl for k in ['4-way', '4 way', 'reversing valve']):
        return "4-Way Valve Assembly"
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
    elif any(k in m for k in ['GF-', 'FLOOR', 'STANDING']) or any(x in m for x in ['48', '60', '36', '36TFIH', 'TFIH']):
        cat = "Floor Standing AC"
        ton = "4.0 Ton"
        series = "FLOOR"
    else:
        cat = "Split AC"
        cap_match = re.search(r'-(10|11|12|16|18|24|26|36|48|60)', m)
        if cap_match:
            cv = cap_match.group(1)
            if cv in ['48', '60', '36']:
                ton = "4.0 Ton"
            elif cv in ['24', '26']:
                ton = "2.0 Ton"
            elif cv in ['18', '16']:
                ton = "1.5 Ton"
            elif cv in ['12', '11', '10']:
                ton = "1.0 Ton"
            
        # Strict Platform Series Tokenizer
        for s in ['PITH', 'CITH', 'FITH', 'AITH', 'VITH', 'LITH', 'ZITH', 'VTIH', 'UITH', 'TFIH', 'PIT', 'CIT', 'CM', 'LM', 'ECH', 'DU', 'EM', 'CZ', 'AR', 'PR', 'NV', 'GL', 'IB', 'TF', 'CD', 'CB']:
            if s in m:
                series = s
                break
                
    return {
        'model': m,
        'brand': brand,
        'category': cat,
        'tonnage': ton,
        'series': series,
        'series_key': f"{brand}|{cat}|{ton}|{series}"
    }

def detect_appliance_category(model_str):
    return tokenize_appliance_model(model_str)['category']

def get_tonnage_specs(model_str):
    tok = tokenize_appliance_model(model_str)
    cat = tok['category']
    ton = tok['tonnage']
    
    if cat in ['Washing Machine', 'LED TV', 'Microwave Oven']:
        return 'Standard Unit', 0, 0, 0, cat
        
    if cat == 'Refrigerator':
        return 'Domestic Ref', 4000, 0, 8000, cat
    elif cat == 'Water Dispenser':
        return 'Dispenser', 3500, 0, 4000, cat

    if cat == 'Floor Standing AC' or ton == '4.0 Ton':
        return '4.0 Ton', 13000, 70000, 55000, cat
    elif ton == '2.0 Ton':
        return '2.0 Ton', 8500, 39000, 45000, cat
    elif ton == '1.5 Ton':
        return '1.5 Ton', 7000, 26000, 40000, cat
    elif ton == '1.0 Ton':
        return '1.0 Ton', 5500, 20000, 35000, cat
        
    return '1.5 Ton', 7000, 26000, 40000, cat
