import uuid

import networkx as nx
from networkx import Graph
import pyomo.environ as en
from configuration import Units, Flows, FlowConstraint, OptimisationType, NodeRule, TransformRule, \
    ExpansionType, PathRule
from constants import minutes_per_hour, positive_variable_component, negative_variable_component


class OptimisationGraph(Graph):

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.node_obj = dict()
        self.edge_obj = dict()
        self.path_obj = dict()
        self.sources = []
        self.sinks = []
        self.all_paths = []

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

    def add_path_obj(self, path_obj):
        path_key = tuple(path_obj.vertices)
        self.path_obj[path_key] = path_obj

    def lookup_node_from_port(self, port):
        """ Returns node that a specified port belongs to, if the port belongs to a node."""
        for _, node in self.node_obj.items():
            for _, p in node.ports.items():
                if port == p:
                    return node
        raise ConfigurationError('Port is not part of any node.')

    def generate_all_paths(self):
        """ Retrieve all paths between sources/sinks in the model. """
        all_paths = []
        sources_or_sinks = {}
        for _, n in self.node_obj.items():
            for _, p in n.ports.items():  # Collect info on which ports are sources/sinks/nodes
                if p.path_rule == PathRule.SourceOrSink:
                    sources_or_sinks[p] = n

        for source_port, source_node in sources_or_sinks.items():  # Generate list of paths between sources and sinks
            for sink_port, sink_node in sources_or_sinks.items():
                simple_paths = nx.all_simple_paths(self, source_node, sink_node)
                for i in simple_paths:
                    p = Path()  # Create path objects
                    p.vertices = i
                    p.start_port = source_port
                    p.end_port = sink_port
                    all_paths.append(i)
                    self.add_path_obj(p)

        self.sources_or_sinks = sources_or_sinks


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
        self.demand_tariff = None
        self.installation_capex = 0
        self.var_opex = 0
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

        self.is_pos = 'is_pos_' + self.port_name
        setattr(model, self.is_pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        self.is_neg = 'is_neg_' + self.port_name
        setattr(model, self.is_neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        con_name = 'is_pos_con1_' + self.port_name
        con_rule = self.factory_big_M_one(1, self.positive_port_component, self.is_pos)
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))
        con_name = 'is_pos_con2_' + self.port_name
        con_rule = self.factory_big_M_two(1, self.positive_port_component, self.is_pos)
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))
        con_name = 'is_neg_con1_' + self.port_name
        con_rule = self.factory_big_M_one(-1, self.negative_port_component, self.is_neg)
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))
        con_name = 'is_neg_con2_' + self.port_name
        con_rule = self.factory_big_M_two(-1, self.negative_port_component, self.is_neg)
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

        def pos_neg_rule(model, p, t):
            return getattr(model, self.is_pos)[p, t] + getattr(model, self.is_neg)[p, t] <= 1

        con_name = 'pos_neg_con_' + self.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=pos_neg_rule))

        # Import/export capacity constraint rules
        def import_cap_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] <= self.import_constraint_value

        def export_cap_rule(model, p, t):
            return getattr(model, self.port_name)[p, t] >= self.export_constraint_value

        if self.import_constraint is FlowConstraint.Fixed:
            con_name = 'import_con_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule))
        if self.export_constraint is FlowConstraint.Fixed:
            con_name = 'export_con_' + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule))

        # Tariff variables
        if self.has_tariff:
            if self.tariff:
                self.import_tariff_value = 'import_tariff_' + self.port_name
                self.export_tariff_value = 'export_tariff_' + self.port_name
                setattr(model, self.import_tariff_value,
                        en.Param(model.Expansion, model.Time, initialize=self.tariff.import_tariff))
                setattr(model, self.export_tariff_value,
                        en.Param(model.Expansion, model.Time, initialize=self.tariff.export_tariff))
            if self.demand_tariff:
                self.max_demand = 'max_demand_' + self.port_name
                setattr(model, self.max_demand, en.Var(initialize=0, domain=en.NonNegativeReals))
                self.max_demand_window = 'max_demand_window_' + self.port_name
                setattr(model, self.max_demand_window, en.Param(model.Expansion, model.Time,
                                                                initialize=self.demand_tariff.window))

                def max_demand_rule(model, p, t):
                    return getattr(model, self.max_demand) >= \
                           (getattr(model, self.positive_port_component)[p, t] - self.demand_tariff.min_demand) * \
                           getattr(model, self.max_demand_window)[p, t]

                con_name = 'max_val_con_' + self.port_name
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=max_demand_rule))


    def factory_pos_neg_flows(self, var_name, pos_name, neg_name):

        def constraint(model, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == \
                   (getattr(model, pos_name)[expansion_interval, time_interval] +
                    getattr(model, neg_name)[expansion_interval, time_interval])

        return constraint

    def factory_big_M_one(self, sign, var, indicator):
        def constraint(model, p, t):
            return getattr(model, indicator)[p, t] <= getattr(model, var)[p, t] * model.bigM * sign
        return constraint

    def factory_big_M_two(self, sign, var, indicator):
        def constraint(model, p, t):
            return sign * getattr(model, var)[p, t] <= getattr(model, indicator)[p, t] * model.bigM
        return constraint

    def add_initial_value(self, initial_value):
        self.initial_value = initial_value

    def add_objective(self, model):

        objective = 0
        if self.has_tariff:
            if self.tariff:
                objective += sum(
                    getattr(model, self.import_tariff_value)[p, i] * getattr(model, self.positive_port_component)[p, i] *
                    getattr(model, model.dr)[p] +
                    getattr(model, self.export_tariff_value)[p, i] * getattr(model, self.negative_port_component)[p, i] *
                    getattr(model, model.dr)[p]
                    for p in model.Expansion for i in model.Time)

            if self.demand_tariff:
                objective += getattr(model, self.max_demand) * self.demand_tariff.demand_charge

        if self.opt_type is OptimisationType.Variable:  # To make positive or negative component = 0
            objective += sum(
                (getattr(model, self.positive_port_component)[p, i] - getattr(model, self.negative_port_component)[
                    p, i]) for p in model.Expansion for i in model.Time) * 0.000001

        # Variable opex
        objective += sum(
            (getattr(model, self.positive_port_component)[p, t] - getattr(model, self.negative_port_component)[
                p, t]) * getattr(model, model.dr)[p] for p in model.Expansion for t in model.Time) * self.var_opex

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

    def verify_node(self):
        if self.node_rule is NodeRule.NA and len(self.ports) > 1:
            raise ConfigurationError('NodeRule cannot be NA if node has more than one port.')

        if self.node_rule == NodeRule.Transform:
            if not self.transformations:
                raise ConfigurationError(
                    "Node has Transform rule but Transformation object(s) has not been added to node.")

    def initialise_node(self, model):
        pass


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
                 initial_state_of_charge
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
        self.interval_duration = 60  # ToDo update so this relates to time periods
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

    def add_demand_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)


class ElectricalGeneration(Source):

    def __init__(self):
        super(ElectricalGeneration, self).__init__()
        self.units = Units.KW
        self.export_constraint = FlowConstraint.NoConstraint

    def add_generation_profile(self, generation):
        self.add_initial_value(generation)

    def add_generation_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.add_initial_value(t)


class ElectricalStorage(Storage):
    def __init__(self,
                 max_capacity,
                 depth_of_discharge_limit,
                 charging_power_limit,
                 discharging_power_limit,
                 charging_efficiency,
                 discharging_efficiency,
                 throughput_cost,
                 initial_state_of_charge
                 ):
        super(ElectricalStorage, self).__init__(max_capacity,
                                                depth_of_discharge_limit,
                                                charging_power_limit,
                                                discharging_power_limit,
                                                charging_efficiency,
                                                discharging_efficiency,
                                                throughput_cost,
                                                initial_state_of_charge)
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

    def add_tariff_profile_import(self, tariff):
        self.import_tariff = tariff

    def add_tariff_profile_export(self, tariff):
        self.export_tariff = tariff

    def add_import_tariff_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.import_tariff = t

    def add_export_tariff_profile_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.export_tariff = t


class DemandTariff(object):

    def __init__(self,
                 window,
                 expansion_periods,
                 demand_charge,
                 min_demand
                 ):
        self.window = None
        self.add_window(window, expansion_periods)
        self.demand_charge = demand_charge
        self.min_demand = min_demand

    def add_window(self, array, expansion_periods):
        window = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                window[(ep, i)] = array[i]
        self.window = window


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

    def __init__(self,
                 vertices):
        self.uid = uuid.uuid4()
        self.edge_name = 'edge_' + str(self.uid)
        self.units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
        self.opt_type = OptimisationType.NA  # Is this a decision variable or a fixed parameter
        self.vertices = vertices
        self.has_tariff = False  # Todo should we allow tariffs on edges
        self.tariff = None
        self.initial_edge_capacity = 5000000

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

        # Apply edge capacity constraint on one of the edge vertices
        if port1.opt_type is OptimisationType.Parameter:  # Choose edge vertex that is not a parameter
            selected_port = port2
        else:
            selected_port = port1

        def cap_rule_1(model, p, t):
            return getattr(model, selected_port.port_name)[p, t] <= self.initial_edge_capacity

        def cap_rule_2(model, p, t):
            return getattr(model, selected_port.port_name)[p, t] >= - self.initial_edge_capacity

        con_name = 'flow_con_1_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_1))
        con_name = 'flow_con_2_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=cap_rule_2))

        setattr(model, self.edge_name, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

        def edge_var_con(model, p, t):
            return getattr(model, self.edge_name)[p, t] == getattr(model, self.vertices[0].port_name)[p, t]

        con_name = 'edge_con_' + self.edge_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=edge_var_con))

    def factory_constraint_edge_builder(self, obj1, obj2):
        def constraint(model, expansion_interval, time_interval):
            return getattr(model, obj1)[expansion_interval, time_interval] + \
                   getattr(model, obj2)[expansion_interval, time_interval] == 0

        return constraint

    def add_objective(self, model):
        pass

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

    def add_tariff_from_array(self, array, expansion_periods):
        t = {}
        for ep in range(0, expansion_periods):
            for i in range(0, len(array)):
                t[(ep, i)] = array[i]
        self.tariff = t

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

        # objective += sum(getattr(model, self.flow_value)[p, t] for p in model.Expansion for t in model.Time) * 0.000001

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



