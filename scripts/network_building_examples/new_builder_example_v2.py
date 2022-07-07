# Uses network class instead of directly building dictionary
from echo.echo_builder import *
from pprint import pprint

time_periods = 24
interval_duration = 60
# define dummy dataframe to hold our time series data
df = pd.DataFrame({
    'load': [5] * time_periods,
    'solar': [-2] * time_periods,
})
battery_params = {'max_capacity': 15., 'depth_of_discharge_limit': 0,
                  'charging_power_limit': 1.25, 'discharging_power_limit': -1.25,
                  'charging_efficiency': 1., 'discharging_efficiency': 1.,
                  'initial_state_of_charge': 0}

# initialise a network
n = Network()
# add all our components (nodes)
n.add_node_to_components(n_id='grid', n_type=NodeType.Flex, ports={'downstream': {'units': Units.KW}})
n.add_node_to_components(n_id='cp', n_type=NodeType.Tellegen,
                         ports=dict.fromkeys(['upstream', 'load', 'solar', 'battery'], {'units': Units.KW}))
n.add_node_to_components(n_id='battery', n_type=NodeType.Battery,
                         ports={'bess': {'units': Units.KW, 'parameters': battery_params}})
n.add_node_to_components(n_id='solar', n_type=NodeType.Solar, ports={'pv': {'units': Units.KW, 'data': 'solar'}})
n.add_node_to_components(n_id='load', n_type=NodeType.Load, ports={'load': {'units': Units.KW, 'data': 'load'}})
# Add all our edges
n.add_edge_between_ports(node_tuple=('grid', 'cp'), port_tuple=('downstream', 'upstream'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('cp', 'battery'), port_tuple=('battery', 'bess'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('cp', 'load'), port_tuple=('load', 'load'), resource=Units.KW)
n.add_edge_between_ports(node_tuple=('cp', 'solar'), port_tuple=('solar', 'pv'), resource=Units.KW)

# pprint(n.components)
# pprint(n.to_dict())

x = convert_dict_to_nx(netw_jsn=n.to_dict())

# Convert nx to echo
em, node_uid_dict = convert_nx_to_echo(x, df)

obj = None
opt = run_echo_optimiser(em,
                         obj,
                         interval_duration=interval_duration,
                         time_periods=time_periods,
                         expansion_periods=1,
                         discount_rate=0,
                         optimiser_engine='cplex',
                         opt_display=True)

results = extract_results(opt, node_uid_dict)
df = extract_results_as_df(opt, node_uid_dict)
# pprint(results)
# print(df)
