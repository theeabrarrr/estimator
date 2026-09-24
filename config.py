# config.py
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "dwp_service.db")
DEFAULT_FB_FILE = os.path.join(BASE_DIR, "quality_feedback_report_14SEP2026_170840.csv")
DEFAULT_COLL_FILE = os.path.join(BASE_DIR, "Detail_Collection_14SEP26_052528PM.xlsx")
STOCK_SEARCH_DIRS = [BASE_DIR, ".", r"C:\temp", "/tmp"]

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

# Standard Service Overheads per Category
CATEGORY_OVERHEADS = {
    'Split AC': {
        'visit': 600,
        'mobility': 2000,
        'has_gas': True,
        'label': 'Split AC'
    },
    'Floor Standing AC': {
        'visit': 600,
        'mobility': 2500,
        'has_gas': True,
        'label': 'Floor Standing AC'
    },
    'Refrigerator': {
        'visit': 600,
        'mobility': 1500,
        'has_gas': True,
        'gas_default': 3500,
        'label': 'Refrigerator'
    },
    'Washing Machine': {
        'visit': 600,
        'mobility': 1500,
        'has_gas': False,
        'label': 'Washing Machine'
    },
    'Water Dispenser': {
        'visit': 600,
        'mobility': 1200,
        'has_gas': True,
        'gas_default': 2500,
        'label': 'Water Dispenser'
    },
    'LED TV': {
        'visit': 600,
        'mobility': 1500,
        'has_gas': False,
        'label': 'LED TV'
    },
    'Microwave Oven': {
        'visit': 600,
        'mobility': 1000,
        'has_gas': False,
        'label': 'Microwave Oven'
    },
    'General': {
        'visit': 600,
        'mobility': 1500,
        'has_gas': False,
        'label': 'General Appliance'
    }
}

def detect_appliance_category(model_str):
    m = str(model_str).upper()
    if any(k in m for k in ['GR-', 'REF-', 'REFRIGERATOR']):
        return 'Refrigerator'
    elif any(k in m for k in ['EW-', 'WM-', 'WASHING', 'SPIN']):
        return 'Washing Machine'
    elif any(k in m for k in ['GW-', 'WD-', 'DISPENSER']):
        return 'Water Dispenser'
    elif any(k in m for k in ['CX-', 'U57', 'U87', 'UD96', 'QD8', 'LED', 'TV']):
        return 'LED TV'
    elif any(k in m for k in ['EM-', 'MW-', 'OVEN', 'MICROWAVE']):
        return 'Microwave Oven'
    elif any(k in m for k in ['GF-', 'FLOOR', 'STANDING']):
        return 'Floor Standing AC'
    elif any(k in m for k in ['GS-', 'ES-', 'SPLIT', 'T3', 'PITH', 'PIT']):
        return 'Split AC'
    return 'Split AC' if ('-' in m and any(char.isdigit() for char in m)) else 'General'

def get_tonnage_specs(model_str):
    m = str(model_str).upper()
    cat = detect_appliance_category(m)
    
    if cat in ['Washing Machine', 'LED TV', 'Microwave Oven']:
        return 'Standard Unit', 0, 0, 0, cat
        
    if cat == 'Refrigerator':
        return 'Domestic Ref', 3500, 0, 8000, cat
    elif cat == 'Water Dispenser':
        return 'Dispenser', 2500, 0, 4000, cat

    if cat == 'Floor Standing AC' or any(x in m for x in ['48', '60', '36', '36TFIH', 'TFIH']):
        return '4.0 Ton', 13000, 70000, 55000, cat
    elif any(x in m for x in ['24', '26']):
        return '2.0 Ton', 8500, 39000, 45000, cat
    elif any(x in m for x in ['18', '16']):
        return '1.5 Ton', 7000, 26000, 40000, cat
    elif any(x in m for x in ['12', '11']) or re.search(r'[^0-9]10[^0-9]', m):
        return '1.0 Ton', 5500, 20000, 35000, cat
        
    return '1.5 Ton', 7000, 26000, 40000, cat