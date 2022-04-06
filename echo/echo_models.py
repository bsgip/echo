import uuid
from typing import Optional

import networkx as nx
import numpy as np
from networkx import Graph
import pyomo.environ as en
from echo.configuration import *
from echo.constants import *


class OptimisationGraph(Graph):

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.node_obj = dict()
        self.edge_obj = dict()
        self.paths = {}

    def add_node_obj(self, node):
        def add_single_node(node_obj):
            self.add_node(node_obj)
            self.node_obj[node_obj.uid] = node_obj
        if type(node) is list:
            for n in node:
                add_single_node(n)
        else:
            add_single_node(node)

    def add_edge_obj(self, edge):
        def add_single_edge(edge_obj):
            port1 = edge_obj.vertices[0]
            port2 = edge_obj.vertices[1]
            node1 = self.lookup_node_from_port(port1)
            node2 = self.lookup_node_from_port(port2)
            self.add_edge(node1, node2)
            self.edge_obj[(node1.uid, node2.uid)] = edge_obj
        if type(edge) is list:
            for e in edge:
                add_single_edge(e)
        else:
            add_single_edge(edge)

    def connect_ports_and_create_edge(self, port1, port2):
        e = Edge(vertices=(port1, port2))
        self.add_edge_obj(e)

    def connect_two_nodes_create_edges_create_ports(self, node1, node2):
        """ """
        p1 = ElectricalPort()
        node1.ports[p1.uid] = p1
        self.add_node_obj(node1) # updates
        p2 = ElectricalPort()
        node2.ports[p2.uid] = p2
        self.add_node_obj(node2) # updates
        self.connect_ports_and_create_edge(p1, p2)

    def connect_port_to_node_create_edges_create_port(self, port, node):
        """ """
        p = ElectricalPort()
        node.ports[p.uid] = p
        self.add_node_obj(node) # updates
        self.connect_ports_and_create_edge(port, p)

    def lookup_node_from_port(self, port):
        """ Returns node that a specified port belongs to, if the port belongs to a node."""
        for _, node in self.node_obj.items():
            for _, p in node.ports.items():
                if port == p:
                    return node
        raise ConfigurationError('Port is not part of any node.')

    def check_node_connection(self, node1, node2):
        """ Checks if there is an existing edge between two nodes"""
        connecting_edge = self.edge_obj.get((node1.uid, node2.uid))
        if connecting_edge:
            return True
        else:
            connecting_edge = self.edge_obj.get((node2.uid, node1.uid))
            if connecting_edge:
                return True
            else:
                return False

    def get_port_on_path(self, node1, node2):
        """ Gets port on node1 that forms edge connecting node1 and node2 """
        connecting_edge = self.edge_obj.get((node1.uid, node2.uid))
        if connecting_edge:
            return connecting_edge.vertices[0]
        else:
            connecting_edge = self.edge_obj.get((node2.uid, node1.uid))
            if connecting_edge:
                return connecting_edge.vertices[1]

    def get_ports_on_edge_from_nodes(self, node1, node2):
        """ Gets edge ports from node1, node2 """
        connecting_edge = self.edge_obj.get((node1.uid, node2.uid))
        if connecting_edge:
            node1_port = connecting_edge.vertices[0]
            node2_port = connecting_edge.vertices[1]
            return node1_port, node2_port
        else:
            connecting_edge = self.edge_obj.get((node2.uid, node1.uid))
            if connecting_edge:
                node1_port = connecting_edge.vertices[1]
                node2_port = connecting_edge.vertices[0]
                return node1_port, node2_port

    def get_sources_and_sinks(self):
        sources_or_sinks = set()
        for _, path in self.paths.items():
            sources_or_sinks.add(path.vertices[0])
            sources_or_sinks.add(path.vertices[-1])
        return sources_or_sinks

    def create_path_objects(self, sources, sinks):
        all_paths = {}
        for source_node in sources:
            for sink_node in sinks:
                if source_node is not sink_node:
                    simple_paths = nx.all_simple_paths(self, source_node, sink_node)
                    simple_edges = nx.all_simple_edge_paths(self, source_node, sink_node)
                    for vertex_list, edge_list in zip(simple_paths, simple_edges):
                        p = Path(vertices=vertex_list)  # Create path objects
                        p.units = Units.KW
                        for edge in edge_list:
                            edge_obj = self.get_ports_on_edge_from_nodes(edge[0], edge[1])
                            assert edge_obj[0].units == Units.KW
                            assert edge_obj[1].units == Units.KW
                            p.edge_ports.append(edge_obj)
                        p.start_port = p.edge_ports[0][0]
                        p.end_port = p.edge_ports[-1][-1]
                        all_paths[tuple(vertex_list)] = p

        self.paths = all_paths


class ConfigurationError(Exception):
    pass


class Port(object):
    def __init__(self):
        self.uid = uuid.uuid4()
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.initial_value = 0
        self.port_name = 'port_' + str(self.uid)
        # Used to define the nature of import / export directions and constraints
        self.flows = Flows.NA  # What flow directions are possible (import, export, both)
        self.import_constraint = FlowConstraint.NA
        self.import_constraint_value = None
        self.export_constraint = FlowConstraint.NA
        self.export_constraint_value = None
        self.installation_capex = 0
        self.active_periods = None
        self.slack = False

    def set_flow_constraints(self, max_import, max_export, slack=False):
        if max_import is not None:
            self.import_constraint = FlowConstraint.Fixed
        else:
            self.import_constraint = FlowConstraint.NoConstraint
        self.import_constraint_value = max_import

        if max_export is not None:
            self.export_constraint = FlowConstraint.Fixed
        else:
            self.export_constraint = FlowConstraint.NoConstraint
        self.export_constraint_value = max_export
        self.slack = slack

    def verify_port(self):
        """ Used to verify that a port has been set up appropriately"""
        if self.flows is Flows.NA:
            raise ConfigurationError("The flows value cannot be set to a value of NA.")

        if (self.flows is Flows.Import) or (self.flows is Flows.Both):
            if self.import_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Import FlowConstraint cannot be set to a value of NA.")
            if self.import_constraint is FlowConstraint.Fixed and self.import_constraint_value is None:
                raise ConfigurationError(
                    "The Import flow constraint value cannot be set to None when an Import constraint exists.")

        if (self.flows is Flows.Export) or (self.flows is Flows.Both):
            if self.export_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Export FlowConstraint cannot be set to a value of NA.")
            if self.export_constraint is FlowConstraint.Fixed and self.export_constraint_value is None:
                raise ConfigurationError(
                    "The Export flow constraint value cannot be set to None when an Export constraint exists.")

        if self.opt_type is OptimisationType.NA:
            raise ConfigurationError(
                "The Optimisation Type has to be configured before instantiation.")

        if self.units is Units.NA:
            raise ConfigurationError("The Units parameter has to be configured before instantiation.")

        if self.export_constraint_value is not None:
            if type(self.export_constraint_value) is int or type(self.export_constraint_value) is float:
                if self.export_constraint_value > 0:
                    raise ConfigurationError('Enter export constraint using positive load convention.')
            else:
                for i in self.export_constraint_value:
                    if i > 0:
                        raise ConfigurationError('Enter export constraint using positive load convention.')

        if self.import_constraint_value is not None:
            if type(self.import_constraint_value) is int or type(self.import_constraint_value) is float:
                if self.import_constraint_value < 0:
                    raise ConfigurationError('Enter import constraint using positive load convention.')
            else:
                for i in self.import_constraint_value:
                    if i < 0:
                        raise ConfigurationError('Enter import constraint using positive load convention.')


    def initialise_port(self, model):

        domain = en.Reals
        if self.flows is Flows.Export:
            domain = en.NonPositiveReals
        elif self.flows is Flows.Import:
            domain = en.NonNegativeReals

        if self.opt_type is OptimisationType.Parameter:
            setattr(model, self.port_name,
                    en.Param(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

        if self.opt_type is OptimisationType.Variable:
            setattr(model, self.port_name,
                    en.Var(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

        # Import/export capacity constraint rules
        def import_cap_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.import_con_val)[p, t]

        def export_cap_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.export_con_val)[p, t]

        def import_cap_rule_slack(model, p, t):
            return getattr(model, self.port_name)[p, t] + getattr(model, self.import_slack)[p, t] <= \
                   getattr(model, self.import_con_val)[p, t]

        def export_cap_rule_slack(model, p, t):
            return getattr(model, self.port_name)[p, t] + getattr(model, self.export_slack)[p, t] >= \
                   getattr(model, self.export_con_val)[p, t]

        def export_cap_slack_max_rule(model, p, t):
            return getattr(model, self.export_slack)[p,t] <= getattr(model, self.export_slack_max)

        def import_cap_slack_max_rule(model, p, t):
            return getattr(model, self.import_slack)[p,t] >= getattr(model, self.import_slack_max)

        def generate_array_cons(val):
            d = {}
            if (type(val) is int) or (type(val) is float):
                for i in model.Time:
                    d[(0, i)] = val
            else:
                for i in model.Time:
                    d[(0, i)] = val[i]
            return d

        if self.import_constraint is FlowConstraint.Fixed:
            con_name = 'import_con_' + self.port_name
            self.import_con_val = f"import_con_val_{self.port_name}"
            constraint_array = generate_array_cons(self.import_constraint_value)
            setattr(model, self.import_con_val, en.Param(model.Expansion, model.Time, initialize=constraint_array, domain=en.NonNegativeReals))

            if self.slack is True:
                self.import_slack = 'import_slack_' + self.port_name
                setattr(model, self.import_slack,
                        en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule_slack))
                self.import_slack_max = 'import_slack_max_' + self.port_name
                con_name = 'import_con_max_' + self.port_name
                setattr(model, self.import_slack_max,
                        en.Var(initialize=0, domain=en.NonPositiveReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_slack_max_rule))
            else:
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule))
        if self.export_constraint is FlowConstraint.Fixed:
            con_name = 'export_con_' + self.port_name
            self.export_con_val = f"export_con_val_{self.port_name}"
            constraint_array = generate_array_cons(self.export_constraint_value)
            setattr(model, self.export_con_val, en.Param(model.Expansion, model.Time, initialize=constraint_array, domain=en.NonPositiveReals))

            if self.slack is True:
                self.export_slack = 'export_slack_' + self.port_name
                setattr(model, self.export_slack,
                        en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule_slack))
                self.export_slack_max = 'export_slack_max_' + self.port_name
                con_name = 'export_con_max_' + self.port_name
                setattr(model, self.export_slack_max,
                        en.Var(initialize=0, domain=en.NonNegativeReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_slack_max_rule))
            else:
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule))

        if self.active_periods is not None:
            self.active = 'active_' + self.port_name
            setattr(model, self.active, en.Param(model.Expansion, model.Time, initialize=self.active_periods, domain=en.Binary))

            def on_off_rule1(model, p, t):
                return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * model.bigM

            def on_off_rule2(model, p, t):
                return getattr(model, self.port_name)[p, t] >= - getattr(model, self.active)[p, t] * model.bigM

            setattr(model, f"active_con1_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=on_off_rule1))
            setattr(model, f"active_con2_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=on_off_rule2))

    def constrain_pos_neg(self, model):

        self.pos = positive_variable_component + self.port_name
        self.neg = negative_variable_component + self.port_name

        setattr(model, self.pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))

        self.is_pos = 'is_pos_' + self.port_name
        setattr(model, self.is_pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        con_rule = self.factory_pos_neg_flows(self.port_name, self.pos, self.neg)
        con_name = positive_variable_component + negative_variable_component + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

        def only_pos_or_neg_one(model, p, t):
            return getattr(model, self.pos)[p, t] <= getattr(model, self.is_pos)[p, t] * model.bigM

        def only_pos_or_neg_two(model, p, t):
            return getattr(model, self.neg)[p, t] >= (getattr(model, self.is_pos)[p, t] - 1)* model.bigM

        setattr(model, f"pos_neg_con1_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_one))

        setattr(model, f"pos_neg_con2_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_two))

    def factory_pos_neg_flows(self, var_name, pos_name, neg_name):

        def constraint(model, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == \
                   (getattr(model, pos_name)[expansion_interval, time_interval] +
                    getattr(model, neg_name)[expansion_interval, time_interval])

        return constraint

    def add_initial_value(self, initial_value):
        self.initial_value = initial_value

    def add_initial_value_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)

    def add_active_periods_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.active_periods = t

    def add_objective(self, model):
        objective = 0
        if self.slack is True:
            if hasattr(self, 'import_slack'):
                objective += -1 * getattr(model, self.import_slack_max) * model.bigM
                objective += -1 * sum(getattr(model, self.import_slack)[p, t] for p in model.Expansion for t in model.Time) * model.bigM*0.1
            if hasattr(self, 'export_slack'):
                objective += getattr(model, self.export_slack_max) * model.bigM
                objective += sum(getattr(model, self.export_slack)[p, t] for p in model.Expansion for t in model.Time) * model.bigM*0.1
        return objective


class Node(object):
    """Nodes are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented."""

    def __init__(self):
        self.uid = uuid.uuid4()
        self.node_rule = NodeRule.NA
        self.ports = {}  # 'port_name: port'
        self.node_name = 'node_' + str(self.uid)
        self.transformations = {}
        self.named_ports = []

    def add_named_electrical_ports(self, name_list):
        if type(name_list) is not list:
            return ConfigurationError('Please enter named ports as list of port names.')
        for name in name_list:
            self.ports[name] = ElectricalPort()

    def add_transformation(self, transformation_obj):
        self.transformations[transformation_obj.uid] = transformation_obj

    def add_emission_transformation(self, emitting_port, carbon_port, emission_factor):
        # Create appropriate transformation
        t = Transform()
        if carbon_port not in self.ports.values():
            self.ports['CO2'] = carbon_port
        t.add_lhs_term(carbon_port, TransformRule.Both, 1)
        t.add_rhs_term(emitting_port, TransformRule.NegativeComponent, emission_factor)
        self.add_transformation(t)
        self.node_rule = NodeRule.Transform

    def verify_node(self):
        if self.node_rule is NodeRule.NA and len(self.ports) > 1:
            raise ConfigurationError('NodeRule cannot be NA if node has more than one port.')

        if self.node_rule == NodeRule.Transform:
            if not self.transformations:
                raise ConfigurationError(
                    "Node has Transform rule but Transformation object(s) has not been added to node.")

    def initialise_node(self, model):
        pass

    def num_ports(self):
        return len(self.ports)


# High Level definitions of asset types
class Source(Port):
    """ A source of a commodity. """

    def __init__(self):
        super(Source, self).__init__()
        self.flows = Flows.Export
        self.opt_type = OptimisationType.Parameter


class Sink(Port):
    """ The sink for a commodity. """

    def __init__(self):
        super(Sink, self).__init__()
        self.flows = Flows.Import
        self.opt_type = OptimisationType.Parameter

    def add_sink_profile(self, electrical_demand):
        self.add_initial_value(electrical_demand)

    def add_sink_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)


class Storage(Port):
    """ Storage for a commodity. """

    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 initial_state_of_charge
                 ):
        super(Storage, self).__init__()
        self.flows = Flows.Both
        self.opt_type = OptimisationType.Variable
        self.import_constraint = FlowConstraint.Fixed
        self.import_constraint_value = charging_power_limit
        self.export_constraint = FlowConstraint.Fixed
        self.export_constraint_value = discharging_power_limit
        # Energy Storage Characteristics
        self.max_capacity = max_capacity
        self.depth_of_discharge_limit = depth_of_discharge_limit
        # DC Power Characteristics
        self.charging_power_limit = charging_power_limit
        self.discharging_power_limit = discharging_power_limit
        self.charging_efficiency = charging_efficiency
        self.discharging_efficiency = discharging_efficiency
        # Derived Values
        self.capacity = self.calc_capacity()
        # Initial state of charge
        self.initial_state_of_charge = initial_state_of_charge
        self.fixed_storage_capacity = True
        self.var_opex = 0
        self.regularise = False
        # next variable is for allowing soc to go below min so as to avoid optimisation failing if there infeasible ev trips
        self.enable_trip_slack = False
        # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
        self.soc_conserv = None
        self.soc_conserv_cost = None
        self.available = None

    def initialise_port(self, model):
        super(Storage, self).initialise_port(model)

        self.soc_value = 'storage_soc_' + self.port_name
        # if not self.enable_min_soc_slack:
        setattr(model, self.soc_value,en.Var(model.Expansion, model.Time, initialize=0, bounds=(0, self.max_capacity)))  # Actual SOC
        # else:
        #     setattr(model, self.soc_value, en.Var(model.Expansion, model.Time, initialize=0, bounds=(None, self.max_capacity)))

        def soc_conservative_rule(model, p, t): # a rule for enforcing conservativness while plugged in
            if self.available[t]:
                return getattr(model, self.soc_value)[p,t] + getattr(model, self.cons_slack)[p,t] - self.soc_conserv >= 0
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            assert self.soc_conserv_cost is not None, 'soc_conserv requires soc_conserv_cost'
            assert self.available is not None, 'soc_conserve requires available'
            con_name = 'cons_soc' + self.port_name
            self.cons_slack = 'con_slack' + self.port_name
            setattr(model, self.cons_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=soc_conservative_rule))

        # def min_soc_rule_slack(model,p,t):    # ensure soc stays above min charge but has slack variable for EV infeasible trips
        #     return getattr(model, self.soc_value)[p, t] + getattr(model, self.min_soc_slack) >= 0

        self.optimised_storage_capacity = 'optimised_storage_capacity_' + self.port_name
        if self.fixed_storage_capacity is False:
            setattr(model, self.optimised_storage_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.optimised_storage_capacity,
                    en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

        def cap_limit(model, p, t):  # Ensure SOC is within max capacity
            return getattr(model, self.soc_value)[p, t] <= getattr(model, self.optimised_storage_capacity)

        setattr(model, f"cap_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=cap_limit))

        def charging_limit_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] <= self.charging_power_limit

        setattr(model, f"charge_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=charging_limit_rule))

        def discharging_limit_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] >= self.discharging_power_limit

        setattr(model, f"discharge_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=discharging_limit_rule))

        def SOC_rule(model, p, t):
            if t == 0:
                return getattr(model, self.soc_value)[p, t] == self.initial_state_of_charge + \
                       getattr(model, self.pos)[p, t] * (model.interval_duration / 60) * self.charging_efficiency + \
                       getattr(model, self.neg)[p, t] * (model.interval_duration / 60) / self.discharging_efficiency

            else:
                return getattr(model, self.soc_value)[p, t] == getattr(model, self.soc_value)[p, t - 1] + \
                       getattr(model, self.pos)[p, t] * (model.interval_duration / 60) * self.charging_efficiency + \
                       getattr(model, self.neg)[p, t] * (model.interval_duration / 60) / self.discharging_efficiency

        def SOC_rule_slack(model, p, t):
            if t == 0:
                return getattr(model, self.soc_value)[p, t] == self.initial_state_of_charge + \
                       getattr(model, self.pos)[p, t] * (model.interval_duration / 60) * self.charging_efficiency + \
                       getattr(model, self.neg)[p, t] * (model.interval_duration / 60) / self.discharging_efficiency + \
                       getattr(model, self.trip_slack)[p, t]

            else:
                return getattr(model, self.soc_value)[p, t] == getattr(model, self.soc_value)[p, t - 1] + \
                       getattr(model, self.pos)[p, t] * (model.interval_duration / 60) * self.charging_efficiency + \
                       getattr(model, self.neg)[p, t] * (model.interval_duration / 60) / self.discharging_efficiency+ \
                       getattr(model, self.trip_slack)[p, t]

        def SOC_rule_perfect_efficiency_slack(model, p, t):
            if t == 0:
                return getattr(model, self.soc_value)[p, t] == self.initial_state_of_charge + \
                       getattr(model, self.port_name)[p, t] * (model.interval_duration / 60) \
                       + getattr(model, self.trip_slack)[p, t]
            else:
                return getattr(model, self.soc_value)[p, t] == getattr(model, self.soc_value)[p, t - 1] + \
                       getattr(model, self.port_name)[p, t] * (model.interval_duration / 60) + \
                       getattr(model, self.trip_slack)[p, t]

        def SOC_rule_perfect_efficiency(model, p, t):
            if t == 0:
                return getattr(model, self.soc_value)[p, t] == self.initial_state_of_charge + \
                       getattr(model, self.port_name)[p, t] * (model.interval_duration / 60)
            else:
                return getattr(model, self.soc_value)[p, t] == getattr(model, self.soc_value)[p, t - 1] + \
                       getattr(model, self.port_name)[p, t] * (model.interval_duration / 60)

        if self.enable_trip_slack is True:
            # con_name = 'min_soc_con_' + self.port_name
            self.trip_slack = 'trip_slack_' + self.port_name
            setattr(model, self.trip_slack,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            # setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=min_soc_rule_slack))
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(model, f"soc_lim_trip_slack{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency_slack))
            else:
                self.constrain_pos_neg(model)
                setattr(model, f"soc_lim_trip_slack{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=SOC_rule_slack))
        else:
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(model, f"soc_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency))
            else:
                self.constrain_pos_neg(model)
                setattr(model, f"soc_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=SOC_rule))

    def calc_capacity(self):
        capacity = self.max_capacity
        if 0 <= self.depth_of_discharge_limit <= 1:
            # Assume we have a decimal representation of the dod limit
            capacity *= (1 - self.depth_of_discharge_limit)
        elif 1 < self.depth_of_discharge_limit <= 100:
            # Assume we have a percentage representation of the dod limit
            capacity *= (1 - self.depth_of_discharge_limit / 100.0)
        else:
            raise ConfigurationError('The DoD limit should be between 0 - 100')

        return capacity

    def add_objective(self, model):
        super(Storage, self).add_objective(model)
        objective = 0

        # To get unique solution
        if self.regularise is True:
            objective += sum(
                getattr(model, self.pos)[p, t] * getattr(model, self.pos)[p, t] + \
                getattr(model, self.neg)[p, t] * getattr(model, self.neg)[p, t]
                for p in model.Expansion for t in model.Time) * 0.0000001

        # Storage capex
        objective += getattr(model, self.optimised_storage_capacity) * self.installation_capex

        if self.enable_trip_slack:
            objective += sum(getattr(model, self.trip_slack)[p,t] for p in model.Expansion for t in model.Time ) * model.bigM * 20  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            objective += sum(getattr(model, self.cons_slack)[p,t] for p in model.Expansion for t in model.Time) * self.soc_conserv_cost

        return objective


class ElectricalDemand(Sink):
    """ Fixed electrical demand"""

    def __init__(self):
        super(ElectricalDemand, self).__init__()
        self.units = Units.KW
        self.import_constraint = FlowConstraint.NoConstraint

    def add_demand_profile(self, electrical_demand):
        self.add_initial_value(electrical_demand)

    def add_demand_profile_from_array(self, array, expansion_periods):
        if type(array) is np.ndarray:
            assert (array >= 0).all(), 'power demand must be non negative'
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)


class ElectricalGeneration(Source):
    """ Electrical generation which can be fixed (non-curtailable) or variable (curtailable) """

    def __init__(self):
        super(ElectricalGeneration, self).__init__()
        self.units = Units.KW
        self.export_constraint = FlowConstraint.NoConstraint
        self.curtailable = False

    def add_generation_profile(self, generation):
        self.add_initial_value(generation)

    def add_generation_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)

    def initialise_port(self, model):
        self.port_name_max = 'port_max_' + self.port_name
        setattr(model, self.port_name_max, en.Param(model.Expansion, model.Time,
                                                    initialize=self.initial_value, domain=en.NonPositiveReals))
        setattr(model, self.port_name, en.Var(model.Expansion, model.Time,
                                              initialize=self.initial_value, domain=en.NonPositiveReals))
        if self.curtailable:
            def gen_less_than_max_gen(model, p, t):
                return getattr(model, self.port_name)[p, t] >= getattr(model, self.port_name_max)[p, t]

            setattr(model, f"cons_{self.port_name}_curtailment", en.Constraint(model.Expansion, model.Time, rule=gen_less_than_max_gen))
        else:
            # TODO This could be simplified to only set solar_p as a Param on initialisation
            def gen_equal_max_gen(model, p, t):
                return getattr(model, self.port_name)[p, t] == getattr(model, self.port_name_max)[p, t]

            setattr(model, f"cons_{self.port_name}_curtailment",
                    en.Constraint(model.Expansion, model.Time, rule=gen_equal_max_gen))


class ElectricalStorage(Storage):
    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 initial_state_of_charge
                 ):
        super(ElectricalStorage, self).__init__(max_capacity,
                                                depth_of_discharge_limit,
                                                charging_power_limit,
                                                discharging_power_limit,
                                                charging_efficiency,
                                                discharging_efficiency,
                                                initial_state_of_charge)
        self.units = Units.KW


class ElectricalNode(Node):

    def __init__(self):
        super(ElectricalNode, self).__init__()
        self.units = Units.KW


class ElectricalTellegenNode(ElectricalNode):
    """A node that implements a Kirchoff / Tellegen constraint requiring that electrical power is conserved"""

    def __init__(self):
        super(ElectricalTellegenNode, self).__init__()
        self.node_rule = NodeRule.Tellegen


class ElectricalPort(Port):
    """ Flexible port """

    def __init__(self):
        super(ElectricalPort, self).__init__()
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW


class CarbonSource(Port):
    """ For doing carbon emissions from an asset (node) """

    def __init__(self):
        super(CarbonSource, self).__init__()
        self.flows = Flows.Export
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.CO2


class CarbonSink(Port):
    """ For sinking carbon emissions into an aggregation node """

    def __init__(self):
        super(CarbonSink, self).__init__()
        self.flows = Flows.Import
        self.import_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.CO2


class CarbonAggregation(Node):

    def __init__(self):
        super(CarbonAggregation, self).__init__()
        aggregation_port = CarbonSink()
        self.ports['sum'] = aggregation_port
        setattr(self, 'sum', aggregation_port)

    def add_aggregation_transformation(self):
        # Create appropriate transformation
        t = Transform()
        for port_name, port_obj in self.ports.items():
            if port_name != 'sum':
                t.add_lhs_term(port_obj, TransformRule.PositiveComponent, 1)
        t.add_rhs_term(self.ports['sum'], TransformRule.PositiveComponent, 1)
        self.add_transformation(t)
        self.node_rule = NodeRule.Transform

    def verify_node(self):
        self.add_aggregation_transformation()
        super(CarbonAggregation, self).verify_node()


class ControlledLoadOrGen(Port):
    """ A controlled load or generation has a max/min power, as well as a max/min utilisation.
    The load/generation must be operated within the min and max utilisation (per time unit). """

    def __init__(self,
                 max_power,
                 min_power,
                 min_utilisation,
                 max_utilisation):
        super(ControlledLoadOrGen, self).__init__()
        self.min_utilisation = min_utilisation   # Per time unit (minute)
        self.max_utilisation = max_utilisation
        self.max_power = max_power
        self.min_power = min_power
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW

    def initialise_port(self, model):

        super(ControlledLoadOrGen, self).initialise_port(model)

        def min_power_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] >= self.min_power

        setattr(model, f"cons_{self.port_name}_min_power",
                en.Constraint(model.Expansion, model.Time, rule=min_power_rule))

        def max_power_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] <= self.max_power

        setattr(model, f"cons_{self.port_name}_max_power",
                en.Constraint(model.Expansion, model.Time, rule=max_power_rule))

        if self.min_utilisation is not None:
            def sum_of_energy_must_be_greater_than_min(model):
                return sum(getattr(model, self.port_name)[p, i] * model.interval_duration / 60.0
                           for p in model.Expansion for i in model.Time) >= \
                       self.min_utilisation * self.max_power * model.interval_duration * model.number_of_intervals / 60.0

            setattr(model, f"cons_{self.port_name}_min_utilisation_req",
                    en.Constraint(rule=sum_of_energy_must_be_greater_than_min))

        if self.max_utilisation is not None:
            def sum_of_energy_must_be_less_than_max(model):
                return sum(getattr(model, self.port_name)[p, i] * model.interval_duration / 60.0
                           for p in model.Expansion for i in model.Time) <= \
                       self.max_utilisation * self.max_power * model.interval_duration * model.number_of_intervals / 60.0

            setattr(model, f"cons_{self.port_name}_max_utilisation_req",
                    en.Constraint(rule=sum_of_energy_must_be_less_than_max))

    def add_demand_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)


class ControlledLoad(ControlledLoadOrGen):

    def __init__(self,
                 max_power,
                 min_power,
                 min_utilisation,
                 max_utilisation
                 ):
        super(ControlledLoad, self).__init__(max_power,
                                             min_power,
                                             min_utilisation,
                                             max_utilisation)

    def verify_port(self):
        if self.max_power < 0 or self.min_power < 0:
            raise ConfigurationError(
                'For controlled load asset, enter max and min power using positive load convention (i.e. positive).')


class ControlledGen(ControlledLoadOrGen):

    def __init__(self,
                 max_power,
                 min_power,
                 min_utilisation,
                 max_utilisation
                 ):
        super(ControlledGen, self).__init__(max_power,
                                            min_power,
                                            max_utilisation,
                                            min_utilisation)

    def verify_port(self):
        if self.max_power > 0 or self.min_power > 0:
            raise ConfigurationError(
                'For controlled gen asset, enter max and min power using positive load convention (i.e. negative).')


class CarbonSinkNode(Node):

    def __init__(self):
        super(CarbonSinkNode, self).__init__()
        self.node_rule = NodeRule.Custom

    def verify_node(self):
        for port in self.ports.values():
            if port.units is not Units.CO2:
                raise ConfigurationError('All ports on carbon sink node must have carbon units.')


class Inverter(ElectricalNode):
    """ An inverter is a node with one AC port and at least one DC port.
    Flows from AC to DC, and DC to AC, are subject to conversion efficiencies."""

    def __init__(self,
                 max_import,
                 max_export,
                 dc_ac_efficiency,
                 ac_dc_efficiency):
        super(Inverter, self).__init__()
        self.dc_ac_efficiency = dc_ac_efficiency
        self.ac_dc_efficiency = ac_dc_efficiency
        self.dc_ports = {}
        self.ac_port = None
        self.max_inverter_import = max_import
        self.max_inverter_export = max_export
        self.node_rule = NodeRule.Custom # Todo fix this

    def add_dc_port(self, port_name):
        p = ElectricalPort()
        self.dc_ports[port_name] = p
        self.ports[port_name] = p

    def add_ac_port(self, port_name):
        if self.ac_port:
            raise ConfigurationError('AC port already specified for this inverter.')
        else:
            p = ElectricalPort()
            p.set_flow_constraints(max_export=self.max_inverter_export, max_import=self.max_inverter_import)
            self.ac_port = p
            self.ports[port_name] = p

    def initialise_node(self, model):

        for port in self.ports.values(): # Make sure all ports have pos/neg constraint
            port.constrain_pos_neg(model)

        def inverter_ac_output_must_track_efficiency(model, p, t): # Apply efficiency constraints
            dc_pos = 0
            dc_neg = 0
            for dc_port in self.dc_ports.values():
                dc_pos += getattr(model, dc_port.pos)[p, t]
                dc_neg += getattr(model, dc_port.neg)[p, t]

            return getattr(model, self.ac_port.pos)[p, t] * self.ac_dc_efficiency + \
                   getattr(model, self.ac_port.neg)[p, t] / self.dc_ac_efficiency == - (dc_pos + dc_neg)

        setattr(model, f"con_inverter_{self.node_name}", en.Constraint(
            model.Expansion, model.Time, rule=inverter_ac_output_must_track_efficiency))


class EVChargingStation(ElectricalNode):
    # Todo is this a tellegen node?

    def __init__(self,
                 max_export_power,
                 max_import_power,
                 num_chargers,
                 charger_max_export,
                 charger_max_import):
        super(EVChargingStation, self).__init__()
        self.num_chargers = num_chargers
        self.add_charging_ports(self.num_chargers, charger_max_export, charger_max_import)
        self.max_export_power = max_export_power
        self.max_import_power = max_import_power

    def add_charging_ports(self, num_chargers, charger_max_export, charger_max_import):
        for i in range(num_chargers):
            evc = EVCharger(
                export_constraint_value=charger_max_export,
                import_constraint_value=charger_max_import)
            charging_port_name = str(i)
            self.ports[charging_port_name] = evc

    def initialise_node(self, model):
        # Todo apply max power constraints
        pass


class EVCharger(ElectricalPort):
    """ An EV Charger is a flexible electrical port with import/export constraints."""

    def __init__(self,
                 export_constraint_value,
                 import_constraint_value
                 ):
        super(EVCharger, self).__init__()
        self.flows = Flows.Both
        self.export_constraint = FlowConstraint.Fixed
        self.export_constraint_value = export_constraint_value
        self.import_constraint = FlowConstraint.Fixed
        self.import_constraint_value = import_constraint_value


class ElectricVehicle(Node):

    def __init__(self):
        super(ElectricVehicle, self).__init__()
        self.units = Units.KW

    def initialise_node(self, model):
        super(ElectricVehicle, self).initialise_node(model)


class Edge(object):
    """ Edges are used to connect nodes. For an edge (x, y) where x and y are nodes,
    the edge value is equal to the flow from x->y plus the flow from y->x. """

    def __init__(self,
                 vertices):
        self.uid = uuid.uuid4()
        self.edge_name = 'edge_' + str(self.uid)
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.vertices = vertices
        self.tariff = None

    def add_vertices(self, obj1, obj2):
        self.vertices = (obj1, obj2)

    def verify_edge(self):
        port1 = self.vertices[0]
        port2 = self.vertices[1]

        if (port1.flows is Flows.Export) and (port2.flows is Flows.Export):
            raise ConfigurationError('Port flow constraints do not allow any flow along the edge.')
        if (port1.flows is Flows.Import) and (port2.flows is Flows.Import):
            raise ConfigurationError('Port flow constraints do not allow any flow along the edge.')

    def initialise_edge(self, model):

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        con_rule1 = self.factory_constraint_edge_builder(port1.port_name, port2.port_name)
        con_name = 'edge_con_' + port1.port_name + '_' + port2.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule1))

    def factory_constraint_edge_builder(self, obj1, obj2):
        def constraint(model, expansion_interval, time_interval):
            return getattr(model, obj1)[expansion_interval, time_interval] + \
                   getattr(model, obj2)[expansion_interval, time_interval] == 0
        return constraint

    def add_objective(self, model):
        # Todo add edge tariffs here
        return 0

    def add_initial_edge_capacity(self, initial_capacity):
        self.initial_edge_capacity = initial_capacity


class Transform(object):
    """ An object for carrying a generic linear node transformation."""

    def __init__(self):
        self.uid = uuid.uuid4()
        self.transform_name = 'transform_' + str(self.uid)
        self.rhs = []
        self.lhs = []

    def add_rhs_term(self, var, rule, weight):
        term = {'var': var, 'rule': rule, 'weight': weight}
        self.rhs.append(term)

    def add_lhs_term(self, var, rule, weight):
        term = {'var': var, 'rule': rule, 'weight': weight}
        self.lhs.append(term)

    def initialise_transform(self, model):
        # Check if we need to create pos/neg components
        for i in range(len(self.lhs)):
            rule = self.lhs[i]['rule']
            if rule is not TransformRule.Both:
                var = self.lhs[i]['var']
                if not hasattr(var, 'pos'):
                    var.constrain_pos_neg(model)

        for i in range(len(self.rhs)):
            rule = self.rhs[i]['rule']
            if rule is not TransformRule.Both:
                var = self.rhs[i]['var']
                if not hasattr(var, 'pos'):
                    var.constrain_pos_neg(model)




class Path(object):
    """ A path is a sequence of distinct vertices (nodes). """

    def __init__(self, vertices):
        self.edge_ports = []
        self.vertices = vertices
        self.uid = uuid.uuid4()
        self.path_name = 'path_' + str(self.uid)
        self.units = Units.KW
        self.start_port = None
        self.end_port = None

    def add_vertices(self, vertex_list):
        if type(vertex_list) is not list:
            raise ConfigurationError('Please enter path vertices (nodes) as a list.')
        self.vertices = vertex_list

    def verify_path(self):
        pass

    def initialise_path(self, model):
        self.flow_value = 'flow_value_' + self.path_name
        setattr(model, self.flow_value, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

    def add_objective(self, model):
        objective = 0

        # To get a unique solution
        objective += sum(getattr(model, self.flow_value)[p, t] for p in model.Expansion for t in model.Time) * \
                     0.00000001

        return objective

# BZ assets

class GasBoiler(Node):

    """ Gas boiler converts gas to thermal energy """

    def __init__(self,
                 gas_to_heat_efficiency):
        super(GasBoiler, self).__init__()
        self.gas_to_heat_efficiency = gas_to_heat_efficiency
        gp = GasPort()
        gp.flows = Flows.Import
        self.ports['gas'] = gp
        hp = ThermalPort()
        hp.flows = Flows.Export
        self.ports['heat'] = hp
        self.add_boiler_transformation(gp, hp, gas_to_heat_efficiency)

    def add_boiler_transformation(self, gas_port, heat_port, gas_to_heat_efficiency):
        # Create appropriate transformation
        t = Transform()
        t.add_lhs_term(heat_port, TransformRule.NegativeComponent, -1)
        t.add_rhs_term(gas_port, TransformRule.PositiveComponent, gas_to_heat_efficiency)
        self.add_transformation(t)
        self.node_rule = NodeRule.Transform

class Chiller(Node):
    """ A chiller is a node that imports electricity and heat, where the amount of heat imported depends on
    a defined coefficient of performance (cop), which is unitless (kW of cooling per kW electrical) """

    def __init__(self,
                 cop):
        super(Chiller, self).__init__()
        self.cop = cop
        ep = ElectricalPort()
        ep.flows = Flows.Import
        self.ports['elec'] = ep
        cp = ThermalPort()
        cp.flows = Flows.Export
        self.ports['cooling'] = cp
        self.add_chiller_transformation(ep, cp, cop)

    def add_chiller_transformation(self, elec_port, cooling_port, cop):
        # Create appropriate transformation
        t = Transform()
        t.add_lhs_term(cooling_port, TransformRule.NegativeComponent, -1)
        t.add_rhs_term(elec_port, TransformRule.PositiveComponent, cop)
        self.add_transformation(t)
        self.node_rule = NodeRule.Transform

class ThermalLoad(Sink):
    """ Positive thermal load is a heating load, neg is a cooling load (ie heat to be removed/exported)"""

    def __init__(self):
        super(ThermalLoad, self).__init__()
        self.units = Units.KWT
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint

class GasPort(Port):

    def __init__(self):
        super(GasPort, self).__init__()
        self.units = Units.J
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable

class ThermalPort(Port):

    def __init__(self):
        super(ThermalPort, self).__init__()
        self.units = Units.KWT
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable



class BulkGrid(Node):

    def __init__(self):
        super(BulkGrid, self).__init__()
        self.ports['grid'] = ElectricalPort()


class BulkGas(Node):

    def __init__(self):
        super(BulkGas, self).__init__()
        self.ports['gas'] = GasPort()




class GasLoad(Sink):

    def __init__(self):
        super(GasLoad, self).__init__()
        self.flows = Flows.Import
        self.units = Units.KW


class GasTellegenNode(Node):

    def __init__(self):
        super(GasTellegenNode, self).__init__()
        self.node_rule = NodeRule.Tellegen
        self.units = Units.J