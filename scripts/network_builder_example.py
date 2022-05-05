import pandas as pd
from echo.echo_builder import *

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
                'ports': ['upstream', 'load']
            }
        },
        'load': {
            'Node': {
                'id': 'load',
                'type': 'load',
                'ports': ['load'],
                'data': 'load',
                'parameters': {},
                'results': {'soc_result', 'power_result', 'other'}  # echo results stored in pandas df
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

    }
}


objective_dict = {
    'import_tariff': {'prices': [],
                      'type': None,
                      'component': 'port_or_path_name'}

}

# Convert dict to nx
x = convert_dict_to_nx(network_dict)
# Do a check
check_nx_for_floating_nodes(x)
#nx.draw(x, with_labels=True)

em, node_uid_dict = convert_nx_to_echo(x, df)

opt = run_echo_optimiser(em,
                         obj.ObjectiveSet(objective_list=[]),
                         interval_duration=30,
                         time_periods=48,
                         expansion_periods=1,
                         discount_rate=0,
                         optimiser_engine='cplex',
                         opt_display=False)

grid_node = em.node_obj[node_uid_dict['bulk_grid']]
cp_node = em.node_obj[node_uid_dict['elec_cp']]
load_node = em.node_obj[node_uid_dict['load']]

print(opt.values(grid_node.ports['downstream'].port_name, 0))
print(opt.values(cp_node.ports['upstream'].port_name, 0))
print(opt.values(load_node.ports['load'].port_name, 0))


# battery = {'max_capacity': 15., 'depth_of_discharge_limit':0,
#             'charging_power_limit':1.25, 'discharging_power_limit':-1.25,
#            'charging_efficiency':1., 'discharging_efficiency':1.,
#            'initial_state_of_charge':0}
# b = create_battery_node(battery)
