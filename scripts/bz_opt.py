import pandas as pd
from echo.echo_builder import *
from echo.bz_utils import *

time_periods = 48

# Import components and hierarchy/topology data as json
anu_network = get_anu_electrical_network_json()

# Import electrical loads as df
df = get_cleaned_electrical_data()

# Import data on what assets exist at each building
#todo
asset_info = {}

def build_anu_network():
    # Create an echo network
    n = Network()

    # Create a BSP node
    n.add_flex_node(node_id='BSP1', ports=['downstream'])
    # Create a tellegen node with one port per feeder, plus an upstream port
    port_list = list(anu_network.keys())
    port_list.append('upstream')
    n.add_tellegen_node(node_id='CP1', ports=port_list, units='kW')

    # Topology is feeder --> substation --> building
    for feeder_name, sub_dict in anu_network.items():
        port_list = list(sub_dict.keys())
        port_list.append('upstream')
        # Create tellegen node for each feeder, which has ports for all connected downstream subs plus an upstream port
        n.add_tellegen_node(node_id=feeder_name, ports=port_list, units='kW')
        # Connect feeder to CP node
        n.add_edge(edge_name=feeder_name + '_CP1', node_tuple=(feeder_name, 'CP1'), port_tuple=('upstream', feeder_name), res='elec')
        for sub_name, bldg_list in sub_dict.items():
            port_list = list(bldg_list)
            port_list.append('upstream')
            # Create tellegen node for substation, with ports for all connected downstream buildings plus an upstream port
            n.add_tellegen_node(node_id=sub_name, ports=port_list, units='kW')
            # Connect substation to feeder
            n.add_edge(edge_name=sub_name + feeder_name, node_tuple=(sub_name, feeder_name), port_tuple=('upstream', sub_name),
                            res='elec')

            for bldg_name in bldg_list:
                # Create a tellegen node for each building's cp
                n.add_tellegen_node(node_id=bldg_name, ports=['cp'], units='kW')
                n.add_edge(edge_name=bldg_name + sub_name, node_tuple=(bldg_name, sub_name), port_tuple=('cp', bldg_name),
                                res='elec')
                # Get any load data for the bldg
                col_name = match_network_building_name_to_time_series(bldg_name, df)
                load_name = bldg_name + '_load'
                n.add_data_node(node_id=load_name, node_type='load', ports=[load_name], units='kW', node_data=col_name)
                # Add a port to the CP to accommodate this load
                n.add_port_to_node(bldg_name, 'load')
                # Do edge to the bldg cp
                n.add_edge(edge_name=load_name, node_tuple=(load_name, bldg_name), port_tuple=(load_name, 'load'), res='elec')
                # Create nodes for all the assets at each building
                # todo where to get this info beyond a building load
                # for asset in asset_info[bldg_name]:
                #     pass

# print(n.components['Avenue'])
# print(n.components['AVE00739'])
# print(n.components['B116'])
# print(n.components['B116_load'])






