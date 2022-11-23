import pandas as pd

bl_meter_file ='/home/anna/GitBSGIP/bz_data/processed_data/buildings_with_meters.csv'
el_meter_mapping = '/home/anna/GitBSGIP/bz_data/source_data/Authority_Elec_meter_data/SQL_Electricity_Meter_Relationship_220905.xlsx'

bl_df = pd.read_csv(bl_meter_file, dtype={'ID': str, 'gas_meter': str})
electrical_df = pd.read_excel(el_meter_mapping , dtype={'Building Number': str, 'SubStation Number': str})

