# Uses network class instead of directly building dictionary
from echo.echo_builder import Network, NetworkSet, run_echo_optimiser, extract_results, extract_objectives
import pandas as pd
import numpy as np
import time as time
from pprint import pprint
from echo.configuration import *

# Define our time periods and interval duration
time_periods = 48
interval_duration = 60

# Define a dataframe that holds time series data.
# We can reference columns in this dataframe when we create our assets

df = pd.DataFrame({
    'load': [5] * time_periods,
    'solar': [-2] * time_periods,
    'ev_available': [1] * 12 + [0] * 12 + [1] * 12 + [0] * 12,
    'ev_usage': [0.0] * 12 + [0.5] * 12 + [0.0] * 12 + [1.0] * 12})

# Define some parameters for our assets

battery_params = {'max_capacity': 15.,
                  'depth_of_discharge_limit': 0,
                  'charging_power_limit': 1.25,
                  'discharging_power_limit': -1.25,
                  'charging_efficiency': 1.,
                  'discharging_efficiency': 1.,
                  'initial_state_of_charge': 0}

inverter_params = {'ac_port_name': 'cp',
                   'dc_port_names': ['bess', 'pv']}

solar_params = {'curtailable': True}

ev_params = {'charge_mode': EVChargeMode.V2G,
             'available': 'ev_available',  # we can pass a reference col name instead of data
             'usage': 'ev_usage',  # we can pass a reference col name instead of data
             'max_capacity': 40.,
             'depth_of_discharge_limit': 0,
             'charging_power_limit': 10.,
             'discharging_power_limit': -10,
             'charging_efficiency': 1,
             'discharging_efficiency': 1,
             'initial_state_of_charge': 0.0,
             'interval_duration': interval_duration,
             'tod_charging': False}

# Initialise a network

n = Network(name='my network')

# Add our profile to the network

n.add_profile(profile=df)

# Add all our components (nodes)

n.add_node_to_components(n_id='grid', n_type=NodeType.FlexWithEmissions, ports=['downstream', 'co2'],
                         params={'emitting_port': 'downstream',
                                 'carbon_port': 'co2',
                                 'emissions_factor': 60})

n.add_node_to_components(n_id='emissions', n_type=NodeType.CarbonAggregation, ports=['grid'])
n.add_node_to_components(n_id='cp', n_type=NodeType.ElectricalTellegen, ports=['upstream', 'load', 'inv', 'ev'])
n.add_node_to_components(n_id='inverter', n_type=NodeType.Inverter, ports=['cp', 'bess', 'pv'], params=inverter_params)
n.add_node_to_components(n_id='battery', n_type=NodeType.Battery, ports=['bess'], params=battery_params)
n.add_node_to_components(n_id='solar', n_type=NodeType.Solar, ports=['pv'], data='solar', params=solar_params)
n.add_node_to_components(n_id='ev', n_type=NodeType.EV, ports=['ev_cp'], params=ev_params)

# For nodes with time series data, we pass the column name of the data in the dataframe.
n.add_node_to_components(n_id='load', n_type=NodeType.ElectricalLoad, ports=['load'], data='load')

# Add edges
n.add_edge_between_ports(node_tuple=('grid', 'cp'), port_tuple=('downstream', 'upstream'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('cp', 'load'), port_tuple=('load', 'load'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('cp', 'inverter'), port_tuple=('inv', 'cp'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('inverter', 'battery'), port_tuple=('bess', 'bess'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('inverter', 'solar'), port_tuple=('pv', 'pv'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('cp', 'ev'), port_tuple=('ev', 'ev_cp'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('grid', 'emissions'), port_tuple=('co2', 'grid'), resource=Units.CO2)

# Add different objectives to the different networks

n.add_objective(name='import_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ImportTariff,
                prices=[1] * (time_periods // 2) + [1] * (time_periods // 2))

n.add_objective(name='carbon_cost',
                component={'node': 'emissions', 'port': 'grid'},
                obj_type=TariffType.ImportTariff,
                prices=[0.5] * time_periods)

n.add_objective(name='export_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ExportTariff,
                prices=[0.1] * (time_periods // 2) + [3] * (time_periods // 2))

# Define some demand charges as dicts
dc1_param = {'name': 'shoulder',
             'rate': 3.,
             'window': [0] * 24 + [1] * 24}

dc2_param = {'name': 'peak',
             'rate': 5.,
             'window': [1] * 24 + [0] * 24}

n.add_objective(name='import_demand_tariff',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ImportDemandTariff,
                charges=[dc1_param, dc2_param])

# Make two other copies of our network
n1 = n.copy()
n2 = n.copy()

# Modify the objectives for these two other networks
n1.objectives = {}
n1.add_objective(name='import_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ImportTariff,
                prices=[1] * (time_periods // 2) + [2] * (time_periods // 2))

n1.add_objective(name='export_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ExportTariff,
                prices=[0.1] * (time_periods // 2) + [3] * (time_periods // 2))

n1.add_objective(name='import_demand_tariff',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ImportDemandTariff,
                charges=[dc1_param, dc2_param])


n2.objectives = {}
n2.add_objective(name='carbon_cost',
                component={'node': 'emissions', 'port': 'grid'},
                obj_type=TariffType.ImportTariff,
                prices=[0.5] * time_periods)

# Validate the networks to make sure there is consistency between component naming, edge naming, objective naming.
n.validate_network()
n1.validate_network()
n2.validate_network()

# Create a netset and add our three networks
netset = NetworkSet(name='default_name', description='')
netset.add_network(n.dict())  # netset expects dict, so convert our network class to dict
netset.add_network(n1.dict())  # netset expects dict, so convert our network class to dict
netset.add_network(n2.dict())  # netset expects dict, so convert our network class to dict

# Set interval duration
netset.interval_duration = interval_duration
netset.time_periods = time_periods
num_sites = len(netset.networks)
netset.df = df  #todo fix the need to do this

t1 = time.time()
processing_errors = netset.optimise_network_set()
t2 = time.time()
print('\n')
print('Time to optimise all sites for {} intervals of {} minutes was {} minutes'.format(time_periods, interval_duration,
                                                                                        np.round((t2 - t1) / 60), 1))
print('Number of sites failed to be processed was ', np.array(processing_errors).sum(), '/', num_sites)

# Compare total costs
print('Cost comparison:\n')
print(netset.results[0]['cost_summary'])
print(netset.results[1]['cost_summary'])
print(netset.results[2]['cost_summary'])
