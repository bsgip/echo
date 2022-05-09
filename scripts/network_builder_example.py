import pandas as pd
from echo.echo_builder import *
import numpy as np

time_periods = 48

df = pd.DataFrame({
    'load': [5] * time_periods,
})

# Define an example network as a dict/json type structure, with fully specified ports

network_dict = {
    'components': {
        'bulk_grid': {
            'Node': {
                'id': 'bulk_grid',
                'type': 'flex',
                'ports': ['downstream']
            }
        },
        'elec_cp': {
            'Node': {
                'id': 'elec_cp',
                'type': 'tellegen',
                'ports': ['upstream', 'load', 'bess', 'ev']
            }
        },
        'load': {
            'Node': {
                'id': 'load',
                'type': 'load',
                'ports': ['load'],
                'data': 'load',
                'parameters': {},
            }
        },
        'battery': {
            'Node': {
                'id': 'bess',
                'type': 'battery',
                'ports': ['bess'],
                'parameters': {'max_capacity': 15.,
                               'depth_of_discharge_limit': 0,
                               'charging_power_limit': 1.25,
                               'discharging_power_limit': -1.25,
                               'charging_efficiency': 1.,
                               'discharging_efficiency': 1.,
                               'initial_state_of_charge': 0},
                'results': {'soc_result', 'power_result', 'other'}  # echo results stored in pandas df
            }
        },
        'ev1': {
            'Node': {
                'id': 'ev1',
                'type': 'ev',
                'ports': ['ev_cp'],
                'parameters': {'available': np.array([1] * 24 + [0] * 24),
                               'usage': np.array([0.0] * 24 + [0.1] * 24),
                               'max_capacity': 40.,
                               'depth_of_discharge_limit': 0,
                               'charging_power_limit': 10.,
                               'discharging_power_limit': -10.,
                               'charging_efficiency': 1.,
                               'discharging_efficiency': 1.,
                               'initial_state_of_charge': 20.,
                               'charge_mode': 'V0G',
                               'soc_conserv': None,
                               'soc_conserv_cost': 0.,
                               'enable_trip_slack': True,
                               'interval_duration': 30.}  #todo another way to carry this info, we need it for building EVs tho
            }
        }
    },
    'edges': {
        'edge_1': {'nodes': ('bulk_grid', 'elec_cp'),
                   'ports': ('downstream', 'upstream'),
                   'res': 'elec'},

        'edge_2': {'nodes': ('elec_cp', 'load'),
                   'ports': ('load', 'load'),
                   'res': 'elec'},

        'edge_3': {'nodes': ('elec_cp', 'battery'),
                   'ports': ('bess', 'bess'),
                   'res': 'elec'},

        'edge_4': {'nodes': ('elec_cp', 'ev1'),
                   'ports': ('ev', 'ev_cp'),
                   'res': 'elec'},

    }
}


objective_dict = {
    'import_tariff': {'type': 'import_tariff',
                      'prices': [0]*48,
                      'component': {'node': 'elec_cp',
                                    'port': 'upstream'}
                      },
    'demand_tariff': {'type': 'import_demand_tariff',
                      'component': {'node': 'elec_cp',
                                    'port': 'upstream'},
                      'charges': [
                          {'name': 'shoulder',
                           'rate': 2.,
                           'window': [0]*24 + [1]*24
                           },
                          {'name': 'peak',
                           'rate': 1.,
                           'window': [1]*24 + [0]*24
                           },
                      ]
                      }
}


results_key = {}

# Convert dict to nx
x = convert_dict_to_nx(network_dict)

# Convert nx to echo
em, node_uid_dict = convert_nx_to_echo(x, df)

# Convert objective dict to echo objective
obj = convert_objective_to_echo_objective(em, node_uid_dict, objective_dict)

# Run optimiser on echo model and echo objective
opt = run_echo_optimiser(em,
                         obj,
                         interval_duration=30,
                         time_periods=48,
                         expansion_periods=1,
                         discount_rate=0,
                         optimiser_engine='cplex',
                         opt_display=False)

results = extract_results(opt, node_uid_dict)
new_dict = append_results(results, network_dict, in_place=False)

# Get some results
grid_node = em.node_obj[node_uid_dict['bulk_grid']]
cp_node = em.node_obj[node_uid_dict['elec_cp']]
load_node = em.node_obj[node_uid_dict['load']]
battery_node = em.node_obj[node_uid_dict['battery']]
ev_cp_node = em.node_obj[node_uid_dict['ev1']]
#ev_battery = em.node_obj[node_uid_dict['ev1vehicle']]

print(opt.opt_status)
print('Grid import:\n', opt.values(cp_node.ports['upstream'].port_name, 0))
print('Load\n', opt.values(load_node.ports['load'].port_name, 0))
print('Battery soc\n', opt.values(battery_node.ports['bess'].soc_value, 0))
print('Battery\n', opt.values(battery_node.ports['bess'].port_name, 0))
print('EV node \n', opt.node_values(ev_cp_node, 0))


