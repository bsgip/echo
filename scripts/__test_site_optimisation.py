time_periods = 96                       # the number of intervals that we wish to optimise the site over
interval_duration = 15                  # the duration of each interval (minutes)

import numpy as np

import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff_array = np.array(([0.1] * 96))

load_profile = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 2.05, 2.19])

pv_profile = -1*np.array(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
     0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
     3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
     5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

# if no pv then do pv_profile=None

battery = {'max_capacity': 15., 'depth_of_discharge_limit':0,
            'charging_power_limit':1.25, 'discharging_power_limit':-1.25,
           'charging_efficiency':1., 'discharging_efficiency':1.,
           'initial_state_of_charge':0}

available1 = np.array([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24)        # binary for when its available to charge
usage1 = np.array([0.0] * 24 + [0.5] * 24 + [0.0] * 24 + [1.0] * 24)    # energy usage on trip at each time period
# first vehicle is V2G
ev1 = {'name':'ev1','available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1,'initial_state_of_charge':0.0, 'charge_mode':'V2G'}

# Create vehicle 2
available2 = np.array([1] * 10 + [0] * 10 + [1] * 28 + [0] * 48)
usage2 = np.array([0.0] * 10 + [0.4] * 10 + [0.0] * 28 + [0.5] * 48)

# second vehicle is V1G
ev2 = {'name':'ev2','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-0., 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode':'V1G'}

ev3 = {'name':'ev3','available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G'}

tod_charging = np.ones(available2.shape)
tod_charging[20:30] = 0.            # we dont want to charge in the 20-30 time intervals
ev4 = {'name':'ev4','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G', 'tod_charging':tod_charging}

evs = [ev1, ev2, ev3, ev4]
# if no evs at site then do
# evs=None

# site_max_import_array = 23*np.ones(load_profile.shape)
site_max_import_array = 20*np.ones(load_profile.shape)
# site_max_import_array = None

site_dict = {'name':'test_site', 'load_profile':load_profile,
                    'pv_profile':pv_profile, 'battery':battery,
                    'evs':evs, 'export_tariff':export_tariff_array,
                     'import_tariff':import_tariff_array,
                    'site_max_import':site_max_import_array, 'site_max_export':-20}

from echo_scenario import process_site
site_dict = process_site(site_dict, interval_duration, time_periods)

from echo_scenario import retrieve_value

print('Pyomo optimisation status is:')
print(retrieve_value(site_dict,'opt_status'))

## Check for any import export constraint violation
export_violation = site_dict['export_violation']
import_violation = site_dict['import_violation']

print('Maximum import violation was {} kW'.format(import_violation.max()))
print('Maximum export violation was {} kW \n'.format(export_violation.min()))


for i in range(4):
    print('EV ' + site_dict['evs'][i]['name']+':')
    if retrieve_value(site_dict['evs'][i], 'charge_mode') == 'V0G':
        str = ' with time of day' if retrieve_value(site_dict['evs'][i], 'tod_charging') is not None else ' with convenience'
    else:
        str = ''
    print('\t Specified charging method was '+ retrieve_value(site_dict['evs'][i], 'charge_mode') + str)
    print('\t Charging status was: ' + retrieve_value(site_dict['evs'][i], 'charge_status'))
    print('\n')

import matplotlib.pyplot as plt
import seaborn as sns

aggregate_load = site_dict['aggregate_load']    # the combined load on the grid from the site


battery_power = site_dict['battery']['delta']       # battery power
battery_soc = site_dict['battery']['SOC']           # battery state of charge

ev1_soc = site_dict['evs'][0]['SOC']
ev1_power = site_dict['evs'][0]['delta']

ev2_soc = site_dict['evs'][1]['SOC']
ev2_power = site_dict['evs'][1]['delta']

ev3_soc = site_dict['evs'][2]['SOC']
ev3_power = site_dict['evs'][2]['delta']

ev4_soc = site_dict['evs'][3]['SOC']
ev4_power = site_dict['evs'][3]['delta']



colors = sns.color_palette()
hrs = np.arange(0, len(load_profile)) / 4

plt.subplot(2,1,1)
plt.plot(hrs, load_profile, label='load')
plt.plot(hrs, pv_profile, label='pv')
plt.title('Site PV and Load')
plt.legend()

plt.subplot(2,1,2)
plt.plot(hrs, battery_soc, label='state of charge')
plt.plot(hrs, battery_power, label='power')
plt.title('battery')
plt.legend()

plt.tight_layout()
plt.show()

plt.subplot(3,1,1)
for i in range(4):
    plt.plot(hrs, site_dict['evs'][i]['SOC'], label=site_dict['evs'][i]['charge_mode'] + ' EV')
plt.title('EV state of charges')
plt.legend()

plt.subplot(3,1,2)
for i in range(4):
    if (site_dict['evs'][i]['charge_mode'] == 'V0G') and (retrieve_value(site_dict['evs'][i],'tod_charging') is not None):
        plt.plot(hrs, site_dict['evs'][i]['delta'], label=site_dict['evs'][i]['charge_mode'] + ' TOD EV')
    else:
        plt.plot(hrs, site_dict['evs'][i]['delta'], label=site_dict['evs'][i]['charge_mode'] + ' EV')
plt.title('EV power')
plt.legend()

plt.subplot(3,1,3)
plt.plot(hrs, aggregate_load, label='aggregate_load')
plt.legend()
plt.title('Aggregate load')

plt.tight_layout()
plt.show()
