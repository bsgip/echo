import json
import sys
import pandas as pd
import numpy as np
import sgt
import sgt_e_json
import matplotlib.pyplot as plt
## echo and optimisation imports
import echo_models as ecm
from echo_optimiser import EchoOptimiser
import objectives as obj
from pyomo.util.infeasible import log_infeasible_constraints
import seaborn as sns
import pickle
import time

import echo_scenario as ecs

network_file = '../data/ausnet_a.json'
con_point_df = ecs.get_connection_point_info(network_file)

num_sites = len(con_point_df)       # 1 site per connected load in original data file

pv_percent = 0.2                    # percentage of sites with PV
bat_percent = 0.1                   # percentage of sites with battery
ev_percent = 0.1                   # percentage of sites with evs
ev_mean = 2                         # mean number of evs per site

num_evs = np.random.poisson(ev_mean, (1000,))
plt.hist(num_evs, bins=30)

## DEFINE SOME DUMMY VALUES TO ASSIGN TO SITES
## define load to be used in testing
rep = 7

test_load = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 2.05, 2.19] * rep)

# test pv generation values
test_pv = np.array(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
     0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
     3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
     5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] * rep)
test_pv *= -1  # convert solar generation to negative to match convention.

# define battery
battery = {'max_capacity': 15., 'depth_of_discharge_limit': 0,
           'charging_power_limit': 1.25, 'discharging_power_limit': -1.25,
           'charging_efficiency': 1., 'discharging_efficiency': 1.,
           'initial_state_of_charge': 0}

available1 = np.array(([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24) * rep)  # binary for when its available to charge
usage1 = np.array(([0.0] * 24 + [0.5] * 24 + [0.0] * 24 + [1.0] * 24) * rep)  # energy usage on trip at each time period
# first vehicle is V2G
ev1 = {'name': 'ev1', 'available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit': 0,
       'charging_power_limit': 10., 'discharging_power_limit': -10, 'charging_efficiency': 1,
       'discharging_efficiency': 1, 'initial_state_of_charge': 0.0}

# Create vehicle 2
available2 = np.array(([1] * 10 + [0] * 10 + [1] * 28 + [0] * 48) * rep)
usage2 = np.array(([0.0] * 10 + [0.4] * 10 + [0.0] * 28 + [0.5] * 48) * rep)

# second vehicle is V1G
ev2 = {'name': 'ev2', 'available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit': 0,
       'charging_power_limit': 10., 'discharging_power_limit': 0, 'charging_efficiency': 1,
       'discharging_efficiency': 1, 'initial_state_of_charge': 0.0}

import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12) * rep)
export_tariff_array = np.array(([0.1] * 96) * rep)

# test_site_3_dict = {'name': 'test_site_3', 'load_profile': test_load,
#                     'pv_profile': test_pv, 'battery': battery,
#                     'evs': evs, 'export_tariff': export_tariff_array,
#                     'import_tariff': import_tariff_array}

## put together all the site dictionaries


has_battery = np.random.rand(num_sites,) > (1 - bat_percent)
has_solar = np.random.rand(num_sites,) > (1 - pv_percent)
has_ev = np.random.rand(num_sites,) > (1 - ev_percent)
num_evs = has_ev.astype(int) * np.random.poisson(ev_mean, (num_sites,))
names = con_point_df.id.to_numpy()
# for i, r in con_point_df.iterrows():

sites = []
for i, r in con_point_df.iterrows():
    b = battery if has_battery[i] else None
    pv = test_pv if has_solar[i] else None
    l = test_load
    if has_ev[i]:
        evs =[]
        for k in range(num_evs[i]):
            if np.random.rand() > 0.5:
                tmp = ev1.copy()
                tmp['name'] = tmp['name'] + '_' + str(k)        # todo: a less hacky way of ensuring names arent the same
                evs.append(ev1)
            else:
                tmp = ev1.copy()
                tmp['name'] = tmp['name'] + '_' + str(k)
                evs.append(tmp)
    else:
        evs = None
    site = {'name': names[i], 'load_profile': l,
                    'pv_profile': pv, 'battery': b,
                    'evs': evs, 'export_tariff': export_tariff_array,
                    'import_tariff': import_tariff_array}
    sites.append(site)

scenario = {'name':'test_scenario', 'network':'ausnet_a',
            'num_sites':num_sites, 'ev_percent':ev_percent,
            'battery_percent':bat_percent, 'pv_percent':pv_percent,
            'sites':sites, 'interval_duration':15, 'time_periods':4*24*rep}

# test saving and loading as a dict
t1 = time.time()
with open('../data/test_scenario.pickle', 'wb') as handle:
    pickle.dump(scenario, handle, protocol=pickle.HIGHEST_PROTOCOL)
t2 = time.time()
print('Time to save as pickle was ',t2-t1)

t1 = time.time()
with open('../data/test_scenario.pickle', 'rb') as handle:
    tmp = pickle.load(handle)
t2 = time.time()
print('Time to load as pickle was ',t2-t1)


## optimise scenario sites
num_sites = scenario['num_sites']
count = 0
t1 = time.time()
for i in range(100):
    site_dict = scenario['sites'][i]
    if (site_dict['battery'] is not None) or (site_dict['evs'] is not None):      # then there is an asset to optimise
        ecs.create_site_from_dict(site_dict)
        ### create a test site with 1 battery, pv, and 2 evs
        echo_site, objective_set, node_uid_dict = ecs.create_site_from_dict(site_dict)

        # Invoke the optimiser and optimise
        optimiser = EchoOptimiser(interval_duration=scenario['interval_duration'],
                                    number_of_intervals=scenario['time_periods'],
                                    number_of_expansion_intervals=1,
                                    discount_rate=0,
                                    ES=echo_site,
                                    objective_set=objective_set, optimiser_engine='cplex')

        optimiser.optimise()

        log_infeasible_constraints(optimiser.model)

        aggregate_load, battery_res, evs_res = ecs.extract_site_results(optimiser, echo_site, node_uid_dict)

        site_dict['aggregate_load'] = aggregate_load
        if battery_res is not None:
            site_dict['battery']['SOC'] = battery_res['SOC']
            site_dict['battery']['delta'] = battery_res['delta']
        if len(evs_res) > 0:
            for j, ev_res in enumerate(evs_res):
                site_dict['evs'][j]['SOC'] = ev_res['SOC']
                site_dict['evs'][j]['delta'] = ev_res['delta']
        count += 1
    else:
        if site_dict['pv_profile'] is not None:
            site_dict['aggregate_load'] = site_dict['pv_profile'] + site_dict['load_profile']
        else:
            site_dict['aggregate_load'] = site_dict['load_profile']

    scenario['sites'][i] = site_dict

t2 = time.time()
print('\n')
print('Time to optimise {} sites was {}'.format(count,t2-t1))