# Uses network class instead of directly building dictionary
from echo.echo_builder import *

time_periods = 48
interval_duration = 60
# define dummy dataframe to hold our time series data
df = pd.DataFrame({
    'load': [5] * time_periods,
    'solar': [-2] * time_periods,
    'ev_available': [1] * 12 + [0] * 12 + [1] * 12 + [0] * 12,
    'ev_usage': [0.0] * 12 + [0.5] * 12 + [0.0] * 12 + [1.0] * 12
})
battery_params = {'max_capacity': 15.,
                  'depth_of_discharge_limit': 0,
                  'charging_power_limit': 1.25,
                  'discharging_power_limit': -1.25,
                  'charging_efficiency': 1.,
                  'discharging_efficiency': 1.,
                  'initial_state_of_charge': 0}
inverter_params = {'ac_port_name': 'cp',
                   'dc_port_names': ['bess', 'pv']}

# V2G vehicle
ev_params = {'available': 'ev_available',
             'usage': [0.0] * 12 + [0.5] * 12 + [0.0] * 12 + [1.0] * 12,
             'max_capacity': 40.,
             'depth_of_discharge_limit': 0,
             'charging_power_limit': 10.,
             'discharging_power_limit': -10,
             'charging_efficiency': 1,
             'discharging_efficiency': 1,
             'initial_state_of_charge': 0.0,
             'charge_mode': EVChargeMode.V2G,
             'interval_duration': interval_duration,
             'tod_charging': False}

# initialise a network
n = Network(name='my network')
# add all our components (nodes)

# n.add_node_to_components(n_id='grid', n_type=NodeType.ElectricalFlex, ports=['downstream'])

n.add_node_to_components(n_id='grid', n_type=NodeType.FlexWithEmissions, ports=['downstream', 'co2'],
                         params={'emitting_port': 'downstream',
                                 'carbon_port': 'co2',
                                 'emissions_factor': 60})

n.add_node_to_components(n_id='emissions', n_type=NodeType.CarbonAggregation, ports=['grid'])

n.add_node_to_components(n_id='cp', n_type=NodeType.ElectricalTellegen, ports=['upstream', 'load', 'inv', 'ev'])

n.add_node_to_components(n_id='inverter', n_type=NodeType.Inverter, ports=['cp', 'bess', 'pv'], params=inverter_params)

n.add_node_to_components(n_id='battery', n_type=NodeType.Battery, ports=['bess'], params=battery_params)

n.add_node_to_components(n_id='solar', n_type=NodeType.Solar, ports=['pv'], data='solar')

n.add_node_to_components(n_id='load', n_type=NodeType.ElectricalLoad, ports=['load'], data='load')

n.add_node_to_components(n_id='ev', n_type=NodeType.EV, ports=['ev_cp'], params=ev_params)

# Add all our edges
n.add_edge_between_ports(node_tuple=('grid', 'cp'), port_tuple=('downstream', 'upstream'), resource=Units.KW)

n.add_edge_between_ports(node_tuple=('cp', 'load'), port_tuple=('load', 'load'), resource=Units.KW)

n.add_edge_between_ports(node_tuple=('cp', 'inverter'), port_tuple=('inv', 'cp'), resource=Units.KW)

n.add_edge_between_ports(node_tuple=('inverter', 'battery'), port_tuple=('bess', 'bess'), resource=Units.KW)

n.add_edge_between_ports(node_tuple=('inverter', 'solar'), port_tuple=('pv', 'pv'), resource=Units.KW)

n.add_edge_between_ports(node_tuple=('cp', 'ev'), port_tuple=('ev', 'ev_cp'), resource=Units.KW)

n.add_edge_between_ports(node_tuple=('grid', 'emissions'), port_tuple=('co2', 'grid'), resource=Units.CO2)

### Define some objective

n.add_objective(obj_name='import_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ImportTariff,
                prices=[1] * (time_periods // 2) + [2] * (time_periods // 2))

n.add_objective(obj_name='carbon_cost',
                component={'node': 'emissions', 'port': 'grid'},
                obj_type=TariffType.ImportTariff,
                prices=[0.0] * time_periods)

n.add_objective(obj_name='export_cost',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ExportTariff,
                prices=[0.1] * (time_periods // 2) + [3] * (time_periods // 2))

dc1_param = {'name': 'shoulder',
             'rate': 0.,
             'window': [0] * 24 + [1] * 24}

dc2_param = {'name': 'peak',
             'rate': 0.,
             'window': [1] * 24 + [0] * 24}

n.add_objective(obj_name='import_demand_tariff',
                component={'node': 'cp', 'port': 'upstream'},
                obj_type=TariffType.ImportDemandTariff,
                charges=[dc1_param, dc2_param])

n.validate_network()

##### Doing things manually with just the network dict

em, obj, node_uid_dict = convert_network_to_echo(n, df)  # convert directly to echo from network class.

opt = run_echo_optimiser(echo_graph=em,
                         objective_set=obj,
                         interval_duration=interval_duration,
                         time_periods=time_periods,
                         expansion_periods=1,
                         discount_rate=0,
                         optimiser_engine='cplex',
                         opt_display=False)

results = extract_results(opt, node_uid_dict)

ha = extract_objectives(opt)
print(ha)

### Doing things using netsets
netset = NetworkSet(name='default_name', description='this is a bad description')
netset.add_network(n.dict())  # netset is expecting a dict
netset.interval_duration = interval_duration
netset.time_periods = time_periods
num_sites = 1
netset.df = df

t1 = time.time()
processing_errors = netset.optimise_network_set()
t2 = time.time()
print('\n')
print('Time to optimise all sites for {} intervals of {} minutes was {} minutes'.format(time_periods, interval_duration,
                                                                                        np.round((t2 - t1) / 60), 1))
print('Number of sites failed to be processed was ', np.array(processing_errors).sum(), '/', num_sites)

netset.to_df('cp', 'upstream')
