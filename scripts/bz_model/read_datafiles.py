import pandas as pd



kambri_central = {'151': ['156-1', '156-2', '155', '154', '153', '152', '15']}
central_plant = {'135': ['46', '48', '141', '134', '136', '137', '138', '122']}

# List of buildings with extra gas meters for a domestic gas supply: hot water, cooking, steam generation
extra_gas_supply = ['46', '141', '134', '136', '137', '138', '15']
bl_with_meters = pd.read_excel('/home/anna/GitBSGIP/bz_data/processed_data/buildings_with_meters.xlsx', dtype={'gas_meter': str,
                                                                                                               'ID': str,
                                                                                                               'substation': str})






heatpump_cop = pd.read_csv('/home/anna/GitBSGIP/bz_data/source_data/heatpump_cop.csv')

source_df = pd.DataFrame({'bl_gas_demand': [0.4, 0.5, 0.6, 1.1, 0.8],
                   'bl_el_demand_net': [7, 8, 10, 8, 11],
                   'ambient_temp': [18, 19, 19, 21, 21],
                   'bl_heating_demand': [283, 255, 264, 263, 276],
                   'bl_cooling_demand': [387.4, 437.5, 481.0, 549.1, 569.3]})

source_df = source_df.merge(heatpump_cop, how='left', left_on='ambient_temp', right_on='ambient_temp')


