import pandas as pd
from collections import defaultdict



kambri_central = {'151': ['156-1', '156-2', '155', '154', '153', '152', '15']}
central_plant = {'135': ['46', '48', '141', '134', '136', '137', '138', '122']}

# List of buildings with extra gas meters for a domestic gas supply: hot water, cooking, steam generation
extra_gas_supply = ['46', '141', '134', '136', '137', '138', '15']
bl_with_meters = pd.read_excel('/home/anna/GitBSGIP/bz_data/processed_data/buildings_with_meters.xlsx', dtype={'gas_meter': str,
                                                                                                             'ID': str,
                                                                                                               'substation': str})
bld_to_model = set(bl_with_meters[bl_with_meters.include_in_model.isin(['Y'])].ID)


heatpump_cop = pd.read_csv('/home/anna/GitBSGIP/bz_data/source_data/heatpump_cop.csv')

source_df = pd.DataFrame({'bl_gas_demand': [0.4, 0.5, 0.6, 1.1, 0.8],
                   'bl_el_demand_net': [7, 8, 10, 8, 11],
                   'ambient_temp': [18, 19, 19, 21, 21],
                   'bl_heating_demand': [283, 255, 264, 263, 276],
                   'bl_cooling_demand': [387.4, 437.5, 481.0, 549.1, 569.3]})

source_df = source_df.merge(heatpump_cop, how='left', left_on='ambient_temp', right_on='ambient_temp')


## Dictionaries with gas and electrical topologies

gas_supply_points_dict = dict()
for gas_meter, group in bl_with_meters[
    ~bl_with_meters.gas_meter.isnull() & bl_with_meters.include_in_model.isin(['Y'])].groupby('gas_meter'):
    gas_supply_points_dict[gas_meter] = list(group.ID)

electrical_feeders = defaultdict()

for _f, group in bl_with_meters[~bl_with_meters.Feeder.isnull()].groupby('Feeder'):
    feeder_subs = []
    unique_subs = [_s for _s in group[~group.substation.isnull()].substation.unique() if _s != '1225,1744']
    for _s in unique_subs:
        feeder_subs.extend(str(_s).split(','))
    electrical_feeders[_f] = [sub_id for sub_id in unique_subs]

bl_substations = defaultdict()
bld_not_included = []
for _bl, group in bl_with_meters[bl_with_meters.include_in_model.isin(['Y'])].groupby('ID'):
    bl_subs = []
    unique_subs = list(group[~group.substation.isnull()].substation.unique())
    if len(unique_subs) == 0:
        bld_not_included.append(_bl)
        continue
    for _s in unique_subs:
        bl_subs.extend(str(_s).split(','))
    bl_substations[_bl] = bl_subs

substations_bl = defaultdict(list)
for k,v in bl_substations.items():
    for _sub in v:
        substations_bl[_sub].append(k)



