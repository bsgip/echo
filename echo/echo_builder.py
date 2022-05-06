import pandas as pd
import networkx as nx
from pyomo.util.infeasible import log_infeasible_constraints
import numpy as np

import echo.objectives as obj
import echo.echo_models as ecm
from echo.echo_optimiser import EchoOptimiser


def convert_dict_to_nx(netw_jsn):
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

    # Do some checks
    check_nx_for_floating_nodes(n)
    check_port_names_are_consistent(n)

    return n


def convert_nx_to_echo(g, df):
    """ Creates echo model from nx graph"""
    print('Converting networkx model to echo')

    node_uid_dict = {}  # Initialise a dict for storing the mapping between node names and node UIDs

    system = ecm.OptimisationGraph()

    # Create nodes
    for node in g.nodes:
        # Check what the node type is so we know what kind of echo node/subgraph to make
        node_dict = g.nodes[node]['attr']['Node']
        if node_dict['type'] == 'battery':
            new_node = create_battery_node(node_dict)
            system.add_node_obj(new_node)
            node_uid_dict[node] = new_node.uid

        if node_dict['type'] == 'tellegen':
            new_node = create_tellegen_node(node_dict)
            system.add_node_obj(new_node)
            node_uid_dict[node] = new_node.uid

        if node_dict['type'] == 'flex':
            new_node = create_flex_node(node_dict)
            system.add_node_obj(new_node)
            node_uid_dict[node] = new_node.uid

        if node_dict['type'] == 'load':
            new_node = create_load_node(node_dict, df)
            system.add_node_obj(new_node)
            node_uid_dict[node] = new_node.uid

        if node_dict['type'] == 'ev':
            # new_subgraph, node_map = create_ev(node_dict, df)
            # system.add_subgraph(new_subgraph)
            # node_uid_dict.update(node_map)
            new_node = create_ev(node_dict, df)
            system.add_node_obj(new_node)
            node_uid_dict[node] = new_node.uid

    # Do edges
    for edge in g.edges:
        # Get node info from edge
        node1_name = edge[0]
        node2_name = edge[1]
        # Retrieve the echo node objects
        node1 = system.node_obj[node_uid_dict[node1_name]]
        node2 = system.node_obj[node_uid_dict[node2_name]]

        # Get port info
        edge_dict = g.edges[edge]
        node1_port = edge_dict['ports'][0]
        node2_port = edge_dict['ports'][1]

        connect_nodes(system, node1, node2, node1_port, node2_port)

    return system, node_uid_dict


def convert_objective_to_echo_objective(em, node_uid_dict, objective_dict):
    print('Converting objectives to echo objectives')
    objective_list = []
    for obj_name, obj_dict in objective_dict.items():
        if obj_dict['type'] == 'import_tariff':
            new_obj = create_import_tariff(obj_dict, node_uid_dict, em)
            objective_list.append(new_obj)
        elif (obj_dict['type'] == 'import_demand_tariff') or (obj_dict['type'] == 'export_demand_tariff'):
            new_obj = create_demand_tariff(obj_dict, node_uid_dict, em)
            objective_list.append(new_obj)
        elif obj_dict['type'] == 'throughput':
            new_obj = create_throughput_tariff(obj_dict, node_uid_dict, em)
            objective_list.append(new_obj)
        elif (obj_dict['type'] == 'peak_pos_power') or (obj_dict['type'] == 'peak_neg_power'):
            new_obj = create_peak_power_objective(obj_dict, node_uid_dict, em)
            objective_list.append(new_obj)
        elif obj_dict['type'] == 'quadratic':
            new_obj = create_quadratic_objective(obj_dict, node_uid_dict, em)
            objective_list.append(new_obj)
        else:
            ValueError('Objective not recognised')

    output = obj.ObjectiveSet(objective_list=objective_list)
    return output


def create_import_tariff(tariff_dict, node_uid_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em)
    t = obj.ImportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_export_tariff(tariff_dict, node_uid_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em)
    t = obj.ExportTariff(component=component_obj, tariff_array=tariff_dict['prices'])
    return t


def create_demand_tariff(tariff_dict, node_uid_dict, em):
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

    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em)
    import_demand = True if 'import' in tariff_dict['type'] else False
    export_demand = False if 'import' in tariff_dict['type'] else True
    demand_tariff = obj.DemandTariffObjective(component=component_obj,
                                              demand_charges=echo_charge_list,
                                              excess_demand_charge=None,
                                              off_peak_demand_charge=None,
                                              export_demand=export_demand,
                                              import_demand=import_demand)
    return demand_tariff


def create_throughput_tariff(tariff_dict, node_uid_dict, em):
    # todo test this
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em)
    t = obj.ThroughputCost(component=component_obj, rate=tariff_dict['rate'])
    return t


def create_peak_power_objective(tariff_dict, node_uid_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em)
    if 'pos' in tariff_dict['type']:
        t = obj.PeakPositivePower(component=component_obj)
    else:
        t = obj.PeakNegativePower(component=component_obj)
    return t


def create_quadratic_objective(tariff_dict, node_uid_dict, em):
    component_obj = get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em)
    t = obj.QuadraticPower(component=component_obj)
    return t


def get_tariff_component_from_node_port_name(tariff_dict, node_uid_dict, em):
    target_node = tariff_dict['component']['node']
    target_port = tariff_dict['component']['port']
    node_obj = em.node_obj[node_uid_dict[target_node]]
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

            # Check every port has an edge, if it doesn't, set it to zero so it doesn't interfere w the optimisation
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


def process_optimisation_results(optimiser):
    pass


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
    tnode = ecm.ElectricalTellegenNode()
    tnode.add_named_electrical_ports(port_list)
    return tnode


def create_flex_node(node_dict):
    port_list = node_dict['ports']
    fnode = ecm.Node()
    fnode.add_named_electrical_ports(port_list)
    return fnode


def create_load_node(load_dict, df):
    col_name = load_dict['data']
    load_profile = df[col_name]
    load = ecm.Node()  # site load
    l1 = ecm.ElectricalDemand()
    l1.add_demand_profile_from_array(load_profile, expansion_periods=1)
    port_name = load_dict['ports'][0]
    load.ports[port_name] = l1
    return load


def create_solar_node(solar_dict, df):
    col_name = solar_dict['data']
    pv_profile = df[col_name]
    solar = ecm.Node()
    pv = ecm.ElectricalGeneration()
    pv.curtailable = False  # todo this should be set from the dict
    pv.add_generation_profile_from_array(pv_profile, expansion_periods=1)
    solar.ports['pv'] = pv
    return solar


def create_ev(ev_dict, df):
    ev = ev_dict['parameters']
    available = ev['available']  # todo could pull from dataframes using a col name instead of directly from dict
    usage = ev['usage']
    soc_conserv = retrieve_value(ev, 'soc_conserv')
    soc_conserv_cost = retrieve_value(ev, 'soc_conserv_cost')

    ev_port_name = ev_dict['ports'][0]
    ev_cp = ecm.EV(charge_mode=ev['charge_mode'],
                   connection_port_name=ev_port_name,
                   max_capacity=ev['max_capacity'],
                   depth_of_discharge_limit=ev['depth_of_discharge_limit'],
                   charging_power_limit=ev['charging_power_limit'],
                   discharging_power_limit=-1e4,
                   charging_efficiency=ev['charging_efficiency'],
                   discharging_efficiency=ev['discharging_efficiency'],
                   initial_state_of_charge=ev['initial_state_of_charge'])

    ev_cp.ports[ev_port_name].add_active_periods_from_array(available, expansion_periods=1)
    ev_cp.ports['vehicle'].enable_trip_slack = ev['enable_trip_slack']
    if soc_conserv is not None:
        assert soc_conserv_cost is not None, 'soc_conserv requires soc_conserve_cost'
        ev_cp.ports['vehicle'].soc_conserv = soc_conserv  # kWh
        ev_cp.ports['vehicle'].soc_conserv_cost = soc_conserv_cost  # dollars per kwh
        ev_cp.ports['vehicle'].available = available

    ev_cp.ports['usage'].add_demand_profile_from_array(usage, expansion_periods=1)

    return ev_cp

    # ev_subgraph = ecm.OptimisationGraph()
    # ev_cp.ports['usage'] = ecm.ElectricalPort()
    # ev_cp.ports['vehicle'] = ecm.ElectricalPort()
    # vehicle = ecm.Node()
    # vehicle.ports['ev'] = ev_storage
    # vehicle.ports['ev'].enable_trip_slack = ev['enable_trip_slack']
    # if soc_conserv is not None:
    #     assert soc_conserv_cost is not None, 'soc_conserv requires soc_conserve_cost'
    #     vehicle.ports['ev'].soc_conserv = soc_conserv  # kWh
    #     vehicle.ports['ev'].soc_conserv_cost = soc_conserv_cost  # dollars per kwh
    #     vehicle.ports['ev'].available = available
    #
    # trip = ecm.Node()
    # usage_port = ecm.ElectricalDemand()
    # usage_port.add_demand_profile_from_array(usage, expansion_periods=1)
    # trip.ports['usage'] = usage_port
    #
    # # Add all nodes (3)
    # ev_subgraph.add_node_obj([vehicle, trip, ev_cp])
    # # Do connections
    # ev_subgraph.connect_ports_and_create_edge(ev_cp.ports['vehicle'], ev_storage)
    # ev_subgraph.connect_ports_and_create_edge(ev_cp.ports['usage'], usage_port)
    #
    # node_map = {ev_dict['id']: ev_cp.uid,
    #             ev_dict['id'] + 'vehicle': vehicle.uid,
    #             ev_dict['id'] + 'usage': trip.uid
    #             }
    #
    # return ev_subgraph, node_map


def check_nx_for_floating_nodes(g):
    """ Checks if we have nodes without any edge"""
    nodes = set(g.nodes)
    nodes_with_edges = set([i for edge in g.edges for i in edge])
    nodes_without_edges = nodes - nodes_with_edges
    assert len(nodes_without_edges) == 0, 'Node {} has no edge'.format(nodes_without_edges)


def check_port_names_are_consistent(g):

    inconsistencies = []
    for edge in g.edges:
        for i in range(0, 2):
            node = edge[i]
            port = g.edges[edge]['ports'][i]
            component = g.nodes[node]
            component_ports = component['attr']['Node']['ports']
            if port not in component_ports:
                err = 'Port {} may be misnamed in edge {}. Node {} has ports {}'.format(port, edge, node, component_ports)
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


def process_V0G_charging(ev, interval_duration):
    # Attempt to resolve to a single load by applying conv charging steps
    success, ev_soc, ev_delta, trip_infeasibility = V0G_charging(ev, interval_duration)
    # Add results to the ev dict
    ev['V0G_delta'] = ev_delta
    ev['SOC'] = ev_soc
    if retrieve_value(ev, 'tod_charging') is not None:
        if success:
            ev['charge_status'] = 'success'
        else:  # force conv
            success, ev_soc, ev_delta, trip_infeasibility = V0G_charging(ev, interval_duration, force_conv=True)
            ev['charge_status'] = 'time of day infeasible, convenience success' if success else 'infeasible'

    else:
        ev['charge_status'] = 'success' if success else 'infeasible'
    ev['trip_infeasibility'] = trip_infeasibility


def V0G_charging(ev, interval_duration, force_conv=False):
    """ Convert a V0G vehicle (convenience charging) to a soc profile and a power profile if possible."""
    available = ev['available']  # bool
    usage = ev['usage']  # kW
    charge_limit = ev['charging_power_limit']  # kW
    max_capacity = ev['max_capacity']  # kWh
    initial_soc = ev['initial_state_of_charge']  # kWh
    charging_efficiency = ev['charging_efficiency']  # ratio
    tod_charging = retrieve_value(ev, 'tod_charging')  # bool flag
    if (tod_charging is not None) and (not force_conv):
        available = available * tod_charging
    T = len(available)
    soc = np.zeros((T + 1,))
    soc[0] = initial_soc
    trip_infeasibility = np.zeros((T + 1,))
    delta = np.zeros((T,))

    for t in range(T):
        if available[t] and (soc[t] < max_capacity):  # available to charge and not at max capacity
            delta[t] = min(charge_limit, (max_capacity - soc[t]) / charging_efficiency / (interval_duration / 60))
            soc[t + 1] = soc[t] + delta[t] * (interval_duration / 60) * charging_efficiency
        else:  # if not available then it might be on a trip and using power
            soc[t + 1] = soc[t] - usage[t] * (interval_duration / 60)
        trip_infeasibility[t + 1] = - min(soc[t + 1], 0)
        soc[t + 1] = max(soc[t + 1], 0)

    success = True if (trip_infeasibility.max() == 0) else False

    return success, soc[:-1], delta, trip_infeasibility[:-1]


def extract_results(optimiser, node_uid_dict):
    """ Extracts results from an echo model and returns them in a dict"""
    system = optimiser.ES
    output = {}  # for storing results

    # todo decide what to return?
    #  we could also let the user specify what they want to retrieve

    for node_name, node_uid in node_uid_dict.items():
        if 'battery' in node_name:
            output[node_name] = {}
            battery_node = system.node_obj[node_uid]
            output[node_name]['SOC'] = optimiser.values(battery_node.ports['bess'].soc_value, 0)
            output[node_name]['delta'] = optimiser.values(battery_node.ports['bess'].port_name, 0)
            output[node_name]['optimised_capacity'] = optimiser.values(
                battery_node.ports['bess'].optimised_storage_capacity, 0)
        elif 'ev' in node_name:
            output[node_name] = {}
            ev_node = system.node_obj[node_uid]
            output[node_name]['SOC'] = optimiser.values(ev_node.ports['vehicle'].soc_value, 0)
            output[node_name]['delta'] = optimiser.values(ev_node.ports['vehicle'].port_name, 0)
            if hasattr(ev_node.ports['vehicle'], 'trip_slack'):
                output[node_name]['trip_infeasibility'] = optimiser.values(ev_node.ports['vehicle'].trip_slack, 0)
                output[node_name]['charge_status'] = 'success' if all(output[node_name]['trip_infeasibility'] == 0) else 'infeasible'

        else:
            # Just grab the port value
            output[node_name] = {}
            node_obj = system.node_obj[node_uid]
            for port_name, port_obj in node_obj.ports.items():
                output[node_name][port_name] = optimiser.values(port_obj.port_name, 0)


    return output



    # ## VERSION THAT ITERATES THROUGH PYOMO MODEL VARS/PARAMS
    # all_pyomo_components = {}
    # for pyomo_component in optimiser.model.component_objects():
    #     all_pyomo_components[(str(pyomo_component))] = pyomo_component
    # for node_name, node_uid in node_uid_dict.items():
    #     node_obj = system.node_obj[node_uid]
    #     node_dict = {}
    #     for port_name, port_obj in node_obj.ports.items():
    #         node_dict[port_name] = {}
    #         for attr_name, attr_val in vars(port_obj).items(): # see if there are port attributes that correspond to pyomo model components
    #             if attr_val in list(all_pyomo_components.keys()):
    #                 # get the value from the model
    #                 result = optimiser.values(attr_val, 0)
    #                 node_dict[port_name][attr_name] = result  # Add result to the dict for this port, for this node
    #
    #     output[node_name] = node_dict



def append_results(result_dict, network_dict):
    """ Takes dict of results from an echo model, and appends them to the correct places in a network dict. """
    # todo want to give option to directly edit the original network dict, or return an updated copy

    for node_name, results in result_dict.items():
        network_dict['components'][node_name]['Node']['results'] = results


def extract_site_results(optimiser, site, node_uid_dict):
    keys = node_uid_dict.keys()
    battery = None
    if 'battery' in keys:
        battery = dict()
        battery['SOC'] = optimiser.values(site.node_obj[node_uid_dict['battery']].ports['bess'].soc_value, 0)
        battery['delta'] = optimiser.values(site.node_obj[node_uid_dict['battery']].ports['bess'].port_name, 0)
    ev_names = [name for name in keys if 'ev:' in name]
    evs = []
    for ev_name in ev_names:
        ev = dict()
        ev['name'] = ev_name
        ev['SOC'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].soc_value, 0)
        ev['delta'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].port_name, 0)
        ev['trip_infeasibility'] = optimiser.values(site.node_obj[node_uid_dict[ev_name]].ports['ev'].trip_slack, 0)
        ev['charge_status'] = 'success' if all(ev['trip_infeasibility'] == 0) else 'infeasible'

        evs.append(ev)

    aggregate_load = optimiser.values(site.node_obj[node_uid_dict['connection_point']].ports['grid'].port_name, 0)

    if hasattr(site.node_obj[node_uid_dict['connection_point']].ports['grid'], 'import_slack'):
        import_violation = -optimiser.values(
            site.node_obj[node_uid_dict['connection_point']].ports['grid'].import_slack, 0)
    else:
        import_violation = 0. * aggregate_load

    if hasattr(site.node_obj[node_uid_dict['connection_point']].ports['grid'], 'export_slack'):
        export_violation = -optimiser.values(
            site.node_obj[node_uid_dict['connection_point']].ports['grid'].export_slack, 0)
    else:
        export_violation = 0. * aggregate_load

    return aggregate_load, battery, evs, import_violation, export_violation


def append_optim_results_to_dict(optimiser, echo_graph, node_uid_dict, network_dict):
    aggregate_load, battery, evs, import_violation, export_violation = extract_site_results(optimiser, echo_graph,
                                                                                            node_uid_dict)
    if battery:
        network_dict['battery']['SOC'] = battery['SOC']
        network_dict['battery']['delta'] = battery['delta']
    if evs:
        for ev in evs:
            name = ev['name']
            found = False
            for i in range(len(network_dict['evs'])):
                if name == 'ev:' + network_dict['evs'][i]['name']:
                    network_dict['evs'][i]['SOC'] = ev['SOC']
                    network_dict['evs'][i]['delta'] = ev['delta']
                    network_dict['evs'][i]['trip_infeasibility'] = ev['trip_infeasibility']
                    network_dict['evs'][i]['charge_status'] = ev['charge_status']
                    found = True
            if not found:
                if retrieve_value(network_dict, 'lost_ev_results') is not None:
                    network_dict['lost_ev_results'].append(ev)
                else:
                    network_dict['lost_ev_results'] = list(ev)

    network_dict['aggregate_load'] = aggregate_load
    network_dict['import_violation'] = import_violation
    network_dict['export_violation'] = export_violation
    network_dict['opt_status'] = optimiser.opt_status
    return network_dict
