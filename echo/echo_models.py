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

    def add_subgraph(self, subgraph):
        for _, new_node_obj in subgraph.node_obj.items():
            self.add_node_obj(new_node_obj)
        for _, new_edge_obj in subgraph.edge_obj.items():
            self.add_edge_obj(new_edge_obj)

    def connect_ports_and_create_edge(self, port1, port2):
        e = Edge(vertices=(port1, port2))
        self.add_edge_obj(e)

    def connect_two_nodes_create_edges_create_ports(self, node1, node2):
        """ """
        p1 = ElectricalPort()
        node1.ports[p1.uid] = p1
        self.add_node_obj(node1)  # updates
        p2 = ElectricalPort()
        node2.ports[p2.uid] = p2
        self.add_node_obj(node2)  # updates
        self.connect_ports_and_create_edge(p1, p2)

    def connect_port_to_node_create_edges_create_port(self, port, node):
        """ """
        p = ElectricalPort()
        node.ports[p.uid] = p
        self.add_node_obj(node)  # updates
        self.connect_ports_and_create_edge(port, p)

    def lookup_node_from_port(self, port):
        """ Returns node that a specified port belongs to, if the port belongs to a node."""
        for _, node in self.node_obj.items():
            for _, p in node.ports.items():
                if port == p:
                    return node
        raise ConfigurationError('Port is not part of any node.')

    def get_ports_on_edge_from_nodes(self, node1, node2):
        """ Gets the ports that are on the edge from node1 to node2. """
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
        """ Returns a set that contains all source and sink nodes."""
        sources_or_sinks = set()
        for _, path in self.paths.items():
            sources_or_sinks.add(path.vertices[0])
            sources_or_sinks.add(path.vertices[-1])
        return sources_or_sinks

    def verify_paths(self):
        """ Verifies that our paths meet the assumptions required to correctly do flow tracing."""
        all_nodes = self.get_sources_and_sinks()
        for node in all_nodes:
            for path in self.paths.values():
                if node in path.vertices[1:-1]:
                    # if the source/sink node appears in the middle of another path, the optimiser will fail
                    # A node can't be both a tellegen node and a source/sink node
                    raise ConfigurationError('Source/sink node is being treated as a tellegen node.')

    def create_path_objects(self, sources, sinks, regularise=False):
        """ Creates path objects according to source/sink lists provided."""
        all_paths = {}
        for source_node in sources:
            for sink_node in sinks:
                if source_node is not sink_node:
                    simple_paths = nx.all_simple_paths(self, source_node, sink_node)
                    simple_edges = nx.all_simple_edge_paths(self, source_node, sink_node)
                    for vertex_list, edge_list in zip(simple_paths, simple_edges):
                        p = Path(vertices=vertex_list)  # Create path objects
                        p.regularise = regularise  # For adding regularisation (ie equal sharing) to give a unique solution
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
        self.verify_paths()


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
        self.optional = False

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
            return getattr(model, self.export_slack)[p, t] <= getattr(model, self.export_slack_max)

        def import_cap_slack_max_rule(model, p, t):
            return getattr(model, self.import_slack)[p, t] >= getattr(model, self.import_slack_max)

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
            if self.opt_type is not OptimisationType.Parameter:  # only apply these constraints to variables
                con_name = 'import_con_' + self.port_name
                self.import_con_val = f"import_con_val_{self.port_name}"
                constraint_array = generate_array_cons(self.import_constraint_value)
                setattr(model, self.import_con_val,
                        en.Param(model.Expansion, model.Time, initialize=constraint_array, domain=en.NonNegativeReals))

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
            if self.opt_type is not OptimisationType.Parameter:  # only apply these constraints to variables
                con_name = 'export_con_' + self.port_name
                self.export_con_val = f"export_con_val_{self.port_name}"
                constraint_array = generate_array_cons(self.export_constraint_value)
                setattr(model, self.export_con_val,
                        en.Param(model.Expansion, model.Time, initialize=constraint_array, domain=en.NonPositiveReals))

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
            setattr(model, self.active,
                    en.Param(model.Expansion, model.Time, initialize=self.active_periods, domain=en.Binary))

            def on_off_rule1(model, p, t):
                return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * model.bigM

            def on_off_rule2(model, p, t):
                return getattr(model, self.port_name)[p, t] >= - getattr(model, self.active)[p, t] * model.bigM

            setattr(model, f"active_con1_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=on_off_rule1))
            setattr(model, f"active_con2_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=on_off_rule2))

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
            return getattr(model, self.neg)[p, t] >= (getattr(model, self.is_pos)[p, t] - 1) * model.bigM

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
                objective += -1 * sum(getattr(model, self.import_slack)[p, t] for p in model.Expansion for t in
                                      model.Time) * model.bigM * 0.1
            if hasattr(self, 'export_slack'):
                objective += getattr(model, self.export_slack_max) * model.bigM
                objective += sum(getattr(model, self.export_slack)[p, t] for p in model.Expansion for t in
                                 model.Time) * model.bigM * 0.1
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
        for port in self.ports.values():
            port.verify_port()
            port.initialise_port(model)

    def apply_node_constraints(self, model):

        def reliability(model, p, t):  # Tellegen node rule
            a = 0
            for _, port in node_ports.items():
                b = getattr(model, port.port_name)
                a += b[p, t]
            return a == 0

        def transform(model, p, t):  # Generic transformation node
            def unpack_transform(x):
                expr = 0
                for term in x:
                    transform_rule = term['rule']
                    weight = term['weight']
                    var = term['var']
                    if transform_rule is TransformRule.Both:
                        expr += getattr(model, var.port_name)[p, t] * weight
                    if transform_rule is TransformRule.NegativeComponent:
                        expr += getattr(model, var.neg)[p, t] * weight
                    if transform_rule is TransformRule.PositiveComponent:
                        expr += getattr(model, var.pos)[p, t] * weight
                return expr

            rhs = unpack_transform(current_transform.rhs)
            lhs = unpack_transform(current_transform.lhs)
            return lhs == rhs

        if self.node_rule == NodeRule.Transform:
            for _, current_transform in self.transformations.items():
                current_transform.initialise_transform(model)
                con_name = 'transformation_con_' + current_transform.transform_name
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=transform))
        if self.node_rule == NodeRule.Tellegen:
            node_ports = self.ports
            con_name = 'reliability_con_' + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=reliability))

    def apply_piecewise_node_constraint(self, index_list, var_list, pw, fval, ):

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
        setattr(model, self.soc_value,
                en.Var(model.Expansion, model.Time, initialize=0, bounds=(0, self.max_capacity)))  # Actual SOC

        # else:
        #     setattr(model, self.soc_value, en.Var(model.Expansion, model.Time, initialize=0, bounds=(None, self.max_capacity)))

        def soc_conservative_rule(model, p, t):  # a rule for enforcing conservativness while plugged in
            if self.available[t]:
                return getattr(model, self.soc_value)[p, t] + getattr(model, self.cons_slack)[
                    p, t] - self.soc_conserv >= 0
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            assert self.soc_conserv_cost is not None, 'soc_conserv requires soc_conserv_cost'
            assert self.available is not None, 'soc_conserve requires available'
            con_name = 'cons_soc' + self.port_name
            self.cons_slack = 'con_slack' + self.port_name
            setattr(model, self.cons_slack,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
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

        setattr(model, f"charge_lim_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=charging_limit_rule))

        def discharging_limit_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] >= self.discharging_power_limit

        setattr(model, f"discharge_lim_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=discharging_limit_rule))

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
                       getattr(model, self.neg)[p, t] * (model.interval_duration / 60) / self.discharging_efficiency + \
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
                setattr(model, f"soc_lim_trip_slack{self.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency_slack))
            else:
                self.constrain_pos_neg(model)
                setattr(model, f"soc_lim_trip_slack{self.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=SOC_rule_slack))
        else:
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(model, f"soc_lim_{self.port_name}",
                        en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency))
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
            objective += sum(getattr(model, self.trip_slack)[p, t] for p in model.Expansion for t in
                             model.Time) * model.bigM * 20  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            objective += sum(getattr(model, self.cons_slack)[p, t] for p in model.Expansion for t in
                             model.Time) * self.soc_conserv_cost

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
        if type(array) is np.ndarray:
            assert (array <= 0).all(), 'power generation must be non positive'
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

            setattr(model, f"cons_{self.port_name}_curtailment",
                    en.Constraint(model.Expansion, model.Time, rule=gen_less_than_max_gen))
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
        self.min_utilisation = min_utilisation  # Per time unit (minute)
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
        self.node_rule = NodeRule.Custom  # Todo fix this

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
        super(Inverter, self).initialise_node(model)

        for port in self.ports.values():  # Make sure all ports have pos/neg constraint
            port.constrain_pos_neg(model)

        def inverter_ac_output_must_track_efficiency(model, p, t):  # Apply efficiency constraints
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


class EV(ElectricalTellegenNode):

    def __init__(self,
                 charge_mode,
                 available,
                 usage,
                 connection_port_name,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 initial_state_of_charge,
                 tod_charging,
                 soc_conserv,
                 soc_conserv_cost,
                 trip_slack,
                 interval_duration
                 ):
        super(EV, self).__init__()
        self.charge_mode = charge_mode
        self.available = available
        self.usage = usage
        self.cp_name = connection_port_name
        self.tod_charging = tod_charging

        # EV always has a storage port, set this up correctly
        self.ports['vehicle'] = ElectricalStorage(max_capacity,
                                                  depth_of_discharge_limit,
                                                  charging_power_limit,
                                                  discharging_power_limit,
                                                  charging_efficiency,
                                                  discharging_efficiency,
                                                  initial_state_of_charge)
        self.ports['vehicle'].enable_trip_slack = trip_slack
        # Process any constraints on the storage port
        if soc_conserv is not None:
            assert soc_conserv_cost is not None, 'soc_conserv requires soc_conserve_cost'
            self.ports['vehicle'].soc_conserv = soc_conserv  # kWh
            self.ports['vehicle'].soc_conserv_cost = soc_conserv_cost  # dollars per kwh
            self.ports['vehicle'].available = available

        # EV always has a trip port
        self.ports['usage'] = ElectricalDemand()
        self.ports['usage'].add_demand_profile_from_array(usage, expansion_periods=1)
        # Customise connection point port type based on the charge mode
        if charge_mode == 'V0G':
            self.ports[connection_port_name] = ElectricalGeneration()
            self.process_V0G_charging(interval_duration)
            self.ports[connection_port_name].add_generation_profile_from_array(self.V0G_delta*-1, expansion_periods=1)
        else:
            self.ports[connection_port_name] = ElectricalPort()
            self.ports[connection_port_name].add_active_periods_from_array(available, expansion_periods=1)
            if charge_mode == 'V1G':
                self.ports[connection_port_name].set_flow_constraints(max_import=charging_power_limit, max_export=0.)

    def process_V0G_charging(self, interval_duration):
        success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration)
        # Add results to the ev dict
        self.V0G_delta = ev_delta
        self.V0G_SOC = ev_soc
        # if self.tod_charging is not None:
        #     if success:
        #         self.charge_status = 'success'
        #     else:  # force conv
        #         success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration, force_conv=True)
        #         self.charge_status = 'time of day infeasible, convenience success' if success else 'infeasible'
        #         self.V0G_delta = ev_delta
        #         self.V0G_SOC = ev_soc
        #
        # else:
        self.charge_status = 'success' if success else 'infeasible'
        self.trip_infeasibility = trip_infeasibility

    def V0G_charging(self, interval_duration, force_conv=False):
        """ Convert V0G vehicle (convenience charging) to a soc profile and a power profile if possible."""

        if (self.tod_charging is not None) and (not force_conv):
            self.available = self.available * self.tod_charging
        T = len(self.available)
        soc = np.zeros((T + 1,))
        soc[0] = self.ports['vehicle'].initial_state_of_charge
        trip_infeasibility = np.zeros((T,))
        delta = np.zeros((T,))
        max_capacity = self.ports['vehicle'].max_capacity
        charge_limit = self.ports['vehicle'].charging_power_limit
        charging_efficiency = self.ports['vehicle'].charging_efficiency

        for t in range(T):
            if self.available[t] and (soc[t] < max_capacity):  # available to charge and not at max capacity
                delta[t] = min(charge_limit, (max_capacity - soc[t]) / charging_efficiency / (interval_duration / 60))
                soc[t + 1] = soc[t] + delta[t] * (interval_duration / 60) * charging_efficiency
            else:  # if not available then it might be on a trip and using power
                soc[t + 1] = soc[t] - self.usage[t] * (interval_duration / 60)
            trip_infeasibility[t] = - min(soc[t + 1], 0)
            soc[t + 1] = max(soc[t + 1], 0)

        success = True if (trip_infeasibility.max() == 0) else False

        return success, soc[:-1], delta, trip_infeasibility

    def verify_node(self):
        super(EV, self).verify_node()
        # Check that all the relevant time series data has been added
        if self.charge_mode == 'V0G':
            assert self.ports[self.cp_name].initial_value != 0, 'V0G connection pt port needs demand profile added.'
        else:
            assert self.ports[self.cp_name].active_periods is not None, 'EV connection pt port needs available periods added.'
        assert self.ports['usage'].initial_value != 0, 'EV usage port needs demand profile added.'






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
        self.regularise = False

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

        if self.regularise is True:
            objective += sum(getattr(model, self.flow_value)[p, t] * getattr(model, self.flow_value)[p, t] \
                             for p in model.Expansion for t in model.Time) * 0.0000001

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
    """ A chiller is a node that imports electricity and exports cooling power, where the conversion occurs according
    to a coefficient of performance (COP), which is unitless (kW of cooling energy per kW electrical). We model this
    nonlinear relationship as a piecewise linear function between input electrical power and output cooling power.
     The COP for a chiller depends on the ambient air temperature, and the system loading."""

    def __init__(self,
                 pw_input,
                 pw_output,
                 max_input,
                 max_output,
                 temp_array=None,
                 coeff_array=None,
                 n_breakpoints=4
                 ):
        super(Chiller, self).__init__()
        # Checks
        assert max_input >= 0, 'Enter max input as positive number'
        assert max_output <= 0, 'Enter max output as negative number'
        assert len(pw_input) == len(pw_output), 'Unequal number of input breakpoints and output values'
        assert max(pw_input) == max_input, 'Input breakpoints should be defined up to max input'
        assert max(pw_output) == max_output * -1, 'Output values should be defined up to max output'
        assert len(coeff_array) == 3, 'Coefficients for a quadratic function should be used (ie 3 coefficients).'

        self.max_input = max_input
        self.max_output = max_output
        self.input_breakpoints = pw_input
        self.output_values = pw_output
        if temp_array:
            self.add_temperature_profile_from_array(temp_array)
        if coeff_array:
            self.convert_coeff_array_to_piecewise_function(coeff_array, n_breakpoints=n_breakpoints)

        # Create input electrical port
        ep = ElectricalPort()
        ep.flows = Flows.Import
        ep.import_constraint = FlowConstraint.Fixed
        ep.import_constraint_value = self.max_input
        self.input = ep
        self.ports['input'] = ep

        # Create output thermal port
        cp = ThermalPort()
        cp.flows = Flows.Export
        self.output = cp
        cp.export_constraint = FlowConstraint.Fixed
        cp.export_constraint_value = self.max_output
        self.ports['output'] = cp
        self.node_rule = NodeRule.Custom

    def add_temperature_profile_from_array(self, array, expansion_periods=1):
        # Calculate temperature correction factor
        y = np.subtract(array, np.average(array))
        cf = y / np.linalg.norm(y)
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(cf)):
                t[(ep, i)] = cf[i]
        self.temp_correction_factors = t

    def convert_coeff_array_to_piecewise_function(self, array, n_breakpoints=4):

        xvals = np.linspace(0, self.max_input, n_breakpoints)
        yvals = np.zeros(len(xvals))
        for i in range(len(xvals)):
            yvals[i] = array[0] * xvals[i] ** 2 + array[1] * xvals[i] + array[2]

        self.input_breakpoints = list(xvals)
        self.output_values = list(yvals)

    def initialise_node(self, model):
        super(Chiller, self).initialise_node(model)

    def apply_node_constraints(self, model):
        # let's ignore temperature for now
        # We use a linear approximation of the relationship between cooling capacity in kWt and input power in kW.
        # Otherwise we will have a non-convex constraint, which cplex can't handle

        # todo less hacky way of doing this
        self.dummy = 'dummy_var_' + self.node_name  # this is a nonnegative variable for the piecewise func
        setattr(model, self.dummy, en.Var(model.Expansion, model.Time, domain=en.NonNegativeReals))

        xvar = getattr(model, self.input.port_name)  # x is our input
        yvar = getattr(model, self.dummy)  # y is our dummy output
        for i in range(len(xvar.index_set())):
            xvar[0, i].bounds = (0, self.max_input)
            yvar[0, i].bounds = (0, self.max_output * -1)

        xdata = self.input_breakpoints
        ydata = self.output_values
        setattr(model, 'piecewise_con', en.Piecewise(
            model.Expansion, model.Time,
            yvar, xvar, pw_pts=xdata, pw_constr_type='EQ', f_rule=ydata, pw_repn='SOS2'))

        def node_constraint(model, p, t):
            # add a linear temp correction factor here. temp will also be correlated with cooling load...
            if hasattr(self, 'temp_correction_factors'):
                return getattr(model, self.output.port_name)[p, t] == \
                       (getattr(model, self.dummy)[p, t] - self.temp_correction_factors[p, t]) * -1
            else:
                return getattr(model, self.output.port_name)[p, t] == \
                       (getattr(model, self.dummy)[p, t]) * -1

        con_name = 'transformation_con_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=node_constraint))


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
        self.units = Units.Jps
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


class GasDemand(Sink):

    def __init__(self):
        super(GasDemand, self).__init__()
        self.import_constraint = FlowConstraint.NoConstraint
        self.units = Units.Jps

    def add_demand_profile_from_array(self, array, expansion_intervals):
        self.add_sink_profile_from_array(array, expansion_intervals)


class GasTellegenNode(Node):

    def __init__(self):
        super(GasTellegenNode, self).__init__()
        self.node_rule = NodeRule.Tellegen
        self.units = Units.Jps
