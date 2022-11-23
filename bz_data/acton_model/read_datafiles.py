import pandas as pd
from collections import defaultdict

time_periods = 24*5 ## 30 days equivalent
interval_duration = 60 ## in minutes
expansion_periods = 1
discount_rate = 0

df_multiplier = int(time_periods/5)
kambri_central = {'151': ['156', '155', '154', '153', '152', '15']}
central_plant = {'135': ['46', '48', '141', '134', '136', '137', '138', '122']}

kambri_gas_sp = 'gm_005'
central_gas_sp = '20514434'


repo_dir = '/home/anna/GitBSGIP/'
#repo_dir = '/home/anna/repos/'

# List of buildings with extra gas meters for a domestic gas supply: hot water, cooking, steam generation
extra_gas_supply = ['46', '141', '134', '136', '137', '138', '15']
bl_with_meters = pd.read_excel(f'{repo_dir}bz_data/processed_data/buildings_with_meters.xlsx',
                               dtype={'gas_meter': str,
                                      'ID': str,
                                      'substation': str})

#### Currently exluding domestic gas usage and only accounting for gas consumption for heating
bl_with_meters.loc[bl_with_meters.ID.isin(central_plant['135']), 'gas_meter'] = central_gas_sp
bl_with_meters.loc[bl_with_meters.ID.isin(kambri_central['151']), 'gas_meter'] = kambri_gas_sp

bld_to_model = set(bl_with_meters[bl_with_meters.include_in_model.isin(['Y'])].ID)


heatpump_cop = pd.read_excel(f'{repo_dir}bz_data/source_data/heatpump_cop.xlsx')

source_df = pd.DataFrame({'bl_gas_demand': [0.4, 0.5, 0.6, 1.1, 0.8]*df_multiplier,
                   'bl_el_demand_net': [7, 8, 10, 8, 11]*df_multiplier,
                   'ambient_temp': [18, 19, 19, 21, 21]*df_multiplier,
                   'bl_heating_demand': [283, 255, 264, 263, 276]*df_multiplier,
                   'bl_cooling_demand': [387.4, 437.5, 481.0, 549.1, 569.3]*df_multiplier})

source_df = source_df.merge(heatpump_cop, how='left', left_on='ambient_temp', right_on='ambient_temp')
source_df['zero_demand'] = 0.0


## Dictionaries with gas and electrical topologies

gas_supply_points_dict = dict()
for gas_meter, group in bl_with_meters[~bl_with_meters.Feeder.isnull()&
    ~bl_with_meters.gas_meter.isnull() & bl_with_meters.include_in_model.isin(['Y'])].groupby('gas_meter'):
    gas_supply_points_dict[gas_meter] = list(group.ID)

electrical_feeders = defaultdict()

for _f, group in bl_with_meters[~bl_with_meters.Feeder.isnull()&bl_with_meters.include_in_model.isin(['Y'])].groupby('Feeder'):
    feeder_subs = []
    unique_subs = list(group[~group.substation.isnull()].substation.unique())
    for _s in unique_subs:
        feeder_subs.extend(str(_s).split(','))
    electrical_feeders[_f] = list(set(feeder_subs))

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
    bl_substations[_bl] = list(set(bl_subs))


bl_gas_sp = defaultdict(list)
for k,v in gas_supply_points_dict.items():
    for bl_id in v:
        bl_gas_sp[bl_id].append(k)



substations_bl = defaultdict(list)
for k,v in bl_substations.items():
    for _sub in v:
        substations_bl[_sub].append(k)


substations_feeders = defaultdict(list)
for k,v in electrical_feeders.items():
    for _sub in v:
        substations_feeders[_sub].append(k)


