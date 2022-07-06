import pandas as pd
from echo.echo_builder import *
from echo.bz_utils import *

time_periods = 48

# Import components and hierarchy/topology data as json
convert_network_dict_to_json(file_name='../bz_data/acton_network.json')
anu_network = get_anu_electrical_network_json()

# Import electrical loads as df
df = get_cleaned_electrical_data()

# Import gas loads as df
# todo

# Import data on what assets exist at each building
# todo
asset_info = {}


def add_electrical_network(n: Network):
    bsp_node_name = 'BSP1'
    cp_node_name = 'CP1'

    n.add_node_to_components(n_id=bsp_node_name, n_type=NodeType.Flex,
                             ports={'downstream': {'units': Units.KW}})  # Create a BSP node
    port_list = list(anu_network.keys())
    port_list.append('upstream')
    port_dict = dict.fromkeys(port_list, {'units': Units.KW})
    n.add_node_to_components(n_id=cp_node_name, n_type=NodeType.Tellegen,
                             ports=port_dict)  # Create a tellegen node with one port per feeder, plus an upstream port
    # connect cp to bsp
    n.add_edge_between_ports(node_tuple=(bsp_node_name, cp_node_name),
                             port_tuple=('downstream', 'upstream'),
                             resource=Units.KW)

    # Topology is feeder --> substation --> building
    for feeder_name, sub_dict in anu_network.items():
        port_list = list(sub_dict.keys())
        port_list.append('upstream-feeder')
        port_dict = dict.fromkeys(port_list, {'units': Units.KW})
        # Create tellegen node for each feeder, which has ports for all connected downstream subs plus an upstream port
        n.add_node_to_components(n_id=feeder_name, n_type=NodeType.Tellegen, ports=port_dict)
        # Connect feeder to CP node
        n.add_edge_between_ports(node_tuple=(feeder_name, cp_node_name),
                                 port_tuple=('upstream-feeder', feeder_name),
                                 resource=Units.KW)

        for sub_name, bldg_list in sub_dict.items():
            port_list = list(bldg_list)
            port_list.append('upstream-sub')
            port_dict = dict.fromkeys(port_list, {'units': Units.KW})
            # Create tellegen node for substation, with ports for all connected downstream buildings plus an upstream port
            n.add_node_to_components(n_id=sub_name, n_type=NodeType.Tellegen, ports=port_dict)
            # Connect substation to feeder
            n.add_edge_between_ports(node_tuple=(sub_name, feeder_name),
                                     port_tuple=('upstream-sub', sub_name),
                                     resource=Units.KW)

            for bldg_name in bldg_list:
                # Create a multi commodity tellegen node for each building's cp
                n.add_node_to_components(n_id=bldg_name, n_type=NodeType.MultiCommodityTellegen,
                                         ports={sub_name: {'units': Units.KW}})
                n.add_edge_between_ports(node_tuple=(bldg_name, sub_name),
                                         port_tuple=(sub_name, bldg_name),
                                         resource=Units.KW)

                # # Get any load data for the bldg
                # col_name = match_network_building_name_to_time_series(bldg_name, df)
                # load_name = bldg_name + '_load'
                # n.add_node_to_components(n_id=load_name, n_type=NodeType.Flex,  ports={load_name: {'units': Units.KW, 'data': col_name}})
                # # Add a port to the CP to accommodate this load
                # n.add_port_to_existing_node(bldg_name, port_dict={'load': {'units': Units.KW}})
                # # Do edge to the bldg cp
                # n.add_edge_between_ports(node_tuple=(load_name, bldg_name), port_tuple=(load_name, 'load'))

    # print(n.components['Avenue'])
    # print(n.components['AVE00739'])
    # print(n.components['B116'])
    # print(n.components['B116_load'])


def add_gas_network(n: Network):
    """ Adds gas network nodes - assuming we can just plug everything into a single connection point."""
    bsp_node_name = 'BSP_gas'
    cp_node_name = 'CP_gas'
    n.add_node_to_components(n_id=bsp_node_name, n_type=NodeType.Flex,
                             ports={'downstream': {'units': Units.JPS}})  # Create a BSP node for gas

    n.add_node_to_components(n_id=cp_node_name, n_type=NodeType.Tellegen,
                             ports={'upstream': {'units': Units.JPS}})  # Create a CP for gas

    n.add_edge_between_ports(node_tuple=(bsp_node_name, cp_node_name),
                             port_tuple=('downstream', 'upstream'),
                             resource=Units.JPS)  # connect nodes

    # Iterate through buildings and build an edge to the gas CP node for each building:
    # Topology is feeder --> substation --> building
    for _, sub_dict in anu_network.items():
        for _, bldg_list in sub_dict.items():
            for bldg_name in bldg_list:
                # Add a port on the building node
                n.add_port_to_existing_node(n_id=bldg_name, port_dict={cp_node_name: {'units': Units.JPS}})
                # Add a port on the cp node
                n.add_port_to_existing_node(n_id=cp_node_name, port_dict={bldg_name: {'units': Units.JPS}})
                # Connect these ports
                n.add_edge_between_ports(node_tuple=(bldg_name, cp_node_name),
                                         port_tuple=(cp_node_name, bldg_name),
                                         resource=Units.JPS)  # connect nodes


def populate_network_with_assets(n: Network):
    pass


# Create an echo network
n = Network()

add_electrical_network(n)
add_gas_network(n)

x = convert_dict_to_nx(netw_jsn=n.to_dict())

# Convert nx to echo
em, node_uid_dict = convert_nx_to_echo(x, df)
