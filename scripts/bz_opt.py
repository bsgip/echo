import pandas as pd
from echo.echo_builder import *
from echo.bz_utils import *

time_periods = 48

# Import components and hierarchy/topology data as json
anu_network = get_anu_electrical_network_json()

# Import electrical loads as df
df = get_cleaned_electrical_data()

# Import gas loads as df
# todo

# Import data on what assets exist at each building
# todo
asset_info = {}


def add_electrical_network(n: Network):
    n.add_flex_node(node_id='BSP1', ports={'downstream': {'units': Units.KW}})  # Create a BSP node
    port_list = list(anu_network.keys())
    port_list.append('upstream')
    port_dict = dict.fromkeys(port_list, {'units': Units.KW})
    n.add_tellegen_node(node_id='CP1', ports=port_dict)  # Create a tellegen node with one port per feeder, plus an upstream port

    # Topology is feeder --> substation --> building
    for feeder_name, sub_dict in anu_network.items():
        port_list = list(sub_dict.keys())
        port_list.append('upstream')
        port_dict = dict.fromkeys(port_list, {'units': Units.KW})
        # Create tellegen node for each feeder, which has ports for all connected downstream subs plus an upstream port
        n.add_tellegen_node(node_id=feeder_name, ports=port_dict)
        # Connect feeder to CP node
        n.add_edge(edge_name=feeder_name + '_CP1', node_tuple=(feeder_name, 'CP1'),
                   port_tuple=('upstream', feeder_name), res='elec')
        for sub_name, bldg_list in sub_dict.items():
            port_list = list(bldg_list)
            port_list.append('upstream')
            port_dict = dict.fromkeys(port_list, Units.KW)
            # Create tellegen node for substation, with ports for all connected downstream buildings plus an upstream port
            n.add_tellegen_node(node_id=sub_name, ports=port_dict)
            # Connect substation to feeder
            n.add_edge(edge_name=sub_name + feeder_name, node_tuple=(sub_name, feeder_name),
                       port_tuple=('upstream', sub_name),
                       res='elec')

            for bldg_name in bldg_list:
                # Create a multi commodity tellegen node for each building's cp
                n.add_tellegen_node(node_id=bldg_name, ports={'cp': Units.KW})
                n.add_edge(edge_name=bldg_name + sub_name, node_tuple=(bldg_name, sub_name),
                           port_tuple=('cp', bldg_name),
                           res='elec')
                # Get any load data for the bldg
                col_name = match_network_building_name_to_time_series(bldg_name, df)
                load_name = bldg_name + '_load'
                n.add_data_node(node_id=load_name, node_type=NodeType.Load, ports={load_name: Units.KW}, units=Units.KW,
                                node_data=col_name)
                # Add a port to the CP to accommodate this load
                n.add_port_to_node(bldg_name, 'load', port_unit=Units.KW)
                # Do edge to the bldg cp
                n.add_edge(edge_name=load_name, node_tuple=(load_name, bldg_name), port_tuple=(load_name, 'load'),
                           res='elec')
                # Create nodes for all the assets at each building
                # todo where to get this info beyond a building load
                # for asset in asset_info[bldg_name]:
                #     pass

    print(n.components['Avenue'])
    print(n.components['AVE00739'])
    print(n.components['B116'])
    print(n.components['B116_load'])


def add_gas_network(n: Network):
    """ Adds gas network nodes - assuming we can just plug everything into a single connection point."""

    n.add_flex_node(node_id='BSP_gas', ports={'downstream': Units.JPS})  # Create a BSP node for gas
    n.add_tellegen_node(node_id='CP1', ports={'upstream': Units.JPS})  # Create a CP for gas
    n.add_edge(edge_name='BSP_gas-CP', node_tuple=('BSP_gas', 'CP1'),
               port_tuple=('downstream', 'upstream'))  # connect nodes

    # Iterate through buildings and build an edge to the gas CP node for each building:
    # Topology is feeder --> substation --> building
    for _, sub_dict in anu_network.items():
        for _, bldg_list in sub_dict.items():
            for bldg_name in bldg_list:
                # Add a port on the building node
                n.add_port_to_node(node_id=bldg_name, port_name='gas_supply', port_unit=Units.JPS)
                # Add a port on the cp node
                n.add_port_to_node(node_id='CP1', port_name=bldg_name, port_unit=Units.JPS)


def populate_network_with_assets(n: Network):
    pass


# Create an echo network
n = Network()

add_electrical_network(n)
add_gas_network(n)
