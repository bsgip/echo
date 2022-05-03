import pandas as pd
from echo.bz_builder import *

time_periods = 48

df = pd.DataFrame({
    'gas': [4] * time_periods,
    'load': [5] * time_periods,
    'solar': [-2] * 24 + [-1] * 24,

})

# Define an example network as a dict/json type structure

network_dict = {
    'components': {
        'bulk_grid': {
            'Node': {
                'id': 'bulk_grid',
                'cons': [],
                'ports': ['downstream']
            }
        },
        'elec_cp': {
            'Node': {
                'id': 'elec_cp',
                'cons': [],
                'ports': []
            }
        },
        'load': {
            'Node': {
                'id': 'load',
                'cons': ['elec_cp'],  # connections to other components
                'ports': ['load'],
                'data': 'load'
            }
        },
        'inverter': {
            'Node': {
                'id': 'inverter',
                'cons': [],  # connections to other components - should they go here or be defined separately as edges?
                'ports': ['ac', 'dc'],

            }
        },
        'battery': {
            'Node': {
                'id': 'battery',
                'cons': [],
                'ports': ['battery']

            }
        },
        'solar': {
            'Node': {
                'id': 'solar',
                'cons': ['elec_cp'],  # connections to other components
                'ports': ['solar'],
                'data': 'solar'
            }
        },
        'bulk_gas': {
            'Node': {
                'id': 'bulk_gas',
                'cons': [],  # connections to other components
                'ports': ['downstream']
            }
        },
        'gas_cp': {
            'Node': {
                'id': 'gas_cp',
                'cons': ['bulk_gas'],  # connections to other components
                'ports': []
            }
        },
        'gas_load': {
            'Node': {
                'id': 'gas_load',
                'cons': [],  # connections to other components - should they go here or be defined separately as edges?
                'ports': [],
                'data': 'gas_load'
            }
        }
    },
    'edges': {
        'edge_1': {'nodes': ('bulk_grid', 'elec_cp'),
                   'ports': ('downstream', None),
                   'res': 'elec'},

        'edge_2': {'nodes': ('elec_cp', 'load'),
                   'ports': (None, 'load'),
                   'res': 'elec'},

        'edge_3': {'nodes': ('elec_cp', 'inverter'),
                   'ports': (None, 'ac'),
                   'res': 'elec'},

        'edge_4': {'nodes': ('inverter', 'solar'),
                   'ports': ('dc', 'solar'),
                   'res': 'elec'},

        'edge_5': {'nodes': ('inverter', 'battery'),
                   'ports': ('dc', 'battery'),
                   'res': 'elec'},

        'edge_6': {'nodes': ('bulk_gas', 'gas_cp'),
                   'ports': ('downstream', None),
                   'res': 'gas'},

        'edge_7': {'nodes': ('gas_cp', 'gas_load'),
                   'ports': (),
                   'res': 'gas'},
    }
}
x = convert_dict_to_nx(network_dict)
check_nx_for_floating_nodes(x)
nx.draw(x, with_labels=True)

em = convert_nx_to_echo(x)

battery = {'max_capacity': 15., 'depth_of_discharge_limit':0,
            'charging_power_limit':1.25, 'discharging_power_limit':-1.25,
           'charging_efficiency':1., 'discharging_efficiency':1.,
           'initial_state_of_charge':0}
b = create_battery_node(battery)
