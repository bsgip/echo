from echo.echo_models import *
import pandas as pd
from echo.echo_scenario import  create_echo_site_from_dict


# Define some dummy parameters
time_periods = 48


# Define network edges (which also defines the nodes)
network_edges_elec = [('bulk_grid', 'elec_cp')]
network_edges_gas = [('bulk_gas', 'gas_cp')]

# Define a building list for each node
elec_node_info = {'bulk_grid': {'bld_list': []},
             'elec_cp': {'bld_list': ['music', 'art']}
             }

gas_node_info = {'bulk_gas': {'bld_list': []},
            'gas_cp': {'bld_list': ['music', 'art']}
            }

# Define what exists at each building for each commodity type and define where we can find the time series data
# Ordered by:
# --> commodity type --> asset type --> specific asset data/params
# --> tariffs #todo work out how best to assign tariffs to points other than the connection point

music_site = {'site_name': 'music',
              'elec': {'load': {'data': 'som_load',
                                'controllable': False},
                       'solar': None,
                       'chiller': {'data': 'col_name',
                                   'temps': None,
                                   'nonlin': [-0.0068, 5.5052, 0]}},
              'gas': {'boiler': [{'data': 'col_name',
                                  'max_input': None,
                                  'max_output': None},
                                 {'data': 'col_name',
                                  'max_input': None,
                                  'max_output': None}]},
              'import_tariff': {'price_array': [0.1]*12 + [0.4]*12 + [0.3]*24},
              'export_tariff': None,
              'import_demand_charge': None,
              'export_demand_charge': None
              }

art_site = {'site_name': 'art',
              'elec': {'load': {'data': 'col_name',
                                'controllable': False},
                       'solar': {'data': 'col_name',
                                 'curtailable': False},
                       'heat_pump': {'data': 'col_name'}},
              'gas': {'boiler': [{'data': 'col_name',
                                  'max_input': None,
                                  'max_output': None},
                                 {'data': 'col_name',
                                  'max_input': None,
                                  'max_output': None}],
                      'gas_kiln': {'data': None,
                                   'max_input': None,
                                   'max_output': None}},
              'import_tariff': None,
              'export_tariff': None,
              'import_demand_charge': None,
              'export_demand_charge': None}

all_sites = {'music': music_site,
             'art': art_site}


df = pd.DataFrame({
    'som_load': [4]*time_periods,
    'soad_load': [5]*time_periods,
    'soad_solar': [-2]*24 + [-1]*24,

})

def convert_bz_site_to_scenario_site(site):
    output = {}
    output['load_profile'] = df[site['elec']['load']['data']].values

    return output

eg = convert_bz_site_to_scenario_site(music_site)

# Build the network in echo from the dict, store node uid -- node name values in dict

system = OptimisationGraph()

node_uid_dict = {}
network_nodes_elec = [item for t in network_edges_elec for item in t]

# Create the network

# Create nodes
for node_name in network_nodes_elec:
    new_node = Node()
    system.add_node_obj(new_node)
    node_uid_dict[node_name] = new_node.uid

# Create edges
for edge in network_edges_elec:
    node1 = system.node_obj[node_uid_dict[edge[0]]]
    node2 = system.node_obj[node_uid_dict[edge[1]]]
    system.connect_two_nodes_create_edges_create_ports(node1, node2)


# Add building cps to network
for n in network_nodes_elec:
    current_node_obj = system.node_obj[node_uid_dict[n]]
    bldg_connections = elec_node_info[n]['bld_list']
    for bldg_name in bldg_connections:
        # check if the node already exists
        if bldg_name not in node_uid_dict.keys():
            # Create building CP node
            cp_node = ElectricalTellegenNode()
            system.add_node_obj(cp_node)
            # build edge
            system.connect_two_nodes_create_edges_create_ports(cp_node, current_node_obj)
            # get site dict
            bldg_dict = all_sites[bldg_name]
            echo_site, objective_set, node_uid_dict = create_echo_site_from_dict(bldg_dict)


print(system.number_of_nodes())


