# Uses network class instead of directly building dictionary
from echo.echo_builder import Network, NetworkSet, run_echo_optimiser, extract_results, extract_objectives
import pandas as pd
import numpy as np
import time as time
from pprint import pprint
import echo.configuration as ec

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

ev_params = {'charge_mode': ec.EVChargeMode.V2G.value,
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

n.add_node_to_components(n_id='grid', n_type=ec.NodeType.FlexWithEmissions, ports=['downstream', 'co2'],
                         params={'emitting_port': 'downstream',
                                 'carbon_port': 'co2',
                                 'emissions_factor': 60})

n.add_node_to_components(n_id='emissions', n_type=ec.NodeType.CarbonAggregation, ports=['grid'])
n.add_node_to_components(n_id='cp', n_type=ec.NodeType.ElectricalTellegen, ports=['upstream', 'load', 'inv', 'ev'])
n.add_node_to_components(n_id='inverter', n_type=ec.NodeType.Inverter, ports=['cp', 'bess', 'pv'], params=inverter_params)
n.add_node_to_components(n_id='battery', n_type=ec.NodeType.Battery, ports=['bess'], params=battery_params)
n.add_node_to_components(n_id='solar', n_type=ec.NodeType.Solar, ports=['pv'], data='solar', params=solar_params)
n.add_node_to_components(n_id='ev', n_type=ec.NodeType.EV, ports=['ev_cp'], params=ev_params)

# For nodes with time series data, we pass the column name of the data in the dataframe.
n.add_node_to_components(n_id='load', n_type=ec.NodeType.ElectricalLoad, ports=['load'], data='load')

# Add edges
n.add_edge_between_ports(node_tuple=('grid', 'cp'), port_tuple=('downstream', 'upstream'), resource=ec.Units.KW.value)
n.add_edge_between_ports(node_tuple=('cp', 'load'), port_tuple=('load', 'load'), resource=ec.Units.KW.value)
n.add_edge_between_ports(node_tuple=('cp', 'inverter'), port_tuple=('inv', 'cp'), resource=ec.Units.KW.value)
n.add_edge_between_ports(node_tuple=('inverter', 'battery'), port_tuple=('bess', 'bess'), resource=ec.Units.KW.value)
n.add_edge_between_ports(node_tuple=('inverter', 'solar'), port_tuple=('pv', 'pv'), resource=ec.Units.KW.value)
n.add_edge_between_ports(node_tuple=('cp', 'ev'), port_tuple=('ev', 'ev_cp'), resource=ec.Units.KW.value)
n.add_edge_between_ports(node_tuple=('grid', 'emissions'), port_tuple=('co2', 'grid'), resource=ec.Units.CO2.value)

# Define objectives

n.add_objective(name='import_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=ec.TariffType.ImportTariff.value,
                prices=[0] * (time_periods // 2) + [0] * (time_periods // 2))

n.add_objective(name='carbon_cost',
                component={'node': 'emissions', 'port': 'grid'},
                obj_type=ec.TariffType.ImportTariff.value,
                prices=[0] * time_periods)

n.add_objective(name='export_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=ec.TariffType.ExportTariff.value,
                prices=[0] * (time_periods // 2) + [0] * (time_periods // 2))

# Define some demand charges as dicts
dc1_param = {'name': 'shoulder',
             'rate': 3.,
             'window': [0] * 24 + [1] * 24}

dc2_param = {'name': 'peak',
             'rate': 5.,
             'window': [1] * 24 + [0] * 24}

n.add_objective(name='import_demand_tariff',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=ec.TariffType.ImportDemandTariff.value,
                charges=[dc1_param, dc2_param])

# Validate the network to make sure there is consistency between component naming, edge naming, objective naming.
n.validate_network()

# Convert this network to an echo model
# Returns the echo model, objective set, node_uid_dict (which is useful if nodes do not have custom names)

em, obj, node_uid_dict = n.convert_to_echo()

# Run the optimiser on the graph, using the objectives we defined
opt = run_echo_optimiser(echo_graph=em,
                         objective_set=obj,
                         interval_duration=interval_duration,
                         time_periods=time_periods,
                         expansion_periods=1,
                         discount_rate=0,
                         optimiser_engine='cplex',
                         opt_display=False)

results = extract_results(opt, node_uid_dict)

objectives_summary = extract_objectives(opt)
print('Objectives summary:\n')
pprint(objectives_summary)
