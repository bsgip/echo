import uuid

import networkx as nx
from networkx import Graph
import pyomo.environ as en
from configuration import Units, Flows, FlowConstraint, OptimisationType, NodeRule, TransformRule, \
    ExpansionType, PathRule
from constants import minutes_per_hour, positive_variable_component, negative_variable_component
import numpy as np


class OptimisationGraph(Graph):

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.port_obj = dict()
        self.node_obj = dict()
        self.edge_obj = dict()
        self.storage_expansion_obj = dict()
        self.gen_expansion_obj = dict()
        self.capacity_exp_obj = dict()  # This dict can include edges and ports
        self.path_obj = dict()

    def add_port_obj(self, port_obj):
        self.port_obj[port_obj.uid] = port_obj

    def add_node_obj(self, node_obj):
        self.add_node(node_obj)
        self.node_obj[node_obj.uid] = node_obj
        for _, port in node_obj.ports.items():  # Add any ports within the node
            self.add_port_obj(port)

    def add_edge_obj(self, edge):
        port1 = edge.vertices[0]
        port2 = edge.vertices[1]
        node1 = self.lookup_node_from_port(port1)
        node2 = self.lookup_node_from_port(port2)
        self.add_edge(node1, node2)
        self.edge_obj[(node1.uid, node2.uid)] = edge
        if edge.capacity_expansion is True:
            self.capacity_exp_obj[edge.uid] = edge

    def add_path_obj(self, path_obj):
        path_key = tuple(path_obj.vertices)
        self.path_obj[path_key] = path_obj

    def add_capacity_expansions(self):
        for _, obj in self.port_obj.items():
            if obj.capacity_expansion is True:
                self.capacity_exp_obj[obj.uid] = obj
        for _, obj in self.edge_obj.items():
            if obj.capacity_expansion is True:
                self.capacity_exp_obj[obj.uid] = obj

    def add_asset_expansions(self, expansion_periods):
        # Asset expansions
        nodes_to_add = []
        edges_to_add = []
        for _, node in self.node_obj.items():
            if node.expansion_planning:  # Check if the node has expansion planning
                for i in range(0, self.global_storage_exp_con):
                    new_asset = Node()
                    new_asset.expansion_asset = True  # Designate new asset as an expansion asset
                    if node.storage_planning is True:  # Check if node has storage expansion planning
                        s = ElectricalStorage(max_capacity=150.0,
                                              depth_of_discharge_limit=0,
                                              charging_power_limit=5.0,
                                              discharging_power_limit=-5.0,
                                              charging_efficiency=1,
                                              discharging_efficiency=1,
                                              throughput_cost=0.018,
                                              initial_state_of_charge=0)
                        new_asset.expansion_asset_type = ExpansionType.Storage
                        s.fixed_storage_capacity = False
                        s.existing_port = False
                        self.storage_expansion_obj[new_asset.uid] = new_asset
                    elif node.generator_planning is True:
                        # ToDo allow user to specify details eg generation profile
                        s = ElectricalGeneration()
                        constant_gen = np.array(([1.0] * 96)) * -1
                        gen1 = {}
                        for ep in range(0, expansion_periods):
                            for j, _ in enumerate(constant_gen):
                                gen1[(ep, j)] = constant_gen[i]
                        s.add_generation_profile(gen1)
                        new_asset.expansion_asset_type = ExpansionType.Generation
                        s.fixed_capacity = True
                        s.existing_port = False
                        self.gen_expansion_obj[new_asset.uid] = new_asset
                    else:
                        raise ConfigurationError('Expansion planning is on but no expansion type is set to True.')

                    new_asset.ports['exp_' + str(i)] = s  # Connect new port to new node
                    s.lifetime = 2
                    s.installation_capex = node.storage_planning_capex
                    p = ElectricalPort()  # Make a new port on the expansion node
                    port_name = 'exp_' + str(i) + '_' + node.node_name
                    node.ports[port_name] = p
                    node.exp_port_names.append(port_name)
                    expansion_edge = Edge()  # Create edge object
                    expansion_edge.add_vertices(p, s)
                    edges_to_add.append(expansion_edge)
                    self.add_port_obj(s)
                    self.add_port_obj(p)
                    nodes_to_add.append(new_asset)  # Keep list of new nodes to add to graph outside this loop
        for i in nodes_to_add:
            self.add_node_obj(i)
        for i in edges_to_add:
            self.add_edge_obj(i)

    def lookup_node_from_port(self, port):
        """ Returns node that a specified port belongs to, if the port belongs to a node."""
        for _, node in self.node_obj.items():
            for _, p in node.ports.items():
                if port == p:
                    return node
        raise ConfigurationError('Port is not part of any node.')

    def lookup_edge_from_port(self, port):
        """ Returns edge containing the specified port, if an edge exists."""
        for _, e in self.edge_obj.items():
            p1 = e.vertices[0]
            p2 = e.vertices[1]
            if (port == p1) or (port == p2):
                return e

    def generate_all_paths(self):
        """ Retrieve all paths between sources/sinks in the model. """

        sources = {}
        sinks = {}
        paths = []
        for _, p in self.port_obj.items():  # Collect info on which ports are sources/sinks/nodes
            n = self.lookup_node_from_port(p)
            if p.path_rule == PathRule.Source:
                sources[p] = n
            if p.path_rule == PathRule.Sink:
                sinks[p] = n
            if p.path_rule == PathRule.SourceOrSink:
                sources[p] = n
                sinks[p] = n

        for source_port, source_node in sources.items():  # Generate list of paths between sources and sinks
            for sink_port, sink_node in sinks.items():
                simple_paths = nx.all_simple_paths(self, source_node, sink_node)
                for i in simple_paths:
                    p = Path()  # Create path objects
                    p.vertices = i
                    p.start_port = source_port
                    p.end_port = sink_port
                    self.add_path_obj(p)
                    paths.append(i)

        self.sources = sources
        self.sinks = sinks
        self.all_paths = paths


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
        # Details about any tariffs and incentives
        self.has_tariff = False
        self.tariff = None
        self.initial_state = 1  # 1 = on, 0 = off
        self.lifetime = 100  # in planning period units
        self.existing_port = True  # Existing assets are forced to be installed in the first planning period
        # Cost per unit capacity - relevant to assets that get installed as part of asset expansion planning problem
        self.installation_capex = 0
        self.expansion_capex = 0  # Cost per unit capacity expansion - for capacity expansion problems
        self.fixed_opex = 0
        self.var_opex = 0
        self.replacement_capex = 0
        self.capacity_expansion = False
        self.path_rule = PathRule.NA

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
            if self.export_constraint_value > 0:
                raise ConfigurationError('Enter export constraint using positive load convention.')

        if self.import_constraint_value is not None:
            if self.import_constraint_value < 0:
                raise ConfigurationError('Enter import constraint using positive load convention.')

        if self.capacity_expansion is True and self.existing_port is False:
            raise ConfigurationError('Import/export capacity expansion can only be applied to an existing port.')

        if self.capacity_expansion is True and (-self.export_constraint_value != self.import_constraint_value):
            raise ConfigurationError('Capacity expansion can only be applied if import cap = export cap.')

        if self.capacity_expansion is True:
            if (self.export_constraint_value is None) or (self.import_constraint_value is None):
                raise ConfigurationError('Import/export cap cannot be None if capacity expansion is on.')

        if self.capacity_expansion is True:
            if (self.import_constraint is not FlowConstraint.Fixed) or (
                    self.export_constraint is not FlowConstraint.Fixed):
                raise ConfigurationError('Capacity expansion can only be applied if import and export constraint is'
                                         'FlowConstraint.Fixed.')

    def initialise_port(self, model):

        domain = en.Reals
        if self.flows is Flows.Export:
            domain = en.NonPositiveReals
        elif self.flows is Flows.Import:
            domain = en.NonNegativeReals

        self.positive_port_component = positive_variable_component + self.port_name
        self.negative_port_component = negative_variable_component + self.port_name

        if self.opt_type is OptimisationType.Parameter:

            setattr(model, self.port_name,
                    en.Param(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

            if type(self) is ElectricalGeneration:
                setattr(model, self.positive_port_component,
                        en.Param(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
                setattr(model, self.negative_port_component,
                        en.Param(model.Expansion, model.Time, initialize=self.initial_value,
                                 domain=en.NonPositiveReals))

            if type(self) is ElectricalDemand:
                setattr(model, self.positive_port_component,
                        en.Param(model.Expansion, model.Time, initialize=self.initial_value,
                                 domain=en.NonNegativeReals))
                setattr(model, self.negative_port_component,
                        en.Param(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))

        if self.opt_type is OptimisationType.Variable:

            setattr(model, self.port_name,
                    en.Var(model.Expansion, model.Time, initialize=self.initial_value, domain=domain))

            setattr(model, self.positive_port_component,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

            setattr(model, self.negative_port_component,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))

            con_rule = self.factory_pos_neg_flows(self.port_name, self.positive_port_component,
                                                  self.negative_port_component)

            con_name = positive_variable_component + negative_variable_component + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

        # Tariff variables
        if self.has_tariff:
            self.import_tariff_value = 'import_tariff_' + self.port_name
            self.export_tariff_value = 'export_tariff_' + self.port_name
            if self.tariff.tariff_optimisation is True:
                setattr(model, self.import_tariff_value,
                        en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals,
                               bounds=(self.tariff.import_tariff_min, self.tariff.import_tariff_max)))
                setattr(model, self.export_tariff_value,
                        en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals,
                               bounds=(self.tariff.export_tariff_min, self.tariff.export_tariff_max)))
            else:
                setattr(model, self.import_tariff_value,
                        en.Param(model.Expansion, model.Time, initialize=self.tariff.import_tariff))
                setattr(model, self.export_tariff_value,
                        en.Param(model.Expansion, model.Time, initialize=self.tariff.export_tariff))

        # # Additional constraint for pos/neg flows
        # self.pos_indicator = 'pos_indicator_' + self.port_name
        # setattr(model, self.pos_indicator, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))
        # self.neg_indicator = 'neg_indicator_' + self.port_name
        # setattr(model, self.neg_indicator, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))
        #
        # def pos_rule1(model, p, t):
        #     return getattr(model, self.pos_indicator)[p, t] <= getattr(model, self.positive_port_component)[p, t] * model.bigM
        #
        # def pos_rule2(model, p, t):
        #     return getattr(model, self.positive_port_component)[p, t] <= getattr(model, self.pos_indicator)[p, t] * model.bigM
        #
        # con_name = 'pos_indicator_con1_' + self.port_name
        # setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=pos_rule1))
        # con_name = 'pos_indicator_con2_' + self.port_name
        # setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=pos_rule2))
        #
        # def neg_rule1(model, p, t):
        #     return getattr(model, self.neg_indicator)[p, t] <= -getattr(model, self.negative_port_component)[p, t] * model.bigM
        #
        # def neg_rule2(model, p, t):
        #     return -getattr(model, self.negative_port_component)[p, t] <= getattr(model, self.neg_indicator)[p, t] * model.bigM
        #
        # con_name = 'neg_indicator_con1_' + self.port_name
        # setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=neg_rule1))
        # con_name = 'neg_indicator_con2_' + self.port_name
        # setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=neg_rule2))
        #
        # def pos_neg_rule(model, p, t):
        #     return getattr(model, self.pos_indicator)[p, t] + getattr(model, self.neg_indicator)[p, t] <= 1
        #
        # con_name = 'pos_neg_rule_' + self.port_name
        # setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=pos_neg_rule))

        # Import/export capacity constraint rules
        def cap_added_rule1(model,
                            p):  # BigM constraints for binary variable indicating whether capacity has been added
            return getattr(model, self.capacity_added_value)[p] <= getattr(model, self.capacity_added)[p] * model.bigM

        def cap_added_rule2(model, p):
            return getattr(model, self.capacity_added)[p] <= getattr(model, self.capacity_added_value)[p] * model.bigM

        def current_cap_rule(model, p):  # Rule for updating current capacity based on added capacity
            if p == 0:
                return getattr(model, self.current_capacity)[p] == self.initial_capacity + \
                       getattr(model, self.capacity_added_value)[p]
            else:
                return getattr(model, self.current_capacity)[p] == \
                       getattr(model, self.current_capacity)[p - 1] + getattr(model, self.capacity_added_value)[p]

        def cap_rule_1(model, p, t):  # Rule for enforcing current capacity on port value
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.current_capacity)[p]

        def cap_rule_2(model, p, t):
            return getattr(model, self.port_name)[p, t] >= - getattr(model, self.current_capacity)[p]

        # Binary variable for port capacity expansion decisions
        self.capacity_added = 'capacity_added_' + self.port_name
        setattr(model, self.capacity_added, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        self.current_capacity = 'current_capacity_' + self.port_name
        setattr(model, self.current_capacity, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        self.capacity_added_value = 'capacity_added_value_' + self.port_name
        if self.import_constraint is not FlowConstraint.Fixed:
            self.initial_capacity = model.bigM
        else:
            self.initial_capacity = self.import_constraint_value

        if self.capacity_expansion is True:
            setattr(model, self.capacity_added_value, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.capacity_added_value, en.Param(model.Expansion, initialize=0))

        con_name = 'current_cap_con_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=current_cap_rule))
        con_name = 'cap_added_con1_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=cap_added_rule1))
        con_name = 'cap_added_con2_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=cap_added_rule2))
        con_name = 'flow_con_1_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_1))
        con_name = 'flow_con_2_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_2))

        # On/off decision variable and constraints
        self.active = 'active_' + self.port_name
        setattr(model, self.active, en.Var(model.Expansion, initialize=self.initial_state, domain=en.Binary))

        def on_off_rule1(model, p, t):
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p] * model.bigM

        def on_off_rule2(model, p, t):
            return getattr(model, self.port_name)[p, t] >= - getattr(model, self.active)[p] * model.bigM

        def on_off_rule_param(model, p, t):  #Todo fix this
            return getattr(model, self.port_name)[p, t] == self.initial_value[p, t] * getattr(model, self.active)[p]

        if self.opt_type is OptimisationType.Variable:
            con_name = 'on_off_con1_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=on_off_rule1))
            con_name = 'on_off_con2_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=on_off_rule2))
        elif self.opt_type is OptimisationType.Parameter and self.existing_port is False:  # ToDo better way of identifying objects like this
            con_name = 'on_off_con_param_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=on_off_rule_param))

        # Installation decision variable and constraints
        self.installed = 'installed_' + self.port_name
        setattr(model, self.installed, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        def install_once_rule(model):
            return sum(getattr(model, self.installed)[p] for p in model.Expansion) <= 1

        con_name = 'install_once_' + self.port_name
        setattr(model, con_name, en.Constraint(rule=install_once_rule))

        def existing_port_rule(model, p):
            if p == 0:
                return getattr(model, self.installed)[p] == 1
            else:
                return getattr(model, self.installed)[p] == 0

        if self.existing_port:
            con_name = 'existing_port_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, rule=existing_port_rule))

        def install_before_active_rule(model, p):
            if p == 0:
                return getattr(model, self.active)[p] <= getattr(model, self.installed)[p]
            else:
                return getattr(model, self.active)[p] <= \
                       (getattr(model, self.installed)[p] + getattr(model, self.active)[p - 1])

        con_name = 'install_before_run_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=install_before_active_rule))

        # Define retirement, replacement, and lifetime remaining variables
        self.retire = 'retire_' + self.port_name
        setattr(model, self.retire, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        self.replace = 'replace_' + self.port_name
        setattr(model, self.replace, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        self.lifetime_remaining = 'lifetime_remaining_' + self.port_name
        setattr(model, self.lifetime_remaining,
                en.Var(model.Expansion, initialize=self.lifetime, domain=en.NonNegativeReals))

        # Define remaining life in terms of active variable and replacement variable
        def remaining_life_rule(model, p):
            if p == 0:
                return getattr(model, self.lifetime_remaining)[p] == self.lifetime
            else:
                return getattr(model, self.lifetime_remaining)[p] == \
                       getattr(model, self.lifetime_remaining)[p - 1] - \
                       getattr(model, self.active)[p - 1] + \
                       getattr(model, self.replace)[p - 1] * (self.lifetime + 1)

        con_name = 'remaining_life_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=remaining_life_rule))

        def eol_rule1(model, p):  # Big M Constraint: force either retirement or replacement at end of lifetime
            return getattr(model, self.lifetime_remaining)[p] <= \
                   (1 - (getattr(model, self.replace)[p] + getattr(model, self.retire)[p])) * model.bigM

        def eol_rule2(model, p):
            return (1 - (getattr(model, self.replace)[p] + getattr(model, self.retire)[p])) <= \
                   getattr(model, self.lifetime_remaining)[p] * model.bigM

        con_name = 'eol_1_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=eol_rule1))
        con_name = 'eol_2_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=eol_rule2))

    def factory_pos_neg_flows(self, var_name, pos_name, neg_name):

        def constraint(model, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == \
                   (getattr(model, pos_name)[expansion_interval, time_interval] +
                    getattr(model, neg_name)[expansion_interval, time_interval])

        return constraint

    def add_initial_value(self, initial_value):
        self.initial_value = initial_value

    def add_objective(self, model):

        objective = 0
        if self.has_tariff:
            objective += sum(
                getattr(model, self.import_tariff_value)[p, i] * getattr(model, self.positive_port_component)[p, i] *
                getattr(model, model.dr)[p] +
                getattr(model, self.export_tariff_value)[p, i] * getattr(model, self.negative_port_component)[p, i] *
                getattr(model, model.dr)[p]
                for p in model.Expansion for i in model.Time)

        if self.opt_type is OptimisationType.Variable:  # To ensure either positive or negative component = 0
            objective += sum(
                (getattr(model, self.positive_port_component)[p, i] - getattr(model, self.negative_port_component)[
                    p, i]) for p in model.Expansion for i in model.Time) * 0.000001

        # Installation capex
        objective += sum(getattr(model, self.installed)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.installation_capex

        # Expansion capex
        objective += sum(getattr(model, self.capacity_added_value)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.expansion_capex

        # Replacement capex
        objective += sum(getattr(model, self.replace)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.replacement_capex

        # Fixed opex
        objective += sum(getattr(model, self.active)[p] * getattr(model, model.dr)[p]
                         for p in model.Expansion) * self.fixed_opex

        # Variable opex
        if self.opt_type is OptimisationType.Variable:  # ToDo better way of identifying ports with variable opex
            objective += sum(
                (getattr(model, self.positive_port_component)[p, t] - getattr(model, self.negative_port_component)[
                    p, t]) *
                getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.var_opex

        return objective


class Node(object):
    """Nodes are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented."""

    def __init__(self):
        self.uid = uuid.uuid4()
        self.node_rule = NodeRule.NA
        self.ports = {}  # 'port_name: port'
        self.named_ports = []  # A list of ports that are expected to be attached
        # Included to ensure that ports can be dynamically populated or can have 'fixed' ports used to implement
        # particular assets like transformations.
        self.allow_dynamic_ports = False
        self.dynamic_ports = []
        self.node_name = 'node_' + str(self.uid)
        self.transformations = {}
        # Expansion planning attributes - for nodes that can accommodate expansions on them
        self.expansion_planning = False  # For identifying nodes which we can connect new expansion assets to
        self.storage_planning = False
        self.generator_planning = False
        self.storage_planning_capex = 0
        self.exp_port_names = []  # For separating original ports from ports that are part of expansion planning
        # Expansion asset attributes - for nodes that ARE potential expansion assets
        self.expansion_asset = False
        self.expansion_asset_type = ExpansionType.NA
        # Todo - should nodes have a lifetime? or just ports/edges

    def add_dynamic_port(self, port_name):
        pass

    def add_named_port(self, port_name):
        pass

    def add_transformation(self, transformation_obj):
        self.transformations[transformation_obj.uid] = transformation_obj

    def verify_node(self):

        if self.expansion_planning is True and self.node_rule is not (NodeRule.Tellegen or NodeRule.Sum):
            raise ConfigurationError('Expansion planning can only be applied to Tellegen nodes.')

        if self.node_rule is NodeRule.NA and len(self.ports) > 1:
            raise ConfigurationError('NodeRule cannot be NA if node has more than one port.')

        if self.expansion_planning is True and self.expansion_asset is True:
            raise ConfigurationError(
                'A node cannot both support expansion planning and be an expansion asset.')

        if self.node_rule == NodeRule.Transform:
            if not self.transformations:
                raise ConfigurationError(
                    "Node has Transform rule but Transformation object(s) has not been added to node.")

        if self.expansion_planning is True and (self.storage_planning is False and self.generator_planning is False):
            raise ConfigurationError('Expansion planning is on but no expansion type is set to True.')

        if self.expansion_asset is True and self.expansion_asset_type is ExpansionType.NA:
            raise ConfigurationError("Expansion asset type cannot be NA.")

    def initialise_node(self, model):

        self.installed = 'installed_node_' + self.node_name
        setattr(model, self.installed, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        def installed_node_rule_one(model, p):  # BigM constraints: node is installed if  all ports in node are installed
            num_ports = 0
            a = 0
            for _, port in self.ports.items():
                a += getattr(model, port.installed)[p]
                num_ports += 1
            return (num_ports - a) <= (1 - getattr(model, self.installed)[p]) * model.bigM

        def installed_node_rule_two(model, p):
            num_ports = 0
            a = 0
            for _, port in self.ports.items():
                a += getattr(model, port.installed)[p]
                num_ports += 1
            return (num_ports - a) * model.bigM >= (1 - getattr(model, self.installed)[p])

        con_name = 'installed_node_con1_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=installed_node_rule_one))
        con_name = 'installed_node_con2_' + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=installed_node_rule_two))


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


class Storage(Port):
    """ Storage for a commodity. """

    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge=0
                 ):
        super(Storage, self).__init__()
        self.storage = True
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
        # Throughput Cost
        # ToDo - Should this be related to the Levelised cost of energy (LCOE)
        self.throughput_cost = throughput_cost
        # Initial state of charge
        self.initial_state_of_charge = initial_state_of_charge
        self.interval_duration = 15  # ToDo update so this relates to time periods
        self.fixed_storage_capacity = True

    def initialise_port(self, model):
        super(Storage, self).initialise_port(model)

        self.storage_soc_value = 'storage_soc_' + self.port_name
        setattr(model, self.storage_soc_value,
                en.Var(model.Expansion, model.Time, initialize=0, bounds=(0, self.max_capacity)))  # Actual SOC

        self.optimised_storage_capacity = 'optimised_storage_capacity_' + self.port_name
        if self.fixed_storage_capacity is False:
            setattr(model, self.optimised_storage_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.optimised_storage_capacity,
                    en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

        def cap_limit(model, expansion_interval, time_interval):  # Ensure SOC is within max capacity
            return getattr(model, self.storage_soc_value)[expansion_interval, time_interval] <= \
                   getattr(model, self.optimised_storage_capacity)

        cap_limit_con_name = 'cap_limit_cons_' + self.port_name
        setattr(model, cap_limit_con_name, en.Constraint(model.Expansion, model.Time, rule=cap_limit))

        # # The battery charging efficiency
        eta_chg = self.charging_efficiency
        # # The battery discharging efficiency
        eta_dischg = self.discharging_efficiency
        charging_limit = self.charging_power_limit * (self.interval_duration / minutes_per_hour)
        discharging_limit = self.discharging_power_limit * (self.interval_duration / minutes_per_hour)

        def charging_limit_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] <= charging_limit

        con_name = 'charge_limit_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=charging_limit_rule))

        def discharging_limit_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] >= discharging_limit

        con_name = 'discharge_limit_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=discharging_limit_rule))

        def SOC_rule(model, p, t):
            if t == 0:
                return getattr(model, self.storage_soc_value)[p, t] \
                       == self.initial_state_of_charge + getattr(model, self.port_name)[p, t]
            else:
                return getattr(model, self.storage_soc_value)[p, t] \
                       == getattr(model, self.storage_soc_value)[p, t - 1] + getattr(model, self.port_name)[p, t]

        soc_con = 'soc_limit_' + self.port_name
        setattr(model, soc_con, en.Constraint(model.Expansion, model.Time, rule=SOC_rule))

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

        objective += sum(
            (getattr(model, self.positive_port_component)[p, t] - getattr(model, self.negative_port_component)[p, t]) *
            getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.throughput_cost / 2.0

        objective += sum(
            getattr(model, self.positive_port_component)[p, t] * getattr(model, self.positive_port_component)[p, t] + \
            getattr(model, self.negative_port_component)[p, t] * getattr(model, self.negative_port_component)[p, t]
            for p in model.Expansion for t in model.Time) * 0.0000001

        # Storage capex
        objective += getattr(model, self.optimised_storage_capacity) * self.installation_capex

        return objective


class FlexiblePort(Port):

    def __init__(self):
        super(FlexiblePort, self).__init__()
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW


class ElectricalDemand(Sink):

    def __init__(self):
        super(ElectricalDemand, self).__init__()
        self.units = Units.KW
        self.import_constraint = FlowConstraint.NoConstraint

    def add_demand_profile(self, electrical_demand):
        self.add_initial_value(electrical_demand)


class ElectricalGeneration(Source):

    def __init__(self):
        super(ElectricalGeneration, self).__init__()
        self.units = Units.KW
        self.export_constraint = FlowConstraint.NoConstraint

    def add_generation_profile(self, generation):
        self.add_initial_value(generation)


class ElectricalStorage(Storage):
    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge=0
                 ):
        super(ElectricalStorage, self).__init__(max_capacity,
                                                depth_of_discharge_limit,
                                                charging_power_limit,
                                                discharging_power_limit,
                                                charging_efficiency,
                                                discharging_efficiency,
                                                throughput_cost,
                                                initial_state_of_charge=0)
        self.units = Units.KW


class ElectricalNode(Node):
    """A node that implements a Kirchoff / Tellegen constraint requiring that electrical power is conserved"""

    def __init__(self):
        super(ElectricalNode, self).__init__()
        self.units = Units.KW


class Tariff(object):

    def __init__(self):
        self.import_tariff = None
        self.export_tariff = None
        self.tariff_optimisation = False
        self.import_tariff_min = 0
        self.import_tariff_max = None
        self.export_tariff_min = 0
        self.export_tariff_max = None

    def add_tariff_profile_import(self, tariff):
        self.import_tariff = tariff

    def add_tariff_profile_export(self, tariff):
        self.export_tariff = tariff

    def create_flat_import_tariff(self, value, time_periods, expansion_periods):
        t = {}
        for p in range(0, expansion_periods+1):
            for i in range(0, time_periods):
                t[p, i] = value
        self.import_tariff = t

    def create_flat_export_tariff(self, value, time_periods, expansion_periods):
        t = {}
        for p in range(0, expansion_periods+1):
            for i in range(0, time_periods):
                t[p, i] = value
        self.export_tariff = t


class ElectricalPort(Port):

    def __init__(self):
        super(ElectricalPort, self).__init__()
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.KW


class CarbonPort(Port):

    def __init__(self):
        super(CarbonPort, self).__init__()
        self.flows = Flows.Export
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable
        self.units = Units.CO


class Edge(object):

    def __init__(self):
        self.uid = uuid.uuid4()
        self.edge_name = 'edge_' + str(self.uid)
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.vertices = None
        self.has_tariff = False  #Todo should we allow tariffs on edges
        self.tariff = None
        self.initial_state = 1  # 1 = on, 0 = off
        self.initial_edge_capacity = 5000000
        # For expansion planning on existing edges
        self.capacity_expansion = False
        # Attributes relevant to edges that ARE possible expansions
        self.expansion_asset = False
        self.expansion_asset_type = ExpansionType.Edge
        # Costs
        self.installation_capex = 0
        self.expansion_capex = 0

    def add_vertices(self, obj1, obj2):
        self.vertices = (obj1, obj2)

    def verify_edge(self):

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        if (port1.flows is Flows.Export) and (port2.flows is Flows.Export):
            raise ConfigurationError('Port flow constraints do not allow any flow along the edge.')
        if (port1.flows is Flows.Import) and (port2.flows is Flows.Import):
            raise ConfigurationError('Port flow constraints do not allow any flow along the edge.')
        # if (port1.opt_type is OptimisationType.Parameter) and (port2.opt_type is OptimisationType.Parameter):
        #     raise ConfigurationError('Edge ports are both parameters.')

    def initialise_edge(self, model):

        self.add_edge_variables(model)
        self.add_constraints(model)

    def add_constraints(self, model):

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        con_rule1 = self.factory_constraint_edge_builder(port1.port_name, port2.port_name)
        con_name = 'edge_con_' + port1.port_name + '_' + port2.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule1))

        def installed_edge_rule1(model, p):  # BigM constraints: edge is installed if both vertices are installed
            a = getattr(model, port1.installed)[p] + getattr(model, port2.installed)[p]
            return (2 - a) <= (1 - getattr(model, self.installed)[p]) * model.bigM

        def installed_edge_rule2(model, p):
            a = getattr(model, port1.installed)[p] + getattr(model, port2.installed)[p]
            return (2 - a) * model.bigM >= (1 - getattr(model, self.installed)[p])

        con_name = 'installed_edge_con1_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=installed_edge_rule1))
        con_name = 'installed_edge_con2_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=installed_edge_rule2))

        # Apply edge capacity constraint on one of the edge vertices
        if port1.opt_type is OptimisationType.Parameter:  # Choose edge vertex that is not a parameter
            selected_port = port2
        else:
            selected_port = port1

        def cap_rule_1(model, p, t):
            return getattr(model, selected_port.port_name)[p, t] <= getattr(model, self.current_capacity)[p]

        def cap_rule_2(model, p, t):
            return getattr(model, selected_port.port_name)[p, t] >= - getattr(model, self.current_capacity)[p]

        con_name = 'flow_con_1_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_1))
        con_name = 'flow_con_2_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_2))

        def current_cap_rule(model, p):
            if p == 0:
                return getattr(model, self.current_capacity)[p] == self.initial_edge_capacity + \
                       getattr(model, self.capacity_added_value)[p]
            else:
                return getattr(model, self.current_capacity)[p] == \
                       getattr(model, self.current_capacity)[p - 1] + getattr(model, self.capacity_added_value)[p]

        con_name = 'current_cap_con_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=current_cap_rule))

        def cap_added_rule1(model, p):
            return getattr(model, self.capacity_added_value)[p] <= getattr(model, self.capacity_added)[p] * model.bigM

        def cap_added_rule2(model, p):
            return getattr(model, self.capacity_added)[p] <= getattr(model, self.capacity_added_value)[p] * model.bigM

        con_name = 'cap_added_con1_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=cap_added_rule1))
        con_name = 'cap_added_con2_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, rule=cap_added_rule2))

    def add_edge_variables(self, model):

        self.installed = 'installed_' + self.edge_name
        setattr(model, self.installed, en.Var(model.Expansion, initialize=0, domain=en.Binary))

        self.capacity_added_value = 'capacity_added_value_' + self.edge_name
        if self.capacity_expansion is False:
            setattr(model, self.capacity_added_value,en.Param(model.Expansion, initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.capacity_added_value, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        self.current_capacity = 'current_capacity_' + self.edge_name
        setattr(model, self.current_capacity, en.Var(model.Expansion, initialize=0, domain=en.NonNegativeReals))

        self.capacity_added = 'capacity_added_' + self.edge_name
        setattr(model, self.capacity_added, en.Var(model.Expansion, initialize=0, domain=en.Binary))

    def factory_constraint_edge_builder(self, obj1, obj2):
        def constraint(model, expansion_interval, time_interval):
            return getattr(model, obj1)[expansion_interval, time_interval] + \
                   getattr(model, obj2)[expansion_interval, time_interval] == 0

        return constraint

    def add_objective(self, model):
        objective = 0

        # Installation capex
        objective += self.installation_capex * self.initial_edge_capacity
        # ToDo update to work for expansion planning problems with new edges

        # Edge expansion capex
        objective += sum(
            getattr(model, self.capacity_added_value)[p] * getattr(model, model.dr)[p] for p in model.Expansion) * \
                     (self.expansion_capex)

        return objective

    def add_initial_edge_capacity(self, initial_capacity):
        self.initial_edge_capacity = initial_capacity


class Transform(object):
    """ An object for carrying a generic linear node transformation."""

    def __init__(self):
        self.uid = uuid.uuid4()
        self.transform_name = 'transform_' + str(self.uid)
        self.rhs = 0
        self.lhs = []
        self.weight = []
        self.rule = []

    def add_rhs(self, val):
        self.rhs = val

    def add_lhs(self, var, rule, weight):
        self.lhs.append(var)
        self.rule.append(rule)
        self.weight.append(weight)


class Path(object):
    """ A path is a list of connected nodes."""

    def __init__(self):
        self.vertices = []
        self.has_tariff = False
        self.tariff = None
        self.uid = uuid.uuid4()
        self.path_name = 'path_' + str(self.uid)
        self.units = Units.KW
        self.start_port = None
        self.end_port = None

    def add_tariff(self, tariff):
        if type(tariff) is not dict:
            raise ConfigurationError('Enter tariff as dictionary.')
        self.tariff = tariff

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

        if self.has_tariff is True:
            objective += sum(getattr(model, self.flow_value)[p, t] * self.tariff.import_tariff[p, t] \
                             for p in model.Expansion for t in model.Time)

        return objective


class ControllableLoad(Sink):

    def __init__(self):
        super(ControllableLoad, self).__init__()
        self.min_utilisation = None   # Per time unit (minute)
        self.max_utilisation = None
        self.max_power = 0

    def apply_constraints(self, model):
        pass


class ControllableGeneration(Source):

    def __init__(self):
        super(ControllableGeneration, self).__init__()
        pass


class Solar(ElectricalGeneration):

    def __init__(self):
        super(Solar, self).__init__()
        pass



