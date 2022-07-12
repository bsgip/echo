"""
The echo builder module contains functions and classes used for building an echo model from a dict/json network representation.
"""

from typing import Optional, Union, Any
import pandas as pd
import numpy as np
import networkx as nx
from pyomo.util.infeasible import log_infeasible_constraints
from tqdm import tqdm

import echo.echo_models as em
from echo.configuration import *
import echo.echo_optimiser as eo
import echo.objectives as eobj

import time as time


class Network(em.BaseModel):
    """ A class for holding our network dict and making it easier to add nodes/edges in the correct format."""
    name: Optional[str] = 'default_name'  # name for our network
    components = {}  # network components (nodes)
    edges = {}  # network edges, representing connectivity
    objectives = {}  # any objectives we want to define

    def add_node_to_components(self, n_id: str, n_type: NodeType, ports: Any = None, params: dict = None,
                               data: Any = None):
        """
        Adds an asset (node) to the component dictionary.
        Args:
            ports: dict of info on ports (names, units, parameters)
            n_id: unique node id
            n_type: node type from NodeType class, so we know what to build in echo
            params: any params that belong to the node (asset) rather than a particular port

        Returns:
            None
        """
        self.validate_new_port(ports)
        if self.components.get(n_id) is not None:
            print('Node {} is already defined in components. Updating node with any additional ports'.format(n_id))
            self.components[n_id]['ports'].update(ports)
        else:
            d = {'id': n_id, 'type': n_type, 'ports': ports}
            if params:
                d['parameters'] = params
            if data:
                d['data'] = data
            self.components[n_id] = d

    def add_edge_between_ports(self, node_tuple: tuple, port_tuple: tuple, resource: Units = None,
                               edge_name: str = None):
        """ Adds an edge between two specified ports on two specified nodes."""
        e = {'nodes': node_tuple, 'ports': port_tuple}
        if resource:
            e['resource'] = resource
        if edge_name is None:  # Create a default name by concatenating node names
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
        self.add_edge_between_ports(node_tuple=node_tuple, port_tuple=node_tuple, edge_name=edge_name,
                                    resource=resource)

    def add_port_to_existing_node(self, n_id: str, port_dict: dict):
        """ Updates the port dict of the node to include the new port"""
        (new_port_name, new_port_values), = port_dict.items()
        if self.components[n_id]['ports'].get(new_port_name) is not None:
            print('Port {} is already defined on node {}'.format(new_port_name, n_id))
            if new_port_values != self.components[n_id]['ports'].get(new_port_name):
                raise ValueError('Port dicts conflict, and node could not be updated.')
        else:
            self.components[n_id]['ports'].update(port_dict)

    def add_objective(self, obj_name: str, obj_type: TariffType, component: dict = None, prices: Any = None,
                      charges: list = None):
        o = {'type': obj_type, 'name': obj_name}
        if component:
            o['component'] = component
        if prices:
            o['prices'] = prices
        if charges:
            o['charges'] = charges
        self.objectives[obj_name] = o

    def validate_new_edge(self, edge_name: str, node_tuple: tuple) -> None:
        """ Checks that edge has unique name and unique node tuple."""
        assert self.edges.get(edge_name) is None, 'Edge with name "{}" is already defined.'.format(edge_name)
        for existing_edge_name, existing_edge_dict in self.edges.items():
            assert existing_edge_dict['nodes'] != node_tuple, \
                'Nodes {} are already connected with existing edge named "{}".'.format(node_tuple, existing_edge_name)
        # Checks that nodes are different
        assert node_tuple[0] != node_tuple[1], 'A node cannot be connected to itself.'

    @staticmethod
    def validate_new_port(ports: Union[dict, list]) -> None:
        """ Checks that each port has at least a unit key """
        if type(ports) is dict:
            for port_name, port_attr in ports.items():
                assert port_attr.get('units') is not None, 'Port {} has no units defined.'.format(port_name)
        elif type(ports) is list:
            assert len(set(ports)) == len(ports), 'Port names must be unique.'
        else:
            raise ValueError(
                'Ports should be defined as a list of port names, or as a dictionary with the port name as key.')

    def validate_network(self):
        print('Validating network "{}"'.format(self.name))

        # check consistency of port names as defined in self.components and self.edges
        err = []
        for edge_name, edge in self.edges.items():
            # check that there is a 1-1 correspondence between ports and nodes
            port1 = edge['ports'][0]
            port2 = edge['ports'][1]
            node1 = edge['nodes'][0]
            node2 = edge['nodes'][1]
            for _, node in self.components.items():
                if node1 == node['id'] or node2 == node['id']:
                    if port1 not in node['ports'] and port2 not in node['ports']:
                        err.append('In edge "{}", port "{}" doesn\'t belong to node "{}" or node "{}"'.format(
                            edge_name, port1, node1, node2))
        assert len(err) == 0, err

        # Print msg warning if no objectives are defined
        if bool(self.objectives) is True:
            for obj_name, obj in self.objectives.items():
                component_node = obj['component']['node']
                component_port = obj['component']['port']
                flag = 0
                for _, node in self.components.items():
                    if component_node == node['id']:
                        flag = 1
                        assert component_port in node['ports'], \
                            'Objective "{}" refers to node "{}", port "{}", but no such port ' \
                            'exists on node {}, which has ports {}'.format(obj_name, component_node, component_port,
                                                                           component_node, node['ports'])
                if flag == 0:
                    raise ValueError(
                        'Objective "{}" refers to node "{}" but no node by that name is defined.'.format(obj_name,
                                                                                                         component_node))
        else:
            print('No objectives defined for network "{}"'.format(self.name))


class NetworkSet:
    """

    A network set is a grouping of separate network pieces that we want to be able to optimise/analyse as a group.
    The networks in a network set must have the same interval duration and time periods.
    This class can be used to manage single networks too, if useful.

    """

    def __init__(self, description, name='default_name'):
        self.name = name
        self.description = description
        self.networks = []  # list of networks as dicts
        self.num_networks = 0
        self.interval_duration = None
        self.time_periods = None
        self.results = []  # another way of accessing results
        self.processing_errors = []
        self.df = None  # dataframe that can hold data for some of our nodes

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
                process_single_network(self.networks[i], self.interval_duration, self.time_periods, verbose=verbose,
                                       df=self.df))
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

    def get_echo_model(self, network_name: str, df: pd.DataFrame = None):
        """ Returns an echo model of a network in the network set"""
        network_dict = self.networks[network_name]
        em, obj, node_name_dict = convert_dict_to_echo(network_dict, df)
        return em, obj, node_name_dict

    def get_echo_optimiser(self, network_name: str):
        """ Returns the echo optimiser for a network in the network set"""
        em, obj, node_name_dict = self.get_echo_model(network_name)

        opt = run_echo_optimiser(em,
                                 obj,
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


def process_single_network(network_dict: dict, interval_duration: int, time_periods: int, df: pd.DataFrame,
                           verbose: bool = True):
    """ Ingests a single network in a networkset, converts it to an echo model,
    runs the optimiser, appends results to the original network, and returns results."""

    if verbose:
        print(f"Processing network {network_dict['name']}")
    em, obj, node_name_dict = convert_dict_to_echo(network_dict, df=df, verbose=verbose)

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


def convert_network_to_echo(netw: Network, df: pd.DataFrame, verbose: bool = True):
    # Converts a network class to a dict, then turns it into an echo model
    netw_dict = netw.dict()
    return convert_dict_to_echo(netw=netw_dict, df=df, verbose=verbose)


def convert_dict_to_echo(netw: dict, df: pd.DataFrame, verbose: bool = True):
    """ Converts dict directly to echo optimisation graph."""
    if verbose:
        start_time = time.time()
        print('Converting dict to echo...')

    node_name_dict = {}
    system = em.OptimisationGraph()
    for node_name, node_dict in netw['components'].items():
        construct_echo_node(system=system, node_dict=node_dict, node_name_dict=node_name_dict, node=node_name, df=df)

    for edge_name, edge_dict in netw['edges'].items():
        construct_echo_edge(system=system, edge_name=edge_name, edge_dict=edge_dict, node_name_dict=node_name_dict)

    obj_set = construct_echo_objective(system=system, objective_dict=netw['objectives'], node_name_dict=node_name_dict)

    if verbose:
        end_time = time.time()
        print('Finished converting dict to echo. Time taken (seconds): ', end_time - start_time)
    return system, obj_set, node_name_dict


def construct_echo_objective(system: em.OptimisationGraph, node_name_dict: dict, objective_dict: dict,
                             verbose: bool = True):
    """ Converts all the objectives defined in an objective set to echo objectives,
    and returns an echo objective set. """
    if verbose:
        print('..constructing objective...')

    objective_list = []
    for obj_name, obj_dict in objective_dict.items():
        # Get the component the tariff applies to:
        component_obj = get_tariff_component_from_node_port_name(obj_dict, node_name_dict, system)

        if obj_dict['type'] == TariffType.ImportTariff:
            new_obj = eobj.ImportTariff(name=obj_name, component=component_obj, tariff_array=obj_dict['prices'])

        elif obj_dict['type'] == TariffType.ExportTariff:
            new_obj = eobj.ExportTariff(name=obj_name, component=component_obj, tariff_array=obj_dict['prices'])

        elif obj_dict['type'] == TariffType.ImportDemandTariff:
            new_obj = create_demand_tariff(obj_dict, component_obj)

        elif obj_dict['type'] == TariffType.ExportDemandTariff:
            new_obj = create_demand_tariff(obj_dict, component_obj)

        elif obj_dict['type'] == TariffType.ThroughputCost:
            new_obj = eobj.ThroughputCost(name=obj_name, component=component_obj, rate=obj_dict['rate'])

        elif obj_dict['type'] == TariffType.PeakPosPower:
            new_obj = eobj.PeakPositivePower(name=obj_name, component=component_obj)

        elif obj_dict['type'] == TariffType.PeakNegPower:
            new_obj = eobj.PeakNegativePower(name=obj_name, component=component_obj)

        elif obj_dict['type'] == TariffType.QuadraticPower:
            new_obj = eobj.QuadraticPower(name=obj_name, component=component_obj)
        else:
            raise ValueError(
                'Objective type "{}" is not recognised and does not have a builder function'.format(
                    obj_dict['type']))
        objective_list.append(new_obj)

    obj_set = eobj.ObjectiveSet(objective_list=objective_list)
    return obj_set


def construct_echo_edge(system: em.OptimisationGraph, edge_name: str, edge_dict: dict, node_name_dict: dict):
    node1_name, node2_name = edge_dict['nodes']
    port1, port2 = edge_dict['ports']
    edge_unit = edge_dict['resource']

    # Retrieve the echo node objects using the node names
    node1 = system.node_obj[node_name_dict[node1_name]]
    node2 = system.node_obj[node_name_dict[node2_name]]

    # need to check we have the ports paired with the correct node
    if port1 in list(node1.ports.keys()):
        p1 = node1.ports[port1]
        p2 = node2.ports[port2]
    else:
        p1 = node1.ports[port2]
        p2 = node2.ports[port1]
    assert p1.units == edge_unit, 'In edge "{}", port and edge units are inconsistent.'.format(edge_name)
    assert p2.units == edge_unit, 'In edge "{}", Port and edge units are inconsistent.'.format(edge_name)
    system.connect_ports_and_create_edge(p1, p2)


def construct_echo_node(system: em.OptimisationGraph, node_name_dict: dict, node, node_dict: dict, df: pd.DataFrame):
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
        new_node = create_battery_node(node_dict)

    elif node_dict['type'] == NodeType.ElectricalTellegen:
        new_node = create_tellegen_node(node_dict, Units.KW)

    elif node_dict['type'] == NodeType.ElectricalFlex:
        new_node = create_flex_node(node_dict, Units.KW)

    elif node_dict['type'] == NodeType.ElectricalLoad:
        new_node = create_load_node(node_dict, Units.KW, df)

    elif node_dict['type'] == NodeType.EV:
        new_node = create_ev(node_dict, df)

    elif node_dict['type'] == NodeType.Inverter:
        new_node = create_inverter_node(node_dict)

    elif node_dict['type'] == NodeType.Solar:
        new_node = create_solar_node(node_dict, df)

    elif node_dict['type'] == NodeType.CarbonAggregation:
        new_node = create_carbon_aggregation_node(node_dict)

    elif node_dict['type'] == NodeType.FlexWithEmissions:
        new_node = create_flex_node_with_emissions(node_dict, units=Units.KW)


    else:
        raise ValueError(
            'Node type "{}" is not recognised and does not have a builder function'.format(node_dict['type']))
    # Update our graph
    update()


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
        print('Performing whole model checks...')
    # Check we have consistent array lengths for ports
    for node_name, node_obj in echo_graph.node_obj.items():
        for port_name, port_obj in node_obj.ports.items():
            # Check we have the correct array lengths - todo may not be sufficient to just check initial value, what about other arrays
            array_length_check(port_obj.initial_value, time_periods,
                               'port "{}" on node "{}", should have length = {} but has length = '.format(port_name,
                                                                                                          node_name,
                                                                                                          time_periods),
                               scalar_ok=True)

    optimiser = eo.EchoOptimiser(interval_duration=interval_duration,
                                 number_of_intervals=time_periods,
                                 number_of_expansion_intervals=1,
                                 discount_rate=0,
                                 ES=echo_graph,
                                 objective_set=objective_set,
                                 optimiser_engine=optimiser_engine)

    optimiser.optimise(tee=opt_display)
    log_infeasible_constraints(optimiser.model)

    return optimiser


## Create node functions

def create_battery_node(node_dict: dict):
    """ Creates an echo battery node from the provided node dict."""
    port_name = check_node_has_only_one_port(node_dict)
    node = em.Battery(node_name=node_dict['id'], port_name=port_name, **node_dict['parameters'])
    return node


def create_tellegen_node(node_dict: dict, port_unit):
    """ Creates an echo tellegen node from the provided node dict."""
    node = em.TellegenNode(node_name=node_dict['id'])
    port_list = node_dict['ports']
    create_flex_ports(node, port_list, [port_unit] * len(port_list))
    return node


def create_flex_node(node_dict: dict, units: Units) -> em.Node:
    """ Creates an echo flexible node from the provided node dict.
    A flexible node is a node with a single flexible port with a specified unit."""
    port_name = check_node_has_only_one_port(node_dict)
    node = em.Node(node_name=node_dict['id'])
    node.ports[port_name] = em.FlexPort(units=units)
    return node


def create_load_node(node_dict: dict, unit: Units, df: pd.DataFrame) -> em.Node:
    """ Creates a node with a demand (import only) port."""
    port_name = check_node_has_only_one_port(node_dict)
    load_profile = process_field(node_dict['data'], df)
    node = em.Load(node_name=node_dict['id'], port_name=port_name, port_unit=unit, profile=load_profile)
    return node


def create_inverter_node(node_dict: dict) -> em.Node:
    """ Creates an inverter node, which has one AC port, and at least one DC port. """

    ports_defined_on_node = node_dict['ports']
    ports_defined_in_params = [node_dict['parameters']['ac_port_name']] + node_dict['parameters']['dc_port_names']
    assert set(ports_defined_on_node) == set(ports_defined_in_params), \
        'Node "{}" has ports {} defined on node, and ports {} defined in parameters.'.format(node_dict['id'],
                                                                                             ports_defined_on_node,
                                                                                             ports_defined_in_params)
    inv_params = node_dict['parameters']
    ac_port = inv_params.pop('ac_port_name')
    dc_ports = inv_params.pop('dc_port_names')
    inverter = em.Inverter(node_name=node_dict['id'], **inv_params)
    inverter.add_ac_port(ac_port)
    for i in dc_ports:
        inverter.add_dc_port(i)

    return inverter


def create_solar_node(node_dict: dict, df: pd.DataFrame) -> em.Node:
    """ Creates a node with one electrical generation port. """
    port_name = check_node_has_only_one_port(node_dict)
    pv_profile = process_field(node_dict['data'], df)
    if node_dict.get('parameters'):
        node = em.Solar(node_name=node_dict['id'], port_name=port_name, profile=pv_profile,
                     params=node_dict.get('parameters'))
    else:
        node = em.Solar(node_name=node_dict['id'], port_name=port_name, profile=pv_profile)
    return node


def create_ev(node_dict: dict, df: pd.DataFrame) -> em.Node:
    cp_port_name = check_node_has_only_one_port(node_dict)
    ev_dict = node_dict['parameters']
    ev_dict['available'] = process_field(ev_dict['available'], df)
    ev_dict['usage'] = process_field(ev_dict['usage'], df)
    node = em.EV(node_name=node_dict['id'], cp_name=cp_port_name, **ev_dict)  # pass all our params as kwargs
    return node


def create_flex_node_with_emissions(node_dict: dict, units: Units):
    node = em.FlexNodeWithEmissions(node_name=node_dict['id'], emitting_port_units=units, **node_dict['parameters'])
    return node


def create_carbon_aggregation_node(node_dict: dict):
    node = em.CarbonAggregation(node_name=node_dict['id'])
    ports = node_dict['ports']
    create_flex_ports(node_obj=node, port_list=ports, port_units=[Units.CO2] * len(ports))
    return node


#### Create objectives functions

def create_demand_tariff(tariff_dict: dict, component_obj: em.Port):
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
        c = eobj.DemandCharge(rate=rate, min_demand=min_demand, window_array=window)  # Create demand charge
        echo_charge_list.append(c)

    import_demand = True if tariff_dict['type'] == TariffType.ImportDemandTariff else False
    export_demand = False if tariff_dict['type'] == TariffType.ImportDemandTariff else True
    demand_tariff = eobj.DemandTariffObjective(name=tariff_dict['name'],
                                          component=component_obj,
                                          demand_charges=echo_charge_list,
                                          export_demand=export_demand,
                                          import_demand=import_demand)
    return demand_tariff


def get_tariff_component_from_node_port_name(tariff_dict: dict, node_name_dict: dict, system: em.OptimisationGraph):
    """ Retrieves an objective component defined in an objective dict from an echo model and returns it."""
    target_node = tariff_dict['component']['node']
    target_port = tariff_dict['component']['port']
    assert target_node in node_name_dict.keys(), 'Tariff component "{}" does not correspond to a defined node/port.'.format(
        tariff_dict['component'])
    node_obj = system.node_obj[node_name_dict[target_node]]
    component_obj = node_obj.ports[target_port]
    return component_obj


### Util functions

def create_flex_ports(node_obj: em.Node, port_list: list, port_units: list):
    for i in range(len(port_list)):
        new_port = em.FlexPort(units=port_units[i])
        node_obj.ports[port_list[i]] = new_port


#### Check functions

def array_length_check(array, length: int, message, scalar_ok=False):
    """ Checks if an array has the correct length."""
    if array is not None:
        if hasattr(array, '__len__') or (not scalar_ok):
            assert len(array) == length, message + str(len(array))


### Result extraction functions

def extract_results(optimiser: eo.EchoOptimiser, node_name_dict: dict, results_key: dict = None) -> dict:
    """ Extracts results from an echo model and returns them in a dict.
    Results key arg allows user to specify which results they want returned."""

    system = optimiser.ES
    output = {}  # for storing results
    for node_name, node_uid in node_name_dict.items():
        output[node_name] = {}
        if 'battery' in node_name:  # todo better way of doing this, we could refer to the node types?
            battery_node = system.node_obj[node_uid]
            battery_port = battery_node.ports[list(battery_node.ports.keys())[0]]  # todo less hacky
            output[node_name]['soc'] = optimiser.values(battery_port.soc_value, 0)
            output[node_name]['port_val'] = optimiser.values(battery_port.port_name, 0)
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
                output[node_name][port_name]['port_val'] = optimiser.values(port_obj.port_name, 0)
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


def extract_objectives(optimiser: eo.EchoOptimiser) -> dict:
    output = {}
    for obj in optimiser.objective_set.objective_list:
        # get objective from optimiser
        output[obj.name] = optimiser.get_single_objective_total_value(obj)
    output['total_cost'] = optimiser.get_total_objective_value()
    return output


def append_results(result_dict, network_dict, in_place: bool = False):
    """ Takes dict of results from an echo model, and appends them to the correct places in a network dict. """
    if in_place is True:
        for node_name, results in result_dict.items():
            network_dict['components'][node_name]['results'] = results
    else:
        network_dict = network_dict.copy()
        for node_name, results in result_dict.items():
            network_dict['components'][node_name]['results'] = results
        return network_dict


def check_node_has_only_one_port(node_dict: dict):
    """ Checks that a node has only one port defined """
    ports = node_dict['ports']
    if type(ports) is dict or type(ports) is list:
        assert len(
            ports) == 1, 'Node {} is of type "{}" and can only have one port, but multiple are defined: {}.'.format(
            node_dict['id'], node_dict['type'], ports)
        if type(ports) is list:
            port_name = ports[0]
        else:
            (port_name, _), = ports.items()
    elif type(ports) is str:
        port_name = ports
    return port_name


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


######################## Superseded functions - todo delete? ######################


def convert_dict_to_nx(netw_jsn: Network, verbose: bool = True):
    """ Creates nx graph from network dictionary"""
    if verbose:
        start_time = time.time()
        print('Converting dict to networkx...')

    n = nx.Graph()
    for node_name, node_dict in netw_jsn.components.items():
        n.add_node(node_name, name=node_name, attr=node_dict)

    for edge_name, edge_dict in netw_jsn.edges.items():
        edge_nodes = edge_dict['nodes']
        edge_ports = edge_dict['ports']
        edge_unit = edge_dict['resource']
        # Check that both edge nodes exist in the component dict
        assert edge_nodes[0] in n.nodes, \
            'Node {} is part of edge {} but is not defined in components dict'.format(edge_nodes[0], edge_name)
        assert edge_nodes[1] in n.nodes, \
            'Node {} is part of edge {} but is not defined in components dict'.format(edge_nodes[1], edge_name)

        n.add_edge(edge_nodes[0], edge_nodes[1], name=edge_name, ports=edge_ports, unit=edge_unit)
        # NB: networkx may add the edges in a different order to the way we specify

    check_nx_for_floating_nodes(n)  # Check that the graph is connected
    check_port_names_are_consistent(n)  # Check there are no naming issues

    if verbose:
        end_time = time.time()
        print('Finished converting dict to nx. Time taken (seconds): ', end_time - start_time)
    return n


def convert_nx_to_echo(g: nx.Graph, df: pd.DataFrame, verbose: bool = True):
    """ Creates echo model from nx graph"""
    if verbose:
        start_time = time.time()
        print('Converting networkx model to echo...')

    node_name_dict = {}  # Initialise a dict for storing the mapping between node names and node UIDs

    system = em.OptimisationGraph()

    # Create nodes
    for node_name in g.nodes:
        node_dict = g.nodes[node_name]['attr']
        construct_echo_node(system, node_name_dict, node_name, node_dict, df)

    # Create edges
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
            p1 = node1.ports[port1]
            p2 = node2.ports[port2]
        else:
            p1 = node1.ports[port2]
            p2 = node2.ports[port1]
        system.connect_ports_and_create_edge(p1, p2)

    if verbose:
        end_time = time.time()
        print('Finished converting nx to echo. Time taken (seconds): ', end_time - start_time)
    return system, node_name_dict


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


def check_nx_for_floating_nodes(g: nx.Graph):
    """ Checks if we have nodes without any edge"""
    nodes = set(g.nodes)
    nodes_with_edges = set([i for edge in g.edges for i in edge])
    nodes_without_edges = nodes - nodes_with_edges
    assert len(nodes_without_edges) == 0, 'Node {} has no edge'.format(nodes_without_edges)


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

def port_connectivity_check(port_obj: em.Port, graph: em.OptimisationGraph):
    # todo this should be an optimisation graph method
    """ Checks if two ports are connected by an edge."""
    for _, edge_obj in graph.edge_obj.items():
        if port_obj in edge_obj.vertices:
            return True
    return False
