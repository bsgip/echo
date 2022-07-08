"""
The echo builder module contains functions and classes used for building an echo model from a dict/json network representation.
"""
import time
from typing import Optional, Union

import networkx as nx
import numpy as np
import pandas as pd
from pyomo.util.infeasible import log_infeasible_constraints
from tqdm import tqdm

import echo.echo_models as ecm
import echo.objectives as obj
from echo.configuration import *
from echo.echo_optimiser import EchoOptimiser
from echo.echo_validators import ArrayType


class Network:
    """ A class for holding our network dict and making it easier to add nodes/edges in the correct format."""
    name: Optional[str] = 'default_name'  # name for our network
    components = {}  # network components (nodes)
    edges = {}  # network edges, representing connectivity
    objectives = {}  # any objectives we want to define

    def to_dict(self):
        """ Returns the network in a dict."""
        d = {'name': self.name, 'components': self.components, 'edges': self.edges, 'objectives': self.objectives}
        return d

    def add_node_to_components(self, n_id: str, n_type: NodeType, ports: dict = None, n_params: dict = None):
        """
        Adds an asset (node) to the component dictionary.
        Args:
            ports: dict of info on ports (names, units, parameters)
            n_id: unique node id
            n_type: node type from NodeType class, so we know what to build in echo
            n_params: any params that belong to the node (asset) rather than a particular port

        Returns:
            None
        """
        self.validate_new_port(ports)
        if self.components.get(n_id) is not None:
            print('Node {} is already defined in components. Updating node with any additional ports'.format(n_id))
            self.components[n_id]['ports'].update(ports)
        else:
            d = {'id': n_id, 'type': n_type, 'ports': ports}
            if n_params:
                d['parameters'] = n_params
            self.components[n_id] = d

    def add_edge_between_ports(self, node_tuple: tuple, port_tuple: tuple, resource: Units = None, edge_name: str = None):
        """ Adds an edge between two specified ports on two specified nodes."""
        e = {'nodes': node_tuple, 'ports': port_tuple}
        if resource:
            e['resource'] = resource
        if edge_name is None: # Create a default name by concatenating node names
            edge_name = node_tuple[0] + '_' + node_tuple[1]
        self.validate_new_edge(edge_name, node_tuple)
        self.edges[edge_name] = e

    def add_edge_between_nodes(self, node_tuple: tuple, resource: Units, edge_name: str = None):
        # Adds an edge between two nodes with no specified ports
        # First create a port on each node, with units matching the res, and port name = node name at other end of edge
        port1_dict = {node_tuple[1]: {'units': resource}}
        port2_dict = {node_tuple[0]: {'units': resource}}
        self.add_port_to_existing_node(n_id=node_tuple[0], port_dict=port1_dict)
        self.add_port_to_existing_node(n_id=node_tuple[1], port_dict=port2_dict)
        self.add_edge_between_ports(node_tuple=node_tuple, port_tuple=node_tuple, edge_name=edge_name, resource=resource)

    def add_port_to_existing_node(self, n_id: str, port_dict: dict):
        """ Updates the port dict of the node to include the new port"""
        (new_port_name, new_port_values), = port_dict.items()
        if self.components[n_id]['ports'].get(new_port_name) is not None:
            print('Port {} is already defined on node {}'.format(new_port_name, n_id))
            if new_port_values != self.components[n_id]['ports'].get(new_port_name):
                raise ValueError('Port dicts conflict, and node could not be updated.')
        else:
            self.components[n_id]['ports'].update(port_dict)

    def add_objective(self, obj_name: str, obj_type: str, component: dict = None, prices: ArrayType = None):
        o = {'type': obj_type}
        if component:
            o['component'] = component
        if prices:
            o['prices'] = prices
        self.objectives[obj_name] = o

    def validate_new_edge(self, edge_name: str, node_tuple: tuple) -> None:
        """ Checks that edge has unique name and unique node tuple."""
        assert self.edges.get(edge_name) is None, 'Edge with name \'{}\' is already defined.'.format(edge_name)
        for existing_edge_name, existing_edge_dict in self.edges.items():
            assert existing_edge_dict['nodes'] != node_tuple, \
                'Nodes {} are already connected with existing edge named \'{}\'.'.format(node_tuple, existing_edge_name)

    @staticmethod
    def validate_new_port(port_dict: dict) -> None:
        """ Checks that each port has at least a unit key """
        for port_name, port_attr in port_dict.items():
            assert port_attr.get('units') is not None, 'Port {} has no units defined.'.format(port_name)


class NetworkSet:
    """

    A network set is a grouping of separate network pieces that we want to be able to optimise/analyse as a group.
    The networks in a network set must have the same interval duration and time periods.
    This class can be used to manage single networks too, if useful.

    """

    def __init__(self, description, name='default_name'):
        self.name = name
        self.description = description
        self.networks = []
        self.num_networks = 0
        self.interval_duration = None
        self.time_periods = None
        self.results = []  # another way of accessing results
        self.processing_errors = []

    def add_network(self, network: dict):
        """ Add a single network to the network set."""
        self.networks.append(network)
        self.num_networks = len(self.networks)

    def add_networks_from_list(self, networks: list):
        """ Add a list of networks to the network set."""
        self.networks.extend(networks)
        self.num_networks = len(self.networks)

    def optimise_network_set(self, log_file=None, verbose=False):
        """ Optimises the set of networks defined in the class instance. """

        if log_file is not None:
            prog_file = open(log_file, 'w')
        else:
            prog_file = None
        for i in tqdm(range(self.num_networks), desc='Optimising sites', file=prog_file):
            # Append results to network dict
            self.results.append(
                process_single_network(self.networks[i], self.interval_duration, self.time_periods, verbose=verbose))
            # Check if there were errors
            self.processing_errors.append(True if self.results[i]['infeasible'] is True else False)
        if log_file is not None:
            prog_file.close()

        return self.processing_errors

    def to_df(self, node, port):
        """
        for each network segment in netset, gets the value of port on node, if that node and port combination does not exist
        sets the result to nan.
        :param node: name of node to look at
        :param port: port to get value of
        :return: dataframe with timeseries data
        """

        assert self.results is not None, "Generate results first"

        data = {}
        for i, res in enumerate(self.results):
            val = np.nan
            if node in res:
                if port in res[node]:
                    if 'port_val' in res[node][port]:
                        val = res[node][port]['port_val']
            data['seg_{}'.format(i)] = val

        df = pd.DataFrame.from_dict(data)
        return df

    def get_echo_model(self, network_name: str):
        """ Returns an echo model of a network in the network set"""
        network_dict = self.networks[network_name]
        x = convert_dict_to_nx(network_dict)
        em, node_name_dict = convert_nx_to_echo(x, None)
        return em, node_name_dict

    def get_echo_optimiser(self, network_name: str):
        """ Returns the echo optimiser for a network in the network set"""
        em, node_name_dict = self.get_echo_model(network_name)
        network_dict = self.networks[network_name]
        objective_dict = network_dict.get('objective')
        objective_set = convert_objective_to_echo_objective(em, node_name_dict, objective_dict)

        opt = run_echo_optimiser(em,
                                 objective_set,
                                 interval_duration=self.interval_duration,
                                 time_periods=self.time_periods,
                                 expansion_periods=1,
                                 discount_rate=0,
                                 optimiser_engine='cplex',
                                 opt_display=False)
        return opt

    def export_results_to_df(self):
        """ Exports optimisation results to a pandas dataframe and returns that dataframe"""
        pass


def process_single_network(network_dict: dict, interval_duration: int, time_periods: int, verbose: bool = True):
    """ Ingests a single network in a networkset, converts it to an echo model,
    runs the optimiser, appends results to the original network, and returns results."""

    if verbose:
        print(f"Processing network {network_dict['name']}")
    x = convert_dict_to_nx(network_dict, verbose=verbose)
    em, node_name_dict = convert_nx_to_echo(x, None, verbose=verbose)
    objective_dict = network_dict.get('objective')
    obj = convert_objective_to_echo_objective(em, node_name_dict, objective_dict, verbose=verbose)

    # Run optimiser on echo model and echo objective
    opt = run_echo_optimiser(em,
                             obj,
                             interval_duration=interval_duration,
                             time_periods=time_periods,
                             expansion_periods=1,
                             discount_rate=0,
                             optimiser_engine='cplex',
                             opt_display=False,
                             verbose=verbose)

    # Manage results
    results = extract_results(opt, node_name_dict)
    # append_results(results, network_dict, in_place=True)
    network_dict['infeasible'] = True if 'infeasible' in opt.opt_status['Termination condition'] else False
    results['infeasible'] = network_dict['infeasible']
    return results


def convert_dict_to_nx(netw_jsn: dict, verbose: bool = True):
    """ Creates nx graph from network dictionary"""
    if verbose:
        start_time = time.time()
        print('Converting dict to networkx...')
    n = nx.Graph()
    # Assume we have a list of components, and that all components are nodes
    # Node name is the unique node ID, Node dict carries all the relevant node info in a dict
    for node_name, node_dict in netw_jsn['components'].items():
        n.add_node(node_name,
                   name=node_name,
                   attr=node_dict)

    # Add edges, Edge name is the unique edge ID, Edge dict carries node pair info, optional port pair info, and resource type
    for edge_name, edge_dict in netw_jsn['edges'].items():
        # Check that both edge nodes exist in the component dict
        assert edge_dict['nodes'][0] in n.nodes, \
            'Node {} is part of edge {} but is not defined in components dict'.format(edge_dict['nodes'][0], edge_name)
        assert edge_dict['nodes'][1] in n.nodes, \
            'Node {} is part of edge {} but is not defined in components dict'.format(edge_dict['nodes'][1], edge_name)

        n.add_edge(edge_dict['nodes'][0], edge_dict['nodes'][1],
                   name=edge_name,
                   ports=edge_dict['ports'],
                   res=edge_dict['resource'])
        # NB: networkx may add the edges in a different order to the way we specify

    check_nx_for_floating_nodes(n)  # Check that the graph is connected
    check_port_names_are_consistent(n)  # Check there are no naming issues

    end_time = time.time()
    print('Finished converting dict to nx. Time taken (seconds): ', end_time - start_time)
    return n


def convert_nx_to_echo(g, df, verbose=True):
    """ Creates echo model from nx graph"""
    if verbose:
        start_time = time.time()
        print('Converting networkx model to echo...')

    node_name_dict = {}  # Initialise a dict for storing the mapping between node names and node UIDs

    system = ecm.OptimisationGraph()

    # Create nodes
    for node in g.nodes:
        # Check what the node type is so we know what kind of echo node to make
        node_dict = g.nodes[node]['attr']
        # Construct the right kind of node
        construct_echo_node(system, node_name_dict, node, node_dict, df)

    # Do edges
    for edge in g.edges:
        # Get node names from edge object
        node1_name = edge[0]
        node2_name = edge[1]
        # Retrieve the echo node objects using the node names
        node1 = system.node_obj[node_name_dict[node1_name]]
        node2 = system.node_obj[node_name_dict[node2_name]]

        # Get port info
        edge_dict = g.edges[edge]
        port1 = edge_dict['ports'][0]
        port2 = edge_dict['ports'][1]

        # need to check we have these round the right way
        if port1 in list(node1.ports.keys()):
            connect_nodes(system, node1, node2, port1=port1, port2=port2)
        else:
            connect_nodes(system, node1, node2, port1=port2, port2=port1)

    end_time = time.time()
    print('Finished converting nx to echo. Time taken (seconds): ', end_time-start_time)
    return system, node_name_dict


def construct_echo_node(system, node_name_dict: dict, node, node_dict: dict, df: pd.DataFrame):
    """
    Works out which type of echo node to build. Builds it, adds it to the graph, and updates the node_name dict.
    Args:
        system: Echo Optimisation Graph
        node_name_dict: dict of {uid: node_name}
        node: str, node name
        node_dict: dict of attributes relevant to the node
        df: dataframe containing any static time series data

    Returns:

    """

    def update():
        """ Adds node to system and updates node uid dict"""
        system.add_node_obj(new_node)
        node_name_dict[node] = new_node.node_name

    if node_dict['type'] == NodeType.Battery:
        new_node = create_battery_node(node_dict, node_dict['ports'])

    elif node_dict['type'] == NodeType.Tellegen:
        new_node = create_tellegen_node(node_dict, node_dict['ports'])

    elif node_dict['type'] == NodeType.Flex:
        new_node = create_flex_node(node_dict, node_dict['ports'])

    elif node_dict['type'] == NodeType.Load:
        new_node = create_load_node(node_dict, node_dict['ports'], df)

    elif node_dict['type'] == NodeType.EV:
        new_node = create_ev(node_dict, df)

    elif node_dict['type'] == NodeType.Inverter:
        new_node = create_inverter_node(node_dict, node_dict['ports'])

    elif node_dict['type'] == NodeType.Solar:
        new_node = create_solar_node(node_dict, node_dict['ports'], df)

    elif node_dict['type'] == NodeType.MultiCommodityTellegen:
        new_node = create_multi_commodity_tellegen_node(node_dict, node_dict['ports'])

    else:
        raise ValueError('node type {} is not recognised/does not have a builder function'.format(node_dict['type']))
    # Update our graph
    update()


def convert_objective_to_echo_objective(em, node_name_dict: dict, objective_dict: dict, verbose: bool = True):
    """ Converts all the objectives defined in an objective set to echo objectives,
    and returns an echo objective set. """

    if verbose:
        print('Converting objectives to echo objectives')
    objective_list = []
    for obj_name, obj_dict in objective_dict.items():
        if obj_dict['type'] == 'import_tariff':
            new_obj = create_import_tariff(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif (obj_dict['type'] == 'import_demand_tariff') or (obj_dict['type'] == 'export_demand_tariff'):
            new_obj = create_demand_tariff(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif obj_dict['type'] == 'throughput':
            new_obj = create_throughput_tariff(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif (obj_dict['type'] == 'peak_pos_power') or (obj_dict['type'] == 'peak_neg_power'):
            new_obj = create_peak_power_objective(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        elif obj_dict['type'] == 'quadratic':
            new_obj = create_quadratic_objective(obj_dict, node_name_dict, em)
            objective_list.append(new_obj)
        else:
            ValueError('Objective not recognised')

    output = obj.ObjectiveSet(objective_list=objective_list)
    return output


def create_import_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo import tariff from a tariff dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ImportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_export_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo export tariff from a tariff dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ExportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_demand_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo demand tariff from a tariff dictionary"""
    echo_charge_list = []
    charges = tariff_dict['charges']  # list of charge dicts
    for c in charges:
        rate = c['rate']
        window = c['window']
        if 'min_demand' in c:
            min_demand = c['min_demand']
        else:
            min_demand = 0
        # todo allow demand tariffs to be specific with start/end times
        c = obj.DemandCharge(rate=rate, min_demand=min_demand, window_array=window)  # Create demand charge
        echo_charge_list.append(c)

    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    import_demand = True if 'import' in tariff_dict['type'] else False
    export_demand = False if 'import' in tariff_dict['type'] else True
    demand_tariff = obj.DemandTariffObjective(component=component_obj,
                                              demand_charges=echo_charge_list,
                                              export_demand=export_demand,
                                              import_demand=import_demand)
    return demand_tariff


def create_throughput_tariff(tariff_dict, node_name_dict, em):
    """ Creates an echo throughput tariff from a tariff dictionary"""
    # todo test this
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ThroughputCost(component=component_obj, rate=tariff_dict['rate'])
    return t


def create_peak_power_objective(tariff_dict, node_name_dict, em):
    """ Creates an echo peak power objective from an objective dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    if 'pos' in tariff_dict['type']:
        t = obj.PeakPositivePower(component=component_obj)
    else:
        t = obj.PeakNegativePower(component=component_obj)
    return t


def create_quadratic_objective(tariff_dict, node_name_dict, em):
    """ Creates an echo quadratic objective from an objective dictionary"""
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.QuadraticPower(component=component_obj)
    return t


def get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em):
    """ Retrieves an objective component defined in an objective dict from an echo model and returns it."""
    target_node = tariff_dict['component']['node']
    target_port = tariff_dict['component']['port']
    assert target_node in node_name_dict.keys(), f"tariff component {tariff_dict['component']} does not correspond to a defined node/port."
    node_obj = em.node_obj[node_name_dict[target_node]]
    component_obj = node_obj.ports[target_port]
    return component_obj


def run_echo_optimiser(echo_graph,
                       objective_set,
                       interval_duration,
                       time_periods,
                       expansion_periods=1,
                       discount_rate=0,
                       optimiser_engine='cplex',
                       opt_display=False,
                       verbose=True):
    """ Runs the echo optimiser on an echo graph with an echo objective set. Returns the optimiser object."""
    if verbose:
        print('Performing whole model checks')
    # Check we have consistent array lengths for ports
    for node_name, node_obj in echo_graph.node_obj.items():
        for port_name, port_obj in node_obj.ports.items():
            # Check we have the correct array lengths - todo may not be sufficient to just check initial value, what about other arrays
            array_length_check(port_obj.initial_value, time_periods,
                               'port "{}" on node "{}", should have length = {} but has length = '.format(port_name,
                                                                                                          node_name,
                                                                                                          time_periods),
                               scalar_ok=True)

            # Check every optional port has an edge, if it doesn't, set it to zero so it doesn't interfere w the optimisation
            if port_obj.optional is True:
                success = port_connectivity_check(port_obj, echo_graph)
                if success is False:
                    print('port "{}" on node "{}" has no edge, setting port to zero'.format(port_name, node_name))
                    port_obj.set_flow_constraints(max_import=0., max_export=0.)

    optimiser = EchoOptimiser(interval_duration=interval_duration,
                              number_of_intervals=time_periods,
                              number_of_expansion_intervals=1,
                              discount_rate=0,
                              ES=echo_graph,
                              objective_set=objective_set,
                              optimiser_engine=optimiser_engine)

    optimiser.optimise(tee=opt_display)
    log_infeasible_constraints(optimiser.model)

    return optimiser


def connect_nodes(system: ecm.OptimisationGraph, node1: ecm.Node, node2: ecm.Node, port1: str, port2: str):
    """ Connects two nodes together via specified ports. Doesn't currently handle blank port names. """

    p1 = node1.ports[port1]
    p2 = node2.ports[port2]
    system.connect_ports_and_create_edge(p1, p2)


def create_battery_node(node_dict: dict, port_dict: dict):
    """ Creates an echo battery node from the provided node dict."""
    check_node_has_only_one_port(node_dict)
    node = ecm.Node(node_name=node_dict['id'])
    (port_name, port_attr), = port_dict.items()
    battery_params = port_attr['parameters']  #todo maybe these should be node parameters?
    b = ecm.ElectricalStorage(**battery_params)
    node.ports[port_name] = b
    return node


def create_tellegen_node(node_dict: dict, port_dict: dict):
    """ Creates an echo tellegen node from the provided node dict."""
    node = ecm.TellegenNode(node_name=node_dict['id'])
    create_flex_ports(node, port_dict)
    return node

def create_flex_ports(node_obj: ecm.Node, port_dict: dict):
    for port_name, port_attr in port_dict.items():
        if port_attr.get('parameters') is not None:
            new_port = ecm.FlexPort(units=port_attr['units'], **port_attr['parameters'])
        else:
            new_port = ecm.FlexPort(units=port_attr['units'])
        node_obj.ports[port_name] = new_port

def create_multi_commodity_tellegen_node(node_dict: dict, port_dict: dict) -> ecm.Node:
    """ Creates a multi commodity tellegen node """
    node = ecm.MultiCommodityTellegenNode(node_name=node_dict['id'])
    create_flex_ports(node, port_dict)
    return node

def create_flex_node(node_dict: dict, port_dict: dict) -> ecm.Node:
    """ Creates an echo flexible node from the provided node dict.
    A flexible node is a node with a single flexible port with a specified unit."""
    check_node_has_only_one_port(node_dict)
    node = ecm.Node(node_name=node_dict['id'])
    create_flex_ports(node, port_dict)
    return node

def create_load_node(node_dict: dict, port_dict: dict, df: pd.DataFrame) -> ecm.Node:
    """ Creates a node with a demand (import only) port."""
    check_node_has_only_one_port(node_dict)
    node = ecm.Node(node_name=node_dict['id'])
    (port_name, port_attr), = port_dict.items()
    p = ecm.Demand(units=port_attr['units'])
    load_profile = process_field(port_attr['data'], df)
    p.add_initial_value_from_array(load_profile)
    node.ports[port_name] = p
    return node

def create_inverter_node(node_dict: dict, port_dict: dict) -> ecm.Node:
    """
    Creates an inverter node, which has one AC port, and at least one DC port.
    """
    inv_params = node_dict['parameters']
    inverter = ecm.Inverter(max_import=inv_params['max_import'],
                            max_export=inv_params['max_export'],
                            dc_ac_efficiency=inv_params['dc_ac_eta'],
                            ac_dc_efficiency=inv_params['ac_dc_eta'])
    for i in inv_params['dc_ports']:
        inverter.add_dc_port(i)
    inverter.add_ac_port(inv_params['ac_port'])
    return inverter

def create_solar_node(node_dict: dict, port_dict: dict, df: pd.DataFrame) -> ecm.Node:
    """ Creates a node with one electrical generation port. """
    check_node_has_only_one_port(node_dict)
    node = ecm.Node(node_name=node_dict['id'])
    (port_name, port_attr), = port_dict.items()
    if port_attr.get('parameters') is not None:
        p = ecm.ElectricalGeneration(units=port_attr['units'], **port_attr['parameters'])
    else:
        p = ecm.ElectricalGeneration(units=port_attr['units'])
    pv_profile = process_field(port_attr['data'], df)
    p.add_initial_value_from_array(pv_profile)
    node.ports[port_name] = p
    return node

def create_ev(node_dict: dict, df: pd.DataFrame) -> ecm.Node:
    check_node_has_only_one_port(node_dict)
    ev_dict = node_dict['parameters']
    ev_dict['available'] = process_field(ev_dict['available'], df)
    ev_dict['usage'] = process_field(ev_dict['usage'], df)
    ev_dict['cp_name'] = ev_dict['ports'][0]
    node = ecm.EV(**ev_dict)  # pass all our params as kwargs
    return node


def check_nx_for_floating_nodes(g: nx.Graph):
    """ Checks if we have nodes without any edge"""
    nodes = set(g.nodes)
    nodes_with_edges = set([i for edge in g.edges for i in edge])
    nodes_without_edges = nodes - nodes_with_edges
    assert len(nodes_without_edges) == 0, 'Node {} has no edge'.format(nodes_without_edges)


def check_port_names_are_consistent(g: nx.Graph):
    """ Checks consistency of port names as defined in nodes and port names as defined in edges."""
    inconsistencies = []
    for edge in g.edges:
        # check that there is a 1-1 correspondence between ports and nodes
        for i in range(0, 2):
            port = g.edges[edge]['ports'][i]
            node1_ports = g.nodes[edge[0]]['attr']['ports']
            node2_ports = g.nodes[edge[1]]['attr']['ports']

            if port not in node1_ports and port not in node2_ports:
                err = 'Port {} may be misnamed in edge {}. It does not belong to either node. ' \
                      'One node has ports {} and the other has ports {}'.format(port, edge, list(node1_ports.keys()),
                                                                                list(node2_ports.keys()))
                inconsistencies.append(err)

    assert len(inconsistencies) == 0, inconsistencies


def array_length_check(array, length: int, message, scalar_ok=False):
    """ Checks if an array has the correct length."""
    if array is not None:
        if hasattr(array, '__len__') or (not scalar_ok):
            assert len(array) == length, message + str(len(array))


def port_connectivity_check(port_obj: ecm.Port, graph: ecm.OptimisationGraph):
    """ Checks if two ports are connected by an edge."""
    for _, edge_obj in graph.edge_obj.items():
        if port_obj in edge_obj.vertices:
            return True
    return False


def extract_results(optimiser: EchoOptimiser, node_name_dict: dict, results_key: dict = None) -> dict:
    """ Extracts results from an echo model and returns them in a dict.
    Results key arg allows user to specify which results they want returned."""

    system = optimiser.ES
    output = {}  # for storing results
    for node_name, node_uid in node_name_dict.items():
        output[node_name] = {}
        if 'battery' in node_name:  #todo better way of doing this, we could refer to the node types?
            battery_node = system.node_obj[node_uid]
            battery_port = battery_node.ports[list(battery_node.ports.keys())[0]]  # todo less hacky
            output[node_name]['soc'] = optimiser.values(battery_port.soc_value, 0)
            output[node_name]['p'] = optimiser.values(battery_port.port_name, 0)
            output[node_name]['opt_capacity'] = optimiser.values(battery_port.optimised_capacity, 0)
        elif 'ev' in node_name:
            ev_node = system.node_obj[node_uid]
            output[node_name]['vehicle_soc'] = optimiser.values(ev_node.ports['vehicle'].soc_value, 0)
            output[node_name]['vehicle_p'] = optimiser.values(ev_node.ports['vehicle'].port_name, 0)
            if hasattr(optimiser.model, ev_node.ports['vehicle'].trip_slack):
                output[node_name]['trip_infeasibility'] = optimiser.values(ev_node.ports['vehicle'].trip_slack, 0)
                output[node_name]['charge_status'] = 'success' if all(
                    output[node_name]['trip_infeasibility'] == 0) else 'infeasible'
                # todo need to update this to have some tolerance rather than ==0

        else:  # Get port value + any slack vars
            node_obj = system.node_obj[node_uid]
            for port_name, port_obj in node_obj.ports.items():
                output[node_name][port_name] = {}
                output[node_name][port_name]['p'] = optimiser.values(port_obj.port_name, 0)
                if hasattr(optimiser.model, port_obj.import_slack):
                    output[node_name][port_name]['import_violation'] = optimiser.values(port_obj.import_slack, 0)
                    output[node_name][port_name]['import_violation_max'] = optimiser.values(port_obj.import_slack_max,
                                                                                            0)
                else:
                    pass
                    # output[node_name][port_name]['import_violation'] = 0 * optimiser.values(port_obj.port_name, 0)
                    # output[node_name][port_name]['import_violation_max'] = 0 * optimiser.values(port_obj.port_name, 0)
                if hasattr(optimiser.model, port_obj.export_slack):
                    output[node_name][port_name]['export_violation'] = optimiser.values(port_obj.export_slack, 0)
                    output[node_name][port_name]['export_violation_max'] = optimiser.values(port_obj.export_slack_max,
                                                                                            0)
                else:
                    pass
                    # output[node_name][port_name]['export_violation'] = 0 * optimiser.values(port_obj.port_name, 0)
                    # output[node_name][port_name]['export_violation_max'] = 0 * optimiser.values(port_obj.port_name, 0)

    return output


def extract_results_as_df(optimiser, node_name_dict: dict) -> pd.DataFrame:
    system = optimiser.ES
    output = {}  # for storing results
    for node_name, node_uid in node_name_dict.items():
        if 'battery' in node_name:  #todo better way of doing this, we could refer to the node types?
            battery_node = system.node_obj[node_uid]
            (battery_port_name, battery_port), = battery_node.ports.items()
            output[node_name+'_node_'+battery_port_name+'_port'+'_soc'] = optimiser.values(battery_port.soc_value, 0)
            output[node_name+'_node_'+battery_port_name+'_port'+'_p'] = optimiser.values(battery_port.port_name, 0)
            output[node_name+'_node_'+battery_port_name+'_port'+'_opt_capacity'] = optimiser.values(battery_port.optimised_capacity, 0)

        else:  # Get port value + any slack vars
            node_obj = system.node_obj[node_uid]
            for port_name, port_obj in node_obj.ports.items():
                output[node_name+'_node_'+port_name+'_port'+'_p'] = optimiser.values(port_obj.port_name, 0)

    df = pd.DataFrame.from_dict(output)
    return df


def append_results(result_dict, network_dict, in_place=False):
    """ Takes dict of results from an echo model, and appends them to the correct places in a network dict. """
    # todo want to give option to directly edit the original network dict, or return an updated copy
    if in_place is True:
        for node_name, results in result_dict.items():
            network_dict['components'][node_name]['results'] = results
    else:
        network_dict = network_dict.copy()
        for node_name, results in result_dict.items():
            network_dict['components'][node_name]['results'] = results
        return network_dict


# Pydantic tinkering
#
# #from our_validators import *
#
# class BatteryParams(BaseModel):
#     max_capacity: float
#     depth_of_discharge_limit: float = 0
#     charging_power_limit: float
#     discharging_power_limit: float
#     charging_efficiency: float = 1
#     discharging_efficiency: float = 1
#     initial_state_of_charge: float
#     test_var: str = str(max_capacity)
#
#     #max_cap_sign = validator("thing to be validated", allow_reuse=True)(my_validator_name)  #needs to be assigned to variable name,
#
#     @validator('max_capacity', allow_reuse=True)
#     def max_cap_sign(cls, v):
#         if v < 0:
#             raise ValueError(f"Max battery capacity should be a positive number")
#         return v
#
#     @root_validator()
#     def dod_check(cls, values):
#         dod_lim = values.get('depth_of_discharge_limit')
#         max_cap = values.get('max_capacity')
#         if dod_lim < 0 or dod_lim > max_cap:
#             raise ValueError('DoD must be between 0 and max capacity')
#         return values
#
#     @root_validator()
#     def init_soc_check(cls, values):
#         init_soc = values.get('initial_state_of_charge')
#         dod_lim = values.get('depth_of_discharge_limit')
#         max_cap = values.get('max_capacity')
#         lb = max(0., dod_lim)
#         if init_soc < lb or init_soc > max_cap:
#             raise ValueError('Initial state of charge must be between min DoD and max capacity')
#         return values
#
#     @validator('charging_power_limit')
#     def charging_sign(cls, v):
#         if v < 0:
#             raise ValueError(f"Charging power limit should be a positive number")
#         return v
#
#     @validator('discharging_power_limit')
#     def discharging_sign(cls, v):
#         if v > 0:
#             raise ValueError('Enter charging power limit using positive load convention (lim<0).')
#         return v
#
#     @validator('charging_efficiency')
#     def ch_efficiency_rule(cls, v):
#         if v > 1 or v < 0:
#             raise ValueError(f"Charging efficiency should be a number between 0 and 1.")
#
#     @validator('discharging_efficiency')
#     def dch_efficiency_rule(cls, v):
#         if v > 1 or v < 0:
#             raise ValueError(f"Discharging efficiency should be a number between 0 and 1.")
#
#
# b_dict = {'max_capacity': 15.,
#           'depth_of_discharge_limit': 5,
#           'charging_power_limit': 1.25,
#           'discharging_power_limit': -1.25,
#           'charging_efficiency': 1.,
#           'discharging_efficiency': 1.,
#           'initial_state_of_charge': 5}
#
# b = BatteryParams(**b_dict

def get_pyomo_var_map(optimiser):
    comp_names = [str(i) for i in optimiser.model.component_objects()]
    comp_objs = [i for i in optimiser.model.component_objects()]
    output = dict(zip(comp_names, comp_objs))
    return output


def get_pyomo_vars_from_port_name(port_name, var_map):
    var_names = []
    ignore_vars = ['index', 'edge', 'con']
    for var_name, var_obj in var_map.items():
        if port_name in var_name:
            flag = [x for x in ignore_vars if x in var_name]
            if not flag:
                var_names.append(var_name)
    return var_names


def check_node_has_only_one_port(node_dict: dict) -> None:
    """ Checks that a node has only one port defined """
    port_dict = node_dict['ports']
    assert len(port_dict) == 1, 'Node {} is of type \'{}\' and can only have one port, but multiple are defined: {}.'.format(
        node_dict['id'], node_dict['type'], list(port_dict.keys()))


def retrieve_value(d, key):
    out = None
    if key in d.keys():
        out = d[key]
        if hasattr(out, '__len__'):
            if len(out) == 0:
                out = None
    return out


def retrieve_key(d, val):
    for k, v in d.items():
        if v == val:
            return k
    return None


def process_field(field, df):
    """ Checks if a field points to data in a df or if it contains the data directly."""
    if type(field) is str:
        try:
            x = df[field]
            vals = x.values
        except IndexError:
            'No column with name {} in df'.format(field)
    else:
        vals = field
    return vals
