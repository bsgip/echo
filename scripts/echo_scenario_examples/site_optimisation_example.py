"""
# Site optimisation Example
This is a netset example of defining the elements that make up a
behind the meter site and optimising the charging/discharging
 of controllable elements. These can include, battery, pv, load, and evs.

"""

"""
Define the time intervals
"""
time_periods = 96                       # the number of intervals that we wish to optimise the site over
interval_duration = 15                  # the duration of each interval (minutes)

"""
Defining the tariffs/objectives

Each tariff is a field inside the objective

Every tariff must have the following fields
- 'type': 'import_tariff', 'export_tariff', 'import_demand_tariff', 
            or 'export_demand_tariff'
- 'component': the node and port to which the tariff is applied

Additionally:
- import_tariff and export_tariff must have a price array/list
- the demand tariffs have 'charges' field which contains a list of dictionaries,
    with each dictionary specifying a 'name', a 'rate' and the 'window' which 
    is a binary array indicating when the demand tariff is applied



"""
import numpy as np

objective = {
    'import_tariff': {
        'type': 'import_tariff',
        'prices': np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12)),
        'component': {'node': 'cp', 'port': 'cp'}
    },
    'export_tariff': {
        'type': 'export_tariff',
        'prices': np.array(([0.1] * 96)),
        'component': {'node': 'cp', 'port': 'cp'}
    },
    'demand_tariff': {'type': 'import_demand_tariff',
                      'component': {'node': 'elec_cp',
                                    'port': 'upstream'},
                      'charges': [
                          {'name': 'shoulder',
                           'rate': 1.,
                           'window': [0]*36 + [1]*32 + [0]*12 + [1]*8 + [0]*8
                           },
                          {'name': 'peak',
                           'rate': 2.,
                           'window': [0]*28 + [1]*8 + [0]*32 + [1]*12 + [0]*16
                           },
                      ]
                      }
}

"""
# Define a load profile and pv profile for the site
These are defined as arrays of length time_periods. If there is no pv at the site then set pv_profile=None. 
PV profile values should be negative as negative is exports. Values are in kW.
"""

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


"""
# Battery parameters
The battery parameters are defined as a dictionary with the following fields:
- max_capacity: maximum capacity of the battery in (kWh)
- depth_of_discharge_limit: percentage minimum charge allowed (0-100)
- charging_power_limit: max charging power (kW)
- dicharging_power_limit: maximum rate of discharge back to the grid (kW)
- charging_efficiency: efficiency of charging (0-1.)
- discharging_efficiency: efficiency of discharging (0-1.)
- initial_state_of_charge: initial charge (kWh)
"""

battery = {'max_capacity': 15., 'depth_of_discharge_limit':0,
            'charging_power_limit':1.25, 'discharging_power_limit':-1.25,
           'charging_efficiency':1., 'discharging_efficiency':1.,
           'initial_state_of_charge':0}


"""
define import/export constraints
"""
site_max_import_array = 23.*np.ones(load_profile.shape)

"""
# Define parameters of EVs at the site
EVs at a site are given by a list of dictionaries. Each dictionary defines a single EV. If there are no EVs at a site then set evs=None or evs=[]. The dictionary for each EV has teh following fields:
- name: name of the ev (each ev at a site should have a unique name, important for how results are appended)
- available: a bool array of length time_steps with true when the EV is at the site and available to charge
- usage: an array containing the power used (kW) during each interval when the EV is away on a trip (i.e. not available)
- max_capacity: maximum capacity of the EV battery (h)
- depth_of_discharge_limit: percentage minimum charge allowed (0-100)
- charging_power_limit: max charging power from the grid  (kW)
- dicharging_power_limit: maximum rate of discharge back to the grid (kW)
- charging_efficiency: efficiency of charging (0-1.)
- discharging_efficiency: efficiency of discharging (0-1.)
- initial_state_of_charge: initial charge (kWh)
- charge_mode: (optional, default=V2G) choose between V0G, V1G, V2G. If V1G then the discharge power limit should be 0
- tod_charging: (optional parameter for V0G charge_mode), this implements a time of day charging protacol. It is a bool array of length time_steps with True at times the ev is permitted to charge.
- soc_conserv: (optional parameter for V1G/V2G) state of charge that a conservative user would like the battery to be above while plugged in (kWh).
- soc_conserv_cost: (optional parameter needed if conserv_soc is used) perceived cost (dolalrs per kwh) for going below the conservative soc limit (not this is not an actual cost incurred by user).

"""

"""
Define a V2G EV
"""
available1 = np.array([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24)        # binary for when its available to charge
usage1 = np.array([0.0] * 24 + [0.5] * 24 + [0.0] * 24 + [1.0] * 24)    # energy usage on trip at each time period
# first vehicle is V2G
ev1 = {'name':'ev1','available': available1, 'usage': usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1,'initial_state_of_charge':20.0, 'charge_mode':'V2G',
       'soc_conserv':20, 'soc_conserv_cost':10}

"""
Define a V1G EV
"""
# Create vehicle 2
available2 = np.array([1] * 10 + [0] * 10 + [1] * 28 + [0] * 48)
usage2 = np.array([0.0] * 10 + [0.4] * 10 + [0.0] * 28 + [0.5] * 48)

# second vehicle is V1G
ev2 = {'name':'ev2','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-0., 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode':'V1G'}

"""
Define a V0G convenienced charged EV
"""
ev3 = {'name':'ev3','available': available1, 'usage': 20*usage1, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G'}

"""
Define a time of day charging ev
"""
tod_charging = np.ones(available2.shape)
tod_charging[20:30] = 0.            # we dont want to charge in the 20-30 time intervals
ev4 = {'name':'ev4','available': available2, 'usage': usage2, 'max_capacity': 40., 'depth_of_discharge_limit':0,
       'charging_power_limit':10., 'discharging_power_limit':-10, 'charging_efficiency':1,
       'discharging_efficiency':1, 'initial_state_of_charge':0.0, 'charge_mode': 'V0G', 'tod_charging':tod_charging}

evs = [ev1, ev2, ev3, ev4]

"""
Create a netset object of class NetworkSet from echo_builder.
 The description string is used to keep details such as percentages of DER.
"""

import echo.echo_builder as eb

description = 'single BTM site example'
netset = eb.NetworkSet(name='default_name', description=description)


"""
Fill in the components and edges using the parameters we defined earlier
"""

components = {}
edges = {}

# First add a component representing conection to upstream grid
components['grid'] = {'id': 'grid', 'type': 'flex', 'units': 'kW', 'ports': ['downstream']}

# create connection point to which all assets attach
components['cp'] = {'id': 'cp', 'type': 'tellegen', 'units': 'kW', 'ports': ['cp','battery', 'solar', 'load'],
                    'parameters': {'cp': {'max_import': site_max_import_array, 'max_export': None, 'slack': True}}}

edges['grid_cp'] = {'nodes': ('grid', 'cp'), 'ports': ('downstream', 'cp'), 'res': 'elec'}

# add battery component
components['battery'] = {'id': 'battery', 'type': 'battery', 'ports': ['battery'], 'parameters': battery}

edges['bess_cp'] = {'nodes': ('battery', 'cp'), 'ports': ('battery', 'battery'), 'res': 'elec'}

# add solar pv
components['solar'] = {'id': 'solar', 'type': 'solar', 'ports': ['solar'], 'data': pv_profile,
                       'parameters': {'curtailable': False}}

edges['solar_cp'] = {'nodes': ('solar', 'cp'), 'ports': ('solar', 'solar'), 'res': 'elec'}

# add load profile
components['load'] = {'id': 'load', 'type': 'load', 'units': 'kW', 'ports': ['load'], 'data': load_profile}

# define the edge
edges['load_cp'] = {'nodes': ('load', 'cp'), 'ports': ('load', 'load'), 'res': 'elec'}

# add evs

for ev in evs:
    components[ev['name']] = {'id': ev['name'], 'type': 'ev', 'ports': ['ev_cp'], 'parameters': ev}
    components['cp']['ports'].append(ev['name'])
    edges[ev['name'] + '_cp'] = {'nodes': (ev['name'], 'cp'), 'ports': ('ev_cp', ev['name']), 'res': 'elec'}


site = {'name':'btm_site',
        'components':components,
        'edges':edges,
        'objective':objective
        }

"""
Add site to netset
"""
netset.add_networks_from_list([site])

netset.interval_duration = interval_duration
netset.time_periods = time_periods

"""
Optimise
"""
processing_errors = netset.optimise_network_set()
