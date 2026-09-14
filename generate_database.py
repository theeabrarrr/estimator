import pandas as pd
import numpy as np

def build_estimator_database(fb_file, coll_file, output_file="Estimator_Database_Master.xlsx"):
    print("[1/5] Loading ERP files...")
    fb = pd.read_csv(fb_file, low_memory=False)
    coll = pd.read_excel(coll_file)

    # Clean Complaint Numbers & Model Names
    fb['COMPLAINT_NO_CLEAN'] = fb['COMPLAINT_NO'].astype(str).str.replace('=', '').str.replace('"', '').str.strip()
    coll['COMPLAINT_NO_CLEAN'] = coll['Complaint No'].astype(str).str.replace('=', '').str.replace('"', '').str.strip()

    fb['MODEL_NAME_CLEAN'] = fb['MODEL_NAME'].astype(str).str.strip().str.upper()
    coll['MODEL_NAME_CLEAN'] = coll['Model Name'].astype(str).str.strip().str.upper()

    print("[2/5] Extracting Model-to-Part compatibility pairs...")
    records = []
    for _, row in fb.iterrows():
        pnos = str(row['HARDWARE_PART_NOS'])
        prods = str(row['HARDWARE_PRODUCTS'])
        qtys = str(row['HARDWARE_QTYS'])
        model = row['MODEL_NAME_CLEAN']
        category = str(row['CATEGORY']).strip() if pd.notna(row['CATEGORY']) else ""
        brand = str(row['BRAND_NAME']).strip() if pd.notna(row['BRAND_NAME']) else ""
        c_no = row['COMPLAINT_NO_CLEAN']

        if pd.isna(row['HARDWARE_PART_NOS']) or pnos.lower() == 'nan' or pnos.strip() == '':
            continue

        pno_list = [p.strip() for p in pnos.split(',') if p.strip()]
        prod_list = [p.strip() for p in prods.split(',') if p.strip()]
        qty_list = [q.strip() for q in qtys.split(',') if q.strip()]

        for i, pno in enumerate(pno_list):
            pname = prod_list[i] if i < len(prod_list) else prod_list[0] if prod_list else "Unknown Part"
            qty = 1.0
            if i < len(qty_list):
                try:
                    qty = float(qty_list[i])
                except:
                    qty = 1.0
            
            records.append({
                'COMPLAINT_NO_CLEAN': c_no,
                'MODEL_NAME': model,
                'BRAND': brand,
                'CATEGORY': category,
                'PART_NO': pno,
                'PART_NAME': pname,
                'QTY': qty,
                'TOTAL_PARTS_IN_JOB': len(pno_list)
            })

    parts_df = pd.DataFrame(records)

    print("[3/5] Merging with Detail Collection to extract cash pricing...")
    coll_part_cash = coll[['COMPLAINT_NO_CLEAN', 'Part Cash', 'Gas Charges Cash', 'Service Cash']].copy()
    merged = pd.merge(parts_df, coll_part_cash, on='COMPLAINT_NO_CLEAN', how='left')

    # Benchmark pricing from single-part cash jobs
    single_part_cash = merged[(merged['TOTAL_PARTS_IN_JOB'] == 1) & (merged['Part Cash'] > 0)].copy()
    single_part_cash['UNIT_PRICE'] = single_part_cash['Part Cash'] / single_part_cash['QTY']

    def get_mode(x):
        m = x.mode()
        return m.iloc[0] if not m.empty else x.median()

    price_stats = single_part_cash.groupby('PART_NO')['UNIT_PRICE'].agg(
        BENCHMARK_PRICE=get_mode,
        MEDIAN_PRICE='median',
        CASH_JOB_COUNT='count'
    ).reset_index()

    parts_master = parts_df.groupby('PART_NO').agg(
        PART_NAME=('PART_NAME', 'first'),
        OCCURRENCE_COUNT=('MODEL_NAME', 'count')
    ).reset_index()

    parts_master = pd.merge(parts_master, price_stats, on='PART_NO', how='left')
    parts_master['BENCHMARK_PRICE'] = parts_master['BENCHMARK_PRICE'].fillna(0).astype(int)
    parts_master['CASH_JOB_COUNT'] = parts_master['CASH_JOB_COUNT'].fillna(0).astype(int)
    parts_master = parts_master.sort_values(by='OCCURRENCE_COUNT', ascending=False)

    print("[4/5] Building Model-Part Compatibility Bridge...")
    bridge = parts_df[['MODEL_NAME', 'PART_NO', 'PART_NAME']].drop_duplicates()
    bridge = pd.merge(bridge, parts_master[['PART_NO', 'BENCHMARK_PRICE']], on='PART_NO', how='left')

    models_master = parts_df.groupby('MODEL_NAME').agg(
        BRAND=('BRAND', 'first'),
        CATEGORY=('CATEGORY', 'first'),
        TOTAL_REPAIRS=('COMPLAINT_NO_CLEAN', 'nunique')
    ).reset_index().sort_values('TOTAL_REPAIRS', ascending=False)

    print(f"[5/5] Exporting clean sheets to {output_file}...")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        bridge.to_excel(writer, sheet_name='Model_Part_Bridge', index=False)
        parts_master.to_excel(writer, sheet_name='Parts_Master', index=False)
        models_master.to_excel(writer, sheet_name='Models_Master', index=False)

    print("SUCCESS: Database generated successfully!")

if __name__ == "__main__":
    build_estimator_database(
        fb_file='quality_feedback_report_14SEP2026_170840.csv',
        coll_file='Detail_Collection_14SEP26_052528PM.xlsx',
        output_file='Estimator_Database_Master.xlsx'
    )