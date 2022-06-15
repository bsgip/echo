# Uses network class instead of directly building dictionary
from echo.echo_builder import *
from pprint import pprint

time_periods = 10
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
n.add_flex_node(node_id='grid', units=Units.KW, ports=['downstream'])
n.add_tellegen_node(node_id='cp', units=Units.KW, ports=['upstream', 'load', 'solar', 'battery'])
n.add_battery_node(node_id='battery', ports=['bess'], param_dict=battery_params)
n.add_data_node(node_id='solar', node_type=NodeType.Solar, node_data='solar', units=Units.KW, ports=['pv'])
n.add_data_node(node_id='load', node_type=NodeType.Load, node_data='load', units=Units.KW, ports=['load'])
# Add all our edges
n.add_edge(node_tuple=('grid', 'cp'), port_tuple=('downstream', 'upstream'))
n.add_edge(node_tuple=('cp', 'battery'), port_tuple=('battery', 'bess'))
n.add_edge(node_tuple=('cp', 'load'), port_tuple=('load', 'load'))
n.add_edge(node_tuple=('cp', 'solar'), port_tuple=('solar', 'pv'))

pprint(n.components)
pprint(n.to_dict())
