import pandas as pd
import networkx as nx
from pyomo.util.infeasible import log_infeasible_constraints
import numpy as np

import echo.objectives as obj
import echo.echo_models as ecm
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from tqdm import tqdm

from pydantic import BaseModel, validator, root_validator, confloat
from typing import Optional


class NetworkSet:
    """ A network set is a grouping of separate network pieces that we want to be able to optimise/analyse as a group.
    The networks in a network set must have the same interval duration and time periods.
    This class can be used to manage single networks too, if useful."""
    def __init__(self, description, name='default_name'):
        self.name = name
        self.description = description
        self.networks = []
        self.num_networks = 0
        self.interval_duration = None
        self.time_periods = None
        self.results = []  #another way of accessing results
        self.processing_errors = []

    def add_network(self, network: dict):
        self.networks.append(network)
        self.num_networks = len(self.networks)

    def add_networks_from_list(self, networks: list):
        self.networks.extend(networks)
        self.num_networks = len(self.networks)

    def optimise_network_set(self, log_file=None):

        if log_file is not None:
            prog_file = open(log_file, 'w')
        else:
            prog_file = None
        for i in tqdm(range(self.num_networks), desc='Optimising sites', file=prog_file):
            self.results.append(process_single_network(self.networks[i], self.interval_duration, self.time_periods))
            self.processing_errors.append(True if self.results[i]['infeasible'] is True else False)
        if log_file is not None:
            prog_file.close()

        return self.processing_errors

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
        obj = convert_objective_to_echo_objective(em, node_name_dict, objective_dict)

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
        pass

def process_single_network(network_dict: dict, interval_duration: int, time_periods: int):
    print(f"Processing network {network_dict['name']}")
    x = convert_dict_to_nx(network_dict)
    em, node_name_dict = convert_nx_to_echo(x, None)
    objective_dict = network_dict.get('objective')
    obj = convert_objective_to_echo_objective(em, node_name_dict, objective_dict)

    # Run optimiser on echo model and echo objective
    opt = run_echo_optimiser(em,
                             obj,
                             interval_duration=interval_duration,
                             time_periods=time_periods,
                             expansion_periods=1,
                             discount_rate=0,
                             optimiser_engine='cplex',
                             opt_display=False)

    # Manage results
    results = extract_results(opt, node_name_dict)
    #append_results(results, network_dict, in_place=True)
    network_dict['infeasible'] = True if 'infeasible' in opt.opt_status['Termination condition'] else False
    results['infeasible'] = network_dict['infeasible']
    return results


def convert_dict_to_nx(netw_jsn: dict):
    """ Creates nx graph from network dictionary"""
    print('Converting dict to networkx')
    n = nx.Graph()
    # Assume we have a list of components, and that all components are nodes
    # Node name is the unique node ID, Node dict carries all the relevant node info in a dict
    for node_name, node_dict in netw_jsn['components'].items():
        n.add_node(node_name,
                   name=node_name,
                   attr=node_dict)

    # Add edges, Edge name is the unique edge ID, Edge dict carries node pair info, optional port pair info, and resource type
    for edge_name, edge_dict in netw_jsn['edges'].items():
        # Check that both node edges exist already
        assert edge_dict['nodes'][0] in n.nodes, \
            'Node {} is part of edge {} but is not defined in components dict'.format(edge_dict['nodes'][0], edge_name)
        assert edge_dict['nodes'][1] in n.nodes, \
            'Node {} is part of edge {} but is not defined in components dict'.format(edge_dict['nodes'][1], edge_name)

        n.add_edge(edge_dict['nodes'][0], edge_dict['nodes'][1],
                   name=edge_name,
                   ports=edge_dict['ports'],
                   res=edge_dict['res'])
        # note that networkx may add the edges in a different order to the way we specify

    # Do some checks
    check_nx_for_floating_nodes(n)
    check_port_names_are_consistent(n)

    return n


def convert_nx_to_echo(g, df):
    """ Creates echo model from nx graph"""
    print('Converting networkx model to echo')

    node_name_dict = {}  # Initialise a dict for storing the mapping between node names and node UIDs

    system = ecm.OptimisationGraph()

    # Create nodes
    for node in g.nodes:
        # Check what the node type is so we know what kind of echo node to make
        node_dict = g.nodes[node]['attr']
        if node_dict['type'] == 'battery':
            new_node = create_battery_node(node_dict)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

        if node_dict['type'] == 'tellegen':
            new_node = create_tellegen_node(node_dict)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

        if node_dict['type'] == 'flex':
            new_node = create_flex_node(node_dict)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

        if node_dict['type'] == 'load':
            new_node = create_load_node(node_dict, df)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

        if node_dict['type'] == 'ev':
            new_node = create_ev(node_dict, df)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

        if node_dict['type'] == 'inverter':
            new_node = create_inverter_node(node_dict)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

        if node_dict['type'] == 'solar':
            new_node = create_solar_node(node_dict, df)
            system.add_node_obj(new_node)
            node_name_dict[node] = new_node.node_name

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

    return system, node_name_dict


def convert_objective_to_echo_objective(em, node_name_dict: dict, objective_dict: dict):
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
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ImportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_export_tariff(tariff_dict, node_name_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ExportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_demand_tariff(tariff_dict, node_name_dict, em):
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
    # todo test this
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.ThroughputCost(component=component_obj, rate=tariff_dict['rate'])
    return t


def create_peak_power_objective(tariff_dict, node_name_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    if 'pos' in tariff_dict['type']:
        t = obj.PeakPositivePower(component=component_obj)
    else:
        t = obj.PeakNegativePower(component=component_obj)
    return t


def create_quadratic_objective(tariff_dict, node_name_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em)
    t = obj.QuadraticPower(component=component_obj)
    return t


def get_tariff_component_from_node_port_name(tariff_dict, node_name_dict, em):
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
                       opt_display=False):
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



def connect_nodes(system, node1, node2, port1, port2):
    # todo clean this up

    if port1 is not None:
        p1 = node1.ports[port1]
    if port2 is not None:
        p2 = node2.ports[port2]

    if port1 is not None and port2 is None:
        system.connect_port_to_node_create_edges_create_port(p1, node2)
    elif port1 is None and port2 is not None:
        system.connect_port_to_node_create_edges_create_port(node1, p2)
    elif port1 is None and port2 is None:
        system.connect_two_nodes_create_edges_create_ports(node1, node2)
    else:
        system.connect_ports_and_create_edge(p1, p2)


def combine_two_graphs(g1, g2, p1=None, p2=None):
    # todo test this function
    """ Takes two networkx graphs and combines them, returning the combination as a third graph"""
    # Initialise a new graph
    output = ecm.OptimisationGraph()

    # Add all nodes from both graphs
    for n in g1.node_obj.values():
        output.add_node_obj(n)
    for n in g2.node_obj.values():
        output.add_node_obj(n)

    # Add all edges from both graphs
    for e in g1.edge_objs.values():
        output.add_edge_obj(e)
    for e in g2.edge_objs.values():
        output.add_edge_obj(e)

    # Find each port object
    port1 = None
    port2 = None
    for n in output.node_obj.values():
        for port_name, port_obj in n.ports.items():
            if port_name == p1:
                port1 = port_obj
            if port_name == p2:
                port2 = port_obj

    assert (port1 is not None) and (port2 is not None), 'Ports to be connected cannot be found in the graphs provided.'
    output.connect_ports_and_create_edge(port1, port2)
    return output


def split_graph():
    pass


def create_battery_node(node_dict):
    battery = node_dict['parameters']
    battery_node = ecm.Node()
    b = ecm.ElectricalStorage(max_capacity=battery['max_capacity'],
                              depth_of_discharge_limit=battery['depth_of_discharge_limit'],
                              charging_power_limit=battery['charging_power_limit'],
                              discharging_power_limit=battery['discharging_power_limit'],
                              charging_efficiency=battery['charging_efficiency'],
                              discharging_efficiency=battery['discharging_efficiency'],
                              initial_state_of_charge=battery['initial_state_of_charge'])

    port_name = node_dict['ports'][0]
    battery_node.ports[port_name] = b
    return battery_node


def create_tellegen_node(node_dict):
    port_list = node_dict['ports']
    port_unit = node_dict['units']
    echo_unit = get_echo_port_units(node_dict['id'], port_unit)
    tnode = ecm.TellegenNode()
    port_params = node_dict.get('parameters') if node_dict.get('parameters') is not None else None
    for port in port_list:
        tnode.add_named_flex_port(port, unit=echo_unit)
        # check for any parameters/constraints on ports - todo this will be a similar process for other node types -- make it a function
        if port_params:
            if port_params.get(port):
                port_obj = tnode.ports[port]
                port_obj.set_flow_constraints(max_export=port_params.get(port)['max_export'],
                                              max_import=port_params.get(port)['max_import'],
                                              slack=port_params.get(port)['slack'])
    return tnode


def create_flex_node(node_dict):
    port_list = node_dict['ports']
    port_unit = node_dict['units']
    echo_unit = get_echo_port_units(node_dict['id'], port_unit)
    fnode = ecm.Node()
    fnode.add_named_flex_ports(port_list, unit=echo_unit)
    return fnode


def create_load_node(load_dict, df):
    if df is not None:
        load_profile = df[load_dict['data']]
    else:
        load_profile = load_dict['data']
    port_unit = load_dict['units']
    echo_unit = get_echo_port_units(load_dict['id'], port_unit)
    load = ecm.Node()  # components load
    l1 = ecm.Demand()
    l1.add_sink_profile_from_array(load_profile, expansion_periods=1)
    l1.units = echo_unit
    port_name = load_dict['ports'][0]
    load.ports[port_name] = l1
    return load


def create_inverter_node(inverter_dict):
    inv = inverter_dict['parameters']
    inverter = ecm.Inverter(max_import=inv['max_import'],
                            max_export=inv['max_export'],
                            dc_ac_efficiency=inv['dc_ac_eta'],
                            ac_dc_efficiency=inv['ac_dc_eta'])
    for i in inv['dc_ports']:
        inverter.add_dc_port(i)
    inverter.add_ac_port(inv['ac_port'])
    return inverter


def create_solar_node(solar_dict, df):
    if df is not None:
        pv_profile = df[solar_dict['data']]
    else:
        pv_profile = solar_dict['data']
    solar = ecm.Node()
    pv = ecm.ElectricalGeneration()
    pv.curtailable = solar_dict['parameters']['curtailable']
    pv.add_generation_profile_from_array(pv_profile, expansion_periods=1)
    solar.ports[solar_dict['ports'][0]] = pv
    return solar


def create_ev(ev_dict, df):
    ev = ev_dict['parameters']
    available = ev['available']  # todo could pull from dataframes using a col name instead of directly from dict
    usage = ev['usage']
    soc_conserv = retrieve_value(ev, 'soc_conserv')
    soc_conserv_cost = retrieve_value(ev, 'soc_conserv_cost')
    tod_charging = retrieve_value(ev, 'tod_charging')
    if tod_charging is None:
        tod_charging = False

    ev_port_name = ev_dict['ports'][0]
    ev_cp = ecm.EV(charge_mode=ev['charge_mode'],
                   available=available,
                   usage=usage,
                   cp_name=ev_port_name,
                   max_capacity=ev['max_capacity'],
                   depth_of_discharge_limit=ev['depth_of_discharge_limit'],
                   charging_power_limit=ev['charging_power_limit'],
                   discharging_power_limit=-1e4,
                   charging_efficiency=ev['charging_efficiency'],
                   discharging_efficiency=ev['discharging_efficiency'],
                   initial_state_of_charge=ev['initial_state_of_charge'],
                   soc_conserv=soc_conserv if soc_conserv else None,
                   soc_conserv_cost=soc_conserv_cost if soc_conserv_cost else 0.,
                   interval_duration=ev['interval_duration'],
                   tod_charging=tod_charging,
                   trip_slack=True)

    return ev_cp


def check_nx_for_floating_nodes(g):
    """ Checks if we have nodes without any edge"""
    nodes = set(g.nodes)
    nodes_with_edges = set([i for edge in g.edges for i in edge])
    nodes_without_edges = nodes - nodes_with_edges
    assert len(nodes_without_edges) == 0, 'Node {} has no edge'.format(nodes_without_edges)


def check_port_names_are_consistent(g):
    inconsistencies = []
    for edge in g.edges:
        # check that there is a 1-1 correspondence between ports and nodes
        for i in range(0, 2):
            port = g.edges[edge]['ports'][i]
            node1_ports = g.nodes[edge[0]]['attr']['ports']
            node2_ports = g.nodes[edge[1]]['attr']['ports']

            if port not in node1_ports and port not in node2_ports:
                err = 'Port {} may be misnamed in edge {}. It does not belong to either node.'.format(port, edge)
                inconsistencies.append(err)

    assert len(inconsistencies) == 0, inconsistencies


def retrieve_value(dict, key):
    out = None
    if key in dict.keys():
        out = dict[key]
        if hasattr(out, '__len__'):
            if len(out) == 0:
                out = None
    return out


def retrieve_key(dict, val):
    for k, v in dict.items():
        if v == val:
            return k
    return None


def array_length_check(array, length, message, scalar_ok=False):
    if array is not None:
        if hasattr(array, '__len__') or (not scalar_ok):
            assert len(array) == length, message + str(len(array))


def port_connectivity_check(port_obj, graph):
    for _, edge_obj in graph.edge_obj.items():
        if port_obj in edge_obj.vertices:
            return True
    return False


def extract_results(optimiser, node_name_dict: dict, results_key: dict=None):
    """ Extracts results from an echo model and returns them in a dict.
    Results key arg allows user to specify which results they want returned."""

    system = optimiser.ES
    output = {}  # for storing results
    for node_name, node_uid in node_name_dict.items():
        output[node_name] = {}
        if 'battery' in node_name:
            battery_node = system.node_obj[node_uid]
            battery_port = battery_node.ports[list(battery_node.ports.keys())[0]] #todo less hacky
            output[node_name]['SOC'] = optimiser.values(battery_port.soc_value, 0)
            output[node_name]['delta'] = optimiser.values(battery_port.port_name, 0)
            output[node_name]['optimised_capacity'] = optimiser.values(battery_port.optimised_storage_capacity, 0)
        elif 'ev' in node_name:
            ev_node = system.node_obj[node_uid]
            output[node_name]['SOC'] = optimiser.values(ev_node.ports['vehicle'].soc_value, 0)
            output[node_name]['delta'] = optimiser.values(ev_node.ports['vehicle'].port_name, 0)
            if getattr(ev_node.ports['vehicle'], 'trip_slack') is not None:
                output[node_name]['trip_infeasibility'] = optimiser.values(ev_node.ports['vehicle'].trip_slack, 0)
                output[node_name]['charge_status'] = 'success' if all(
                    output[node_name]['trip_infeasibility'] == 0) else 'infeasible'
                # todo need to update this to have some tolerance rather than ==0

        else: # Get port value + any slack vars
            node_obj = system.node_obj[node_uid]
            for port_name, port_obj in node_obj.ports.items():
                output[node_name][port_name] = {}
                output[node_name][port_name]['port_val'] = optimiser.values(port_obj.port_name, 0)
                if getattr(port_obj, 'import_slack') is not None:
                    output[node_name][port_name]['import_violation'] = optimiser.values(port_obj.import_slack, 0)
                    output[node_name][port_name]['import_violation_max'] = optimiser.values(port_obj.import_slack_max, 0)
                else:
                    output[node_name][port_name]['import_violation'] = 0 * optimiser.values(port_obj.port_name, 0)
                    output[node_name][port_name]['import_violation_max'] = 0 * optimiser.values(port_obj.port_name, 0)
                if getattr(port_obj, 'export_slack') is not None:
                    output[node_name][port_name]['export_violation'] = optimiser.values(port_obj.export_slack, 0)
                    output[node_name][port_name]['export_violation_max'] = optimiser.values(port_obj.export_slack_max, 0)
                else:
                    output[node_name][port_name]['export_violation'] = 0 * optimiser.values(port_obj.port_name, 0)
                    output[node_name][port_name]['export_violation_max'] = 0 * optimiser.values(port_obj.port_name, 0)

    return output


# def extract_results_from_key(results_key, optimiser, echo_obj):
#     output = {}
#     echo_key = {'SOC': 'soc_value',
#                'delta': 'port_name'}
#     for var_name, select in results_key:
#         if select is True:
#             if hasattr(echo_obj, echo_key[var_name]):
#                 model_var_name = getattr(echo_obj, echo_key[var_name])
#                 output[var_name] = optimiser.values(model_var_name, 0)
#
#     return output

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


def get_echo_port_units(node_name, port_unit):
    if port_unit.upper() in vars(Units):
        unit = vars(Units)[port_unit.upper()]
        return unit
    else:
        valid_units = [f for f in dir(Units) if not f.startswith('_')]
        raise ValueError('Unit {} for node {} does not match any valid unit. Valid units are {}'.format(port_unit, node_name, valid_units))

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
# b = BatteryParams(**b_dict)


def get_pyomo_var_map(optimiser):
    comp_names = [str(i) for i in optimiser.model.component_objects()]
    comp_objs = [i for i in optimiser.model.component_objects()]
    output = dict(zip(comp_names, comp_objs))
    return output


def get_pyomo_vars_from_port_name(port_name, map):
    var_names = []
    ignore_vars = ['index', 'edge', 'con']
    for var_name, var_obj in map.items():
        if port_name in var_name:
            flag = [x for x in ignore_vars if x in var_name]
            if not flag:
                var_names.append(var_name)
    return var_names