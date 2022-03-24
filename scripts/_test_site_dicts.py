
import numpy as np

import matplotlib.pyplot as plt
from echo_optimiser import EchoOptimiser
from pyomo.util.infeasible import log_infeasible_constraints
import seaborn as sns
import pickle
import time
import echo_scenario as ecs

pv_percent = 0.2                    # percentage of sites with PV (0-1)
bat_percent = 0.1                   # percentage of sites with battery (0-1)
ev_percent = 0.1                   # percentage of sites with evs (0-1)
ev_mean = 2                         # mean number of evs per site

description = 'test austnet_a scenario with {}% pv, {}% batteries, {}% evs'.format(pv_percent*100, bat_percent*100, ev_percent*100)

network_file = '../data/ausnet_a.json'
scenario = ecs.EchoScenario(network_file='../data/ausnet_a.json',name='test_scenario', description=description)
con_point_df = scenario.get_connection_point_info()

num_sites = len(con_point_df)       # 1 site per connected load in original data file

# how many evs we want at sites that have evs
num_evs = 1 + np.random.poisson(ev_mean-1, (num_sites,))
plt.hist(num_evs, bins=30)
plt.show()

## DEFINE SOME DUMMY VALUES TO ASSIGN TO SITES
## define load to be used in testing
days = 7
load_profile = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 2.05, 2.19] * days)

# test pv generation values
pv_profile = -1 * np.array(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
     0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
     3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
     5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] * days)

# define battery
battery = {'max_capacity': 15., 'depth_of_discharge_limit': 0,
           'charging_power_limit': 1.25, 'discharging_power_limit': -1.25,
           'charging_efficiency': 1., 'discharging_efficiency': 1.,
           'initial_state_of_charge': 0}

available1 = np.array(([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24) * days)  # binary for when its available to charge
usage1 = np.array(([0.0] * 24 + [0.5] * 24 + [0.0] * 24 + [1.0] * 24) * days)  # energy usage on trip at each time period
# first vehicle is V2G
ev1 = {'name': 'ev1', 'available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit': 0,
       'charging_power_limit': 10., 'discharging_power_limit': -10, 'charging_efficiency': 1,
       'discharging_efficiency': 1, 'initial_state_of_charge': 0.0}

# Create vehicle 2
available2 = np.array(([1] * 10 + [0] * 10 + [1] * 28 + [0] * 48) * days)
usage2 = np.array(([0.0] * 10 + [0.4] * 10 + [0.0] * 28 + [0.5] * 48) * days)

# second vehicle is V1G
ev2 = {'name': 'ev2', 'available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit': 0,
       'charging_power_limit': 10., 'discharging_power_limit': 0, 'charging_efficiency': 1,
       'discharging_efficiency': 1, 'initial_state_of_charge': 0.0}


ev3 = {'name':'ev3','available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G'}


tod_charging = np.ones(available2.shape)
tod_charging[20:30] = 0.            # we dont want to charge in the 20-30 time intervals
ev4 = {'name':'ev4','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G', 'tod_charging':tod_charging}

import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12) * days)
export_tariff_array = np.array(([0.1] * 96) * days)


has_battery = np.random.rand(num_sites,) > (1 - bat_percent)
has_solar = np.random.rand(num_sites,) > (1 - pv_percent)
has_ev = np.random.rand(num_sites,) > (1 - ev_percent)
num_evs = has_ev.astype(int) * np.random.poisson(ev_mean, (num_sites,))
names = con_point_df.id.to_numpy()
# for i, r in con_point_df.iterrows():

sites = []
for i, r in con_point_df.iterrows():
    b = battery.copy() if has_battery[i] else None
    pv = pv_profile * (0.5 + np.random.rand()) if has_solar[i] else None    # random scale applied to pv load
    l = load_profile * (0.5 + np.random.rand())        # random scale between 0.5 and 1.5 applied to load
    if has_ev[i]:
        evs =[]
        for k in range(num_evs[i]):
            which_ev = np.random.rand()
            if which_ev > 0.75:
                tmp = ev1.copy()
                tmp['name'] = tmp['name'] + '_' + str(k)        # todo: a less hacky way of ensuring names arent the same
                evs.append(tmp)
            elif which_ev > 0.5:
                tmp = ev2.copy()
                tmp['name'] = tmp['name'] + '_' + str(k)
                evs.append(tmp)
            elif which_ev > 0.25:
                tmp = ev3.copy()
                tmp['name'] = tmp['name'] + '_' + str(k)
                evs.append(tmp)
            else:
                tmp = ev4.copy()
                tmp['name'] = tmp['name'] + '_' + str(k)
                evs.append(tmp)
    else:
        evs = None

    # define the site
    site = {'name': names[i], 'load_profile': l,
                    'pv_profile': pv, 'battery': b,
                    'evs': evs, 'export_tariff': export_tariff_array,
                    'import_tariff': import_tariff_array}

    # add teh site to the list of sites
    sites.append(site)

# add all the site data to the scenario
scenario.add_site_data(sites)




## optimise scenario sites
time_periods= len(load_profile)                # number of time intervals
interval_duration = 15                           #  (mins)


t1 = time.time()
processing_errors = scenario.optimise_sites(time_periods, interval_duration)
t2 = time.time()
print('\n')
print('Time to optimise all sites for {} intervals of {} minutes was {} minutes'.format(time_periods, interval_duration,np.round((t2-t1)/60),1))
print('Number of sites failed to be processed was ',np.array(processing_errors).sum())
# saving and loading example


# for i in range(num_timesteps):
#     for load in variable_loads:
#         network.zips().set_s_const(load.time_series[i])
#     network.solve_power_flow()
#
#     for bus in network.buses():
#         store_some_data(bus.v())