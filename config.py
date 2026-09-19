# config.py
import re

DB_NAME = "dwp_service.db"
DEFAULT_FB_FILE = "quality_feedback_report_14SEP2026_170840.csv"
DEFAULT_COLL_FILE = "Detail_Collection_14SEP26_052528PM.xlsx"

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
    'ITEM_DESC': 'model',
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

def get_tonnage_specs(model_str):
    m = str(model_str).upper()
    if any(x in m for x in ['48', '60', '36', '36TFIH', 'TFIH']):
        return '4.0 Ton', 13000, 70000, 55000
    elif any(x in m for x in ['24', '26']):
        return '2.0 Ton', 8500, 39000, 45000
    elif any(x in m for x in ['18', '16']):
        return '1.5 Ton', 7000, 26000, 40000
    elif any(x in m for x in ['12', '11']) or re.search(r'[^0-9]10[^0-9]', m):
        return '1.0 Ton', 5500, 20000, 35000
    return '1.5 Ton', 7000, 26000, 40000