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

# Create an echo network
n = Network()

# Create a BSP node
n.add_flex_node(node_id='BSP1', ports=['downstream'])
# Create a tellegen node with one port per feeder, plus an upstream port
port_list = list(anu_network.keys())
port_list.append('upstream')
n.add_tellegen_node(node_id='CP1', ports=port_list, units='kW')

# Walk through feeders
for feeder_name, sub_dict in anu_network.items():
    # Each sub connected to the feeder gets a port, plus one upstream port
    port_list = list(sub_dict.keys())
    port_list.append('upstream')
    # Create tellegen node for each feeder, which has ports for all connected subs plus an upstream port
    n.add_tellegen_node(node_id=feeder_name, ports=port_list, units='kW')
    # Do edges - need to look one level up in the hierarchy
    edge_name = feeder_name + '_CP1'  # we know the level up is CP1
    n.add_edge(edge_name=edge_name, node_tuple=(feeder_name, 'CP1'), port_tuple=('upstream', feeder_name), res='elec')
    # Walk through substation names
    for sub_name, bldg_list in sub_dict.items():
        # Get buildings connected so we can name ports, plus an upstream port
        port_list = list(bldg_list)
        port_list.append('upstream')
        n.add_tellegen_node(node_id=sub_name, ports=port_list, units='kW')
        # Do edges
        edge_name = sub_name + feeder_name  # get the feeder from lvl above
        n.add_edge(edge_name=edge_name, node_tuple=(sub_name, feeder_name), port_tuple=('upstream', sub_name),
                        res='elec')

        # Walk through building names
        for bldg_name in bldg_list:
            # Create a tellegen node for each building's cp
            n.add_tellegen_node(node_id=bldg_name, ports=['cp'], units='kW')
            # Do edge
            edge_name = bldg_name + sub_name
            n.add_edge(edge_name=edge_name, node_tuple=(bldg_name, sub_name), port_tuple=('cp', bldg_name),
                            res='elec')
            # Get any load data for the bldg
            col_name = match_network_building_name_to_time_series(bldg_name, df)
            load_name = bldg_name + '_load'
            n.add_data_node(node_id=load_name, node_type='load', ports=[load_name], units='kW', node_data=col_name)
            # Create nodes for all the assets at each building
            # todo where to get this info beyond a building load
            # for asset in asset_info[bldg_name]:
            #     pass

print(n.components['Avenue'])
print(n.components['B116'])





