import pandas as pd
from echo.echo_builder import *
import numpy as np
import pprint

time_periods = 48

df = pd.DataFrame({
    'load': [5] * time_periods,
    'solar': [-2] * time_periods,
    'gas_load': [3] * time_periods
})

# Define an example network as a dict/json type structure, with fully specified ports

network_dict = {
    'components': {
        'bulk_grid': {
            'Node': {
                'id': 'bulk_grid',
                'type': 'flex',
                'units': 'kW',
                'ports': ['downstream']
            }
        },
        'elec_cp': {
            'Node': {
                'id': 'elec_cp',
                'type': 'tellegen',
                'units': 'kW',
                'ports': ['upstream', 'load', 'inverter']
            }
        },
        'inverter': {
            'Node': {
                'id': 'inverter',
                'type': 'inverter',
                'ports': ['ac', 'bess', 'pv'],
                'parameters': {'ac_port': 'ac',
                               'dc_ports': ['bess', 'pv'],
                               'max_import': 5.,
                               'max_export': -5.,
                               'ac_dc_eta': 1.,
                               'dc_ac_eta': 1.}
            }
        },
        'load': {
            'Node': {
                'id': 'load',
                'type': 'load',
                'units': 'kW',
                'ports': ['load'],
                'data': 'load',
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
                               'discharging_efficiency': 1,
                               'initial_state_of_charge': 0},
            }
        },
        'solar': {
            'Node': {
                'id': 'solar',
                'type': 'solar',
                'ports': ['solar'],
                'data': 'solar',
                'parameters': {'curtailable': False},
            }
        },
        'bulk_gas': {
            'Node': {
                'id': 'bulk_gas',
                'type': 'flex',
                'units': 'JPS',
                'ports': ['downstream']
            }
        },
        'gas_load': {
            'Node': {
                'id': 'gas_load',
                'type': 'load',
                'units': 'JPS',
                'ports': ['upstream'],
                'data': 'gas_load'
            }
        },
    },
    'edges': {
        'edge_1': {'nodes': ('bulk_grid', 'elec_cp'),
                   'ports': ('downstream', 'upstream'),
                   'res': 'elec'},

        'edge_2': {'nodes': ('elec_cp', 'load'),
                   'ports': ('load', 'load'),
                   'res': 'elec'},


        'edge_4': {'nodes': ('elec_cp', 'inverter'),
                   'ports': ('inverter', 'ac'),
                   'res': 'elec'},

        'edge_5': {'nodes': ('inverter', 'battery'),
                   'ports': ('bess', 'bess'),
                   'res': 'elec'},

        'edge_6': {'nodes': ('inverter', 'solar'),
                   'ports': ('pv', 'solar'),
                   'res': 'elec'},

        'edge_7': {'nodes': ('bulk_gas', 'gas_load'),
                   'ports': ('downstream', 'upstream'),
                   'res': 'gas'},

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
inv_node = em.node_obj[node_uid_dict['inverter']]
solar_node = em.node_obj[node_uid_dict['solar']]
gas_node = em.node_obj[node_uid_dict['bulk_gas']]

print(opt.opt_status)
print('Grid import:\n', opt.values(cp_node.ports['upstream'].port_name, 0))
print('Load\n', opt.values(load_node.ports['load'].port_name, 0))
print('Battery soc\n', opt.values(battery_node.ports['bess'].soc_value, 0))
print('Battery\n', opt.values(battery_node.ports['bess'].port_name, 0))
print('Inv node in/out:', opt.node_values(inv_node, 0))
print('Solar node: ', opt.node_values(solar_node, 0))
print('Gas supply: ', opt.node_values(gas_node, 0))


