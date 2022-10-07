from random import uniform

import echo.echo_builder as ecb
from echo.bz_utils import *
import matplotlib.pyplot as plt
from tqdm import tqdm
from echo.echo_optimiser import EchoOptimiser

# Import components and hierarchy/topology data as json
# Build json each time
convert_network_dict_to_json(file_name='../bz_data/acton_network.json')
anu_network = get_anu_electrical_network_json()

# Import electrical loads as df
df = get_cleaned_electrical_data()
# Add a generic daily entry we can scale up and down
df['generic'] = np.array(([0.1] * 6 + [0.4] + [0.6] + [1.0] * 7 + [0.8] + [0.4] + [0.2] + [0.1] * 6) * 365)

time_periods = len(df)

# Import gas loads as df
# todo

# Import data on what assets exist at each building
# todo
asset_info = {}

# Create an echo network
n = ecb.Network(name='acton campus')

bsp_node_name = 'BSP1'
cp_node_name = 'CP1'

n.add_node_to_components(n_id=bsp_node_name, n_type=ecb.NodeType.ElectricalFlex,
                         ports=['downstream'])  # Create a BSP node
port_list = list(anu_network.keys()) + ['upstream']
n.add_node_to_components(n_id=cp_node_name, n_type=ecb.NodeType.ElectricalTellegen,
                         ports=port_list)  # Create a tellegen node with one port per feeder, plus an upstream port
# connect cp to bsp
n.add_edge_between_ports(node_tuple=(bsp_node_name, cp_node_name),
                         port_tuple=('downstream', 'upstream'),
                         resource=ecb.Units.KW)
total_nodes = 0
# Topology is feeder --> substation --> building
for feeder_name, sub_dict in anu_network.items():
    port_list = list(sub_dict.keys()) + ['upstream-feeder']
    # Create tellegen node for each feeder, which has ports for all connected downstream subs plus an upstream port
    n.add_node_to_components(n_id=feeder_name, n_type=ecb.NodeType.ElectricalTellegen, ports=port_list)
    # Connect feeder to CP node
    n.add_edge_between_ports(node_tuple=(feeder_name, cp_node_name),
                             port_tuple=('upstream-feeder', feeder_name),
                             resource=ecb.Units.KW)
    total_nodes += 1
    for sub_name, bldg_list in sub_dict.items():
        port_list = list(bldg_list) + ['upstream-sub']
        # Create tellegen node for substation, with ports for all connected downstream buildings plus an upstream port
        n.add_node_to_components(n_id=sub_name, n_type=ecb.NodeType.ElectricalTellegen, ports=port_list)
        # Connect substation to feeder
        n.add_edge_between_ports(node_tuple=(sub_name, feeder_name),
                                 port_tuple=('upstream-sub', sub_name),
                                 resource=ecb.Units.KW)
        total_nodes += 1
        for bldg_name in bldg_list:
            # Create a multi commodity tellegen node for each building's cp
            n.add_node_to_components(n_id=bldg_name, n_type=ecb.NodeType.MultiCommodityTellegen, ports={})
            n.update_port_dict_on_node(n_id=bldg_name, port_dict={sub_name: {'units': ecb.Units.KW}})
            n.add_edge_between_ports(node_tuple=(bldg_name, sub_name),
                                     port_tuple=(sub_name, bldg_name),
                                     resource=ecb.Units.KW)

            total_nodes += 1
            # Create some generic assets
            # Electrical load node
            load_name = bldg_name + '_load'
            # col_name = match_network_building_name_to_time_series(bldg_name, df)
            # if col_name is not None:
            #     n.add_node_to_components(n_id=load_name, n_type=ecb.NodeType.ElectricalLoad, ports=[load_name],
            #                              data=col_name)
            # else:
            n.add_node_to_components(n_id=load_name, n_type=ecb.NodeType.ElectricalLoad, ports=[load_name],
                                     data=df['generic'].values * uniform(50, 400))
            # Need to add a port to our cp
            n.update_port_dict_on_node(n_id=bldg_name, port_dict={load_name: {'units': ecb.Units.KW}})
            n.add_edge_between_ports(node_tuple=(load_name, bldg_name), port_tuple=(load_name, load_name),
                                     resource=ecb.Units.KW)
            total_nodes += 1

""" Adds gas network nodes - assuming we can just plug everything into a single connection point."""
bsp_node_name = 'BSP_gas'
cp_node_name = 'CP_gas'
n.add_node_to_components(n_id=bsp_node_name, n_type=ecb.NodeType.GasFlex,
                         ports=['downstream'])  # Create a BSP node for gas

n.add_node_to_components(n_id=cp_node_name, n_type=ecb.NodeType.GasTellegen,
                         ports=['upstream'])  # Create a CP for gas

n.add_edge_between_ports(node_tuple=(bsp_node_name, cp_node_name),
                         port_tuple=('downstream', 'upstream'),
                         resource=ecb.Units.JPS)  # connect nodes

# # Iterate through buildings and build a gas port on each building multicommodity node, connecting it to the gas CP node
# # Topology is feeder --> substation --> building
# gas_edge_counter = 0
# for _, sub_dict in anu_network.items():
#     for _, bldg_list in sub_dict.items():
#         for bldg_name in bldg_list:
#             # Check if an edge exists first
#             if n.validate_new_edge(edge_name='', node_tuple=(bldg_name, cp_node_name)) is not None:
#                 # Add a port on the building node
#                 n.update_port_dict_on_node(n_id=bldg_name, port_dict={cp_node_name: {'units': ecb.Units.JPS}})
#                 # Add a port on the cp node
#                 n.update_port_list_on_node(n_id=cp_node_name, port=bldg_name)
#                 # Connect these ports
#                 n.add_edge_between_ports(edge_name='gas_edge_' + str(gas_edge_counter),
#                                          node_tuple=(bldg_name, cp_node_name),
#                                          port_tuple=(cp_node_name, bldg_name),
#                                          resource=ecb.Units.JPS)  # connect nodes
#                 gas_edge_counter += 1

# Convert nx to echo
em, obj, node_uid_dict = ecb.convert_network_to_echo(n, df)

opt = EchoOptimiser(ES=em,
                    objective_set=obj,
                    interval_duration=60,
                    number_of_intervals=time_periods,
                    number_of_expansion_intervals=1,
                    discount_rate=0,
                    optimiser_engine='cplex',
                    verbose=True)

opt.optimise(tee=True)

results = ecb.extract_results(opt, node_uid_dict)
