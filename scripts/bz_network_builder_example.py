import pandas as pd
from echo.echo_builder import *
from echo.bz_utils import *

time_periods = 48

# Import network data as json
netw_jsn = get_anu_electrical_network_json()

# Import time series data as df
# Units are SI (Watts)
df = get_cleaned_electrical_data()

b = ['B1', 'B2']
c = building_name_match_wrapper(b, df)


# Dummy data
df = pd.DataFrame({
    'gas_load': [4] * time_periods,
    'load': [5] * time_periods,
    'solar': [-2] * 24 + [-1] * 24,

})

# Define an example network as a dict/json type structure

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
                'ports': ['upstream', 'load', 'inverter']
            }
        },
        'load': {
            'Node': {
                'id': 'load',
                'type': 'load',
                'ports': ['load'],
                'data': 'load'
            }
        },
        'inverter': {
            'Node': {
                'id': 'inverter',
                'type': 'inverter',
                'ports': ['ac', 'dc_pv', 'dc_bess'],
                'parameters': {'max_import': 10.,
                               'max_export': -10.,
                               'ac_dc_eta': 1.,
                               'dc_ac_eta': 1.}

            }
        },
        'battery': {
            'Node': {
                'id': 'battery',
                'type': 'battery',
                'ports': ['battery'],
                'parameters': {'max_capacity': 15.,
                               'depth_of_discharge_limit': 0,
                               'charging_power_limit': 1.25,
                               'discharging_power_limit': -1.25,
                               'charging_efficiency': 1.,
                               'discharging_efficiency': 1.,
                               'initial_state_of_charge': 0},
            }
        },
        'solar': {
            'Node': {
                'id': 'solar',
                'type': 'solar',
                'ports': ['solar'],
                'data': 'solar'
            }
        },
        'bulk_gas': {
            'Node': {
                'id': 'bulk_gas',
                'type': 'flex',
                'ports': ['downstream']
            }
        },
        'gas_cp': {
            'Node': {
                'id': 'gas_cp',
                'type': 'tellegen',
                'ports': ['upstream', 'load']
            }
        },
        'gas_load': {
            'Node': {
                'id': 'gas_load',
                'type': 'load',
                'ports': ['gas_load'],
                'data': 'gas_load'
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

        'edge_3': {'nodes': ('elec_cp', 'inverter'),
                   'ports': ('inverter', 'ac'),
                   'res': 'elec'},

        'edge_4': {'nodes': ('inverter', 'solar'),
                   'ports': ('dc_pv', 'solar'),
                   'res': 'elec'},

        'edge_5': {'nodes': ('inverter', 'battery'),
                   'ports': ('dc_bess', 'battery'),
                   'res': 'elec'},

        'edge_6': {'nodes': ('bulk_gas', 'gas_cp'),
                   'ports': ('downstream', 'upstream'),
                   'res': 'gas'},

        'edge_7': {'nodes': ('gas_cp', 'gas_load'),
                   'ports': ('load', 'gas_load'),
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

