import pandas as pd
import networkx as nx
import echo.objectives as obj
import echo.echo_models as ecm

def convert_dict_to_nx(netw_jsn):
    # Create networkx graph from network dictionary
    n = nx.Graph()

    # Assume we have a list of components, and that all components are nodes
    for node_name, node_dict in netw_jsn['components'].items():
        n.add_node(node_name,
                   name=node_name,
                   attr=node_dict)

    # Add edges
    for edge_name, edge_dict in netw_jsn['edges'].items():
        n.add_edge(edge_dict['nodes'][0], edge_dict['nodes'][1],
                   name=edge_name,
                   ports=edge_dict['ports'],
                   res=edge_dict['res'])

    return n


def convert_nx_to_echo(g):
    # Converts a nx graph to an echo model
    node_uid_dict = {}
    system = ecm.OptimisationGraph()

    # Create nodes
    for node in g.nodes:
        new_node = ecm.Node()
        system.add_node_obj(new_node)
        node_uid_dict[node] = node.uid

    return system, node_uid_dict


def create_battery_node(battery):

    battery_node = ecm.Node()
    b = ecm.ElectricalStorage(max_capacity=battery['max_capacity'],
                              depth_of_discharge_limit=battery['depth_of_discharge_limit'],
                              charging_power_limit=battery['charging_power_limit'],
                              discharging_power_limit=battery['discharging_power_limit'],
                              charging_efficiency=battery['charging_efficiency'],
                              discharging_efficiency=battery['discharging_efficiency'],
                              initial_state_of_charge=battery['initial_state_of_charge'])
    battery_node.ports['bess'] = b
    return battery_node


def create_load_node(load_dict):

    load_profile = load_dict['profile']
    load = ecm.Node()           # site load
    l1 = ecm.ElectricalDemand()
    l1.add_demand_profile_from_array(load_profile, expansion_periods=1)
    load.ports['load'] = l1

    return load


def create_solar_node(solar_dict):
    pv_profile = solar_dict['profile']
    solar = ecm.Node()
    pv = ecm.ElectricalGeneration()
    pv.curtailable = False
    pv.add_generation_profile_from_array(pv_profile, expansion_periods=1)
    solar.ports['pv'] = pv


def create_ev(ev, num_time_periods):
    # Straight from echo_scenario
    ev_subgraph = ecm.OptimisationGraph()

    available = ev['available']
    usage = ev['usage']
    soc_conserv = retrieve_value(ev, 'soc_conserv')
    soc_conserv_cost = retrieve_value(ev, 'soc_conserv_cost')

    if len(available) != num_time_periods:
        raise Exception(ev['name'] + ' available must have same length as load_profile')
    if len(usage) != num_time_periods:
        raise Exception(ev['name'] + ' usage must have same length as load_profile')
    ev_cp = ecm.ElectricalTellegenNode()
    ev_cp.add_named_electrical_ports(['cp', 'ev', 'usage'])
    ev_cp.ports['cp'].add_active_periods_from_array(available, expansion_periods=1)

    ev_storage = ecm.ElectricalStorage(max_capacity=ev['max_capacity'],
                                       depth_of_discharge_limit=ev['depth_of_discharge_limit'],
                                       charging_power_limit=ev['charging_power_limit'],
                                       discharging_power_limit=-1e4,
                                       charging_efficiency=ev['charging_efficiency'],
                                       discharging_efficiency=ev['discharging_efficiency'],
                                       initial_state_of_charge=ev['initial_state_of_charge'])

    vehicle = ecm.Node()
    vehicle.ports['ev'] = ev_storage
    vehicle.ports['ev'].enable_trip_slack = True
    if soc_conserv is not None:
        assert soc_conserv_cost is not None, 'soc_conserv requires soc_conserve_cost'
        vehicle.ports['ev'].soc_conserv = soc_conserv  # kWh
        vehicle.ports['ev'].soc_conserv_cost = soc_conserv_cost  # dollars per kwh
        vehicle.ports['ev'].available = available

    trip = ecm.Node()
    usage_port = ecm.ElectricalDemand()
    usage_port.add_demand_profile_from_array(usage, expansion_periods=1)
    trip.ports['usage'] = usage_port

    ev_subgraph.add_node_obj([vehicle, trip, ev_cp])
    # Do connections
    ev_subgraph.connect_ports_and_create_edge(ev_cp['ev'], ev_storage)
    ev_subgraph.connect_ports_and_create_edge(ev_cp['usage'], usage_port)

    return ev_subgraph


def check_nx_for_floating_nodes(g):
    """ Checks if we have nodes without any edge"""
    nodes = set(g.nodes)
    nodes_with_edges = set([i for edge in g.edges for i in edge])
    nodes_without_edges = nodes - nodes_with_edges
    for i in nodes_without_edges:
        print('Node ', i, ' has no edge.')


def retrieve_value(dict, key):
    out = None
    if key in dict.keys():
        out = dict[key]
        if hasattr(out, '__len__'):
            if len(out)==0:
                out = None
    return out

