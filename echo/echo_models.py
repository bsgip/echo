import uuid

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from networkx import Graph
import pyomo.environ as en
from echo.configuration import *
from echo.constants import *
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, validator, root_validator, NegativeFloat, PositiveFloat, confloat
from typing import Optional, Union, List, Container, TypeVar
from echo.echo_validators import *
from echo.utils import *

DataFrame = TypeVar('pandas.core.frame.DataFrame')

"""

    Base models

"""


class BaseModel(PydanticBaseModel):
    class Config:
        validate_assignment = True  # set to true so that we re-validate when we update a model field


class OptimisationGraph(Graph):
    # todo do we need anything pydantic related for this class?

    def __init__(self):
        super(OptimisationGraph, self).__init__()
        self.node_obj = dict()
        self.edge_obj = dict()
        self.paths = {}

    def _add_single_node(self, node_obj):
        self.add_node(node_obj.node_name)
        self.node_obj[node_obj.node_name] = node_obj

    def add_node_obj(self, node):
        if type(node) is list:
            for n in node:
                # check if node is already defined
                assert n.node_name not in self.nodes, 'Node \'{}\' already defined'.format(n.node_name)
                self._add_single_node(n)
        else:
            self._add_single_node(node)

    def add_edge_obj(self, edge):
        def add_single_edge(edge_obj):
            port1 = edge_obj.vertices[0]
            port2 = edge_obj.vertices[1]
            node1 = self.lookup_node_from_port(port1)
            node2 = self.lookup_node_from_port(port2)
            self.add_edge(node1.node_name, node2.node_name)
            self.edge_obj[(node1.node_name, node2.node_name)] = edge_obj

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
        connecting_edge = self.edge_obj.get((node1, node2))
        if connecting_edge:
            node1_port = connecting_edge.vertices[0]
            node2_port = connecting_edge.vertices[1]
            return node1_port, node2_port
        else:
            connecting_edge = self.edge_obj.get((node2, node1))
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

    def get_path(self, path_vertices):
        # check whether vertices were entered as a list of node names (str) or list of node objs
        assert type(path_vertices) == list, 'Please enter path as a list of node objects or names.'
        if all(isinstance(item, str) for item in path_vertices):
            return self.paths[tuple(path_vertices)]
        else:
            try:
                name_key = [node.node_name for node in path_vertices]
                return self.paths[tuple(name_key)]
            except:
                raise ValueError('Either enter list of node objects or list of node names. List items not recognised.')

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
                    # Find all the paths, just using the node names
                    simple_paths = nx.all_simple_paths(self, source_node.node_name, sink_node.node_name)
                    simple_edges = nx.all_simple_edge_paths(self, source_node.node_name, sink_node.node_name)
                    for vertex_list, edge_list in zip(simple_paths, simple_edges):
                        # Convert list of node names to list of node objects
                        p = Path(vertices=vertex_list)  # Create path objects
                        p.regularise = regularise  # For adding regularisation (ie equal sharing) to give a unique solution
                        p.units = Units.KW
                        for edge in edge_list:
                            edge_obj = self.get_ports_on_edge_from_nodes(edge[0], edge[1])
                            assert edge_obj[0].units == Units.KW  # todo will need to change this for multi commodity
                            assert edge_obj[1].units == Units.KW
                            p.edge_ports.append(edge_obj)
                        all_paths[tuple(vertex_list)] = p

        self.paths = all_paths
        self.verify_paths()

    def draw(self, with_labels=False, labels=None):
        """
        Draws the network with or without node labels
        """
        nx.draw_networkx(self, with_labels=with_labels, labels=labels)
        plt.show()

    def print_network_hierarchy(self):
        """
        Prints the model hierarchy as node names --> port names
        """
        for n_name, n_object in self.node_obj.items():
            print(n_name)
            for p_name, p_object in n_object.ports.items():
                print('  port_name: ', p_name)


class ConfigurationError(Exception):
    pass


class Port(BaseModel):
    # Pydantic attribute declaration follows this format:
    # attribute_name: type = default_value

    units: int = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
    initial_value: dict = 0.
    opt_type: int = OptimisationType.NA
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    port_name: Optional[str] = None
    flows: int = Flows.NA  # What flow directions are possible (import, export, both)
    # Used to define the nature of import / export directions and constraints
    import_constraint: int = FlowConstraint.NA
    import_constraint_value: Union[
        dict, float, None] = None  # Use Union because this could be a list, or a float, or None. todo maybe make this optional
    export_constraint: int = FlowConstraint.NA
    export_constraint_value: Union[dict, float, None] = None
    active_periods: Optional[dict]
    slack: bool = False
    optional: bool = False

    # All our optional fields/fields that are created when building pyomo model, and used to define variable names
    import_con_val: Optional[str]
    export_con_val: Optional[str]
    import_slack: Optional[str]
    import_slack_max: Optional[str]
    export_slack: Optional[str]
    export_slack_max: Optional[str]
    pos: Optional[str]
    is_pos: Optional[str]
    neg: Optional[str]  # todo don't love having to define every one of these.. is there an alternative?
    active: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        if self.port_name is None:
            # if no name is provided, give it a default name using the uid
            self.port_name = 'port_' + str(self.uid)
        self.import_con_val = f"import_con_val_{self.port_name}"
        self.export_con_val = f"export_con_val_{self.port_name}"
        self.import_slack = f"import_slack_{self.port_name}"
        self.import_slack_max = f"import_slack_max_{self.port_name}"
        self.export_slack = f"export_slack_{self.port_name}"
        self.export_slack_max = f"export_slack_max_{self.port_name}"
        self.pos = positive_variable_component + self.port_name
        self.neg = negative_variable_component + self.port_name
        self.is_pos = f"is_pos_{self.port_name}"

    def set_flow_constraints(self, max_import, max_export, slack=False):
        """

        Sets the values of port flow constraints.

        Args:
            max_import: max allowable import into port (float, array, or None)
            max_export: max allowable export out of port (float, array, or None)
            slack: bool
        """
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
        if slack is not None:
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
        """

        Creates pyomo vars, params, and constraints for the port

        Args:
            model: pyomo concrete model

        """

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
                constraint_array = generate_array_cons(self.import_constraint_value)
                setattr(model, self.import_con_val,
                        en.Param(model.Expansion, model.Time, initialize=constraint_array, domain=en.NonNegativeReals))

                if self.slack is True:
                    setattr(model, self.import_slack,
                            en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
                    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule_slack))
                    con_name = 'import_con_max_' + self.port_name
                    setattr(model, self.import_slack_max,
                            en.Var(initialize=0, domain=en.NonPositiveReals))
                    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_slack_max_rule))
                else:
                    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule))
        if self.export_constraint is FlowConstraint.Fixed:
            if self.opt_type is not OptimisationType.Parameter:  # only apply these constraints to variables
                con_name = 'export_con_' + self.port_name
                constraint_array = generate_array_cons(self.export_constraint_value)
                setattr(model, self.export_con_val,
                        en.Param(model.Expansion, model.Time, initialize=constraint_array, domain=en.NonPositiveReals))

                if self.slack is True:
                    setattr(model, self.export_slack,
                            en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
                    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule_slack))
                    con_name = 'export_con_max_' + self.port_name
                    setattr(model, self.export_slack_max,
                            en.Var(initialize=0, domain=en.NonNegativeReals))
                    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_slack_max_rule))
                else:
                    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule))

        if self.active_periods is not None:
            def on_off_rule1(model, p, t):
                return getattr(model, self.port_name)[p, t] <= self.active_periods[p, t] * model.bigM

            def on_off_rule2(model, p, t):
                return getattr(model, self.port_name)[p, t] >= - self.active_periods[p, t] * model.bigM

            setattr(model, f"active_con1_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=on_off_rule1))
            setattr(model, f"active_con2_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=on_off_rule2))

    def constrain_pos_neg(self, model):
        """
        Applies a mixed integer constraint that splits a port var into positive and negative components:

        Args:
            model: pyomo concrete model

        """

        setattr(model, self.pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
        setattr(model, self.neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
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

    @staticmethod
    def factory_pos_neg_flows(var_name, pos_name, neg_name):
        def constraint(model, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == \
                   (getattr(model, pos_name)[expansion_interval, time_interval] +
                    getattr(model, neg_name)[expansion_interval, time_interval])

        return constraint

    def add_initial_value(self, initial_value):
        """
        Adds initial port value which will be used to initialise the pyomo var/param

        Args:
            initial_value: dict of initial values

        """
        self.initial_value = initial_value

    def add_initial_value_from_array(self, array, expansion_periods=1):
        """
        Adds initial port value which is used to initialise the pyomo var/param

        Args:
            array: array, list of initial values
            expansion_periods: number of expansion periods (int)

        """
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        self.add_initial_value(vals)

    def add_active_periods_from_array(self, array, expansion_periods=1):
        """
        Adds port active periods

        Args:
            array: array, list of active periods as bool values
            expansion_periods: number of expansion periods (int)

        """
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        self.active_periods = vals

    def add_objective(self, model):
        """
        Adds port-specific objective terms to pyomo model

        Args:
            model: pyomo concrete model

        """
        objective = 0
        if self.slack is True:
            if hasattr(model, self.import_slack) is True:
                objective += -1 * getattr(model, self.import_slack_max) * model.bigM
                objective += -1 * sum(getattr(model, self.import_slack)[p, t] for p in model.Expansion for t in
                                      model.Time) * model.bigM * 0.1
            if hasattr(model, self.export_slack) is True:
                objective += getattr(model, self.export_slack_max) * model.bigM
                objective += sum(getattr(model, self.export_slack)[p, t] for p in model.Expansion for t in
                                 model.Time) * model.bigM * 0.1
        return objective


class Node(BaseModel):
    """

    Nodes are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented.

    """
    node_name: Optional[str]
    uid: Optional[uuid.UUID]
    ports: dict = {}
    node_rule: int = NodeRule.NA
    transformations: dict = {}
    named_ports: list = []

    inflow: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        self.uid = uuid.uuid4()
        self.node_name = 'node_' + str(
            self.uid)  # we define the node uid and name like this so that the user can redefine them if desired.

    def add_flex_port(self, name, unit=Units.NA):
        """
        Adds named port of specified type to node.
        Args:
            name: port name as string
            unit: Unit
        """
        self.ports[name] = FlexPort()
        if unit is not Units.NA:
            self.ports[name].units = unit

    def add_electrical_port(self, port_name):
        self.add_flex_port(port_name, unit=Units.KW)

    def add_electrical_ports_from_list(self, name_list):
        if type(name_list) is not list:
            return ConfigurationError('Please enter named ports as list of port names.')
        for name in name_list:
            self.add_electrical_port(port_name=name)

    def add_flex_ports_from_list(self, name_list, unit=Units.NA):
        if type(name_list) is not list:
            return ConfigurationError('Please enter named ports as list of port names.')
        for name in name_list:
            self.add_flex_port(name, unit)

    def add_transformation(self, transformation_obj):
        """
        Adds a transformation object to a node.
        Args:
            transformation_obj: Transform
        """
        self.transformations[transformation_obj.uid] = transformation_obj

    def add_emission_transformation(self, emitting_port, carbon_port, emission_factor):
        """
        Creates an emission transformation and adds to the node.
        Args:
            emitting_port: port object that generates emissions when exporting (when negative)
            carbon_port: port object that represents carbon flows
            emission_factor: a ratio = emissions generated/emitting unit generated (float)
        """
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

    def num_ports(self):
        return len(self.ports)


class Edge(BaseModel):
    """

    Edges are used to connect nodes. For an edge (x, y) where x and y are nodes,
    the edge value is equal to the flow from x->y plus the flow from y->x.

    """
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    edge_name: Optional[str] = None
    opt_type: int = OptimisationType.NA
    vertices: tuple
    tariff: Optional[Union[list, None]]

    @root_validator()
    def assign_edge_name(cls, values):
        uid = values.get("uid")
        if uid is not None:
            values["edge_name"] = 'edge_' + str(uid)
        return values

    def add_vertices(self, obj1, obj2):
        """
        Adds edge vertices (which are ports)
        Args:
            obj1: port object
            obj2: port object
        """
        self.vertices = (obj1, obj2)

    def verify_edge(self):
        port1 = self.vertices[0]
        port2 = self.vertices[1]

        if (port1.flows is Flows.Export) and (port2.flows is Flows.Export):
            raise ConfigurationError('Port flow constraints do not allow any flow along the edge.')
        if (port1.flows is Flows.Import) and (port2.flows is Flows.Import):
            raise ConfigurationError('Port flow constraints do not allow any flow along the edge.')

    def initialise_edge(self, model):
        """
        Applies edge constraint
        Args:
            mode: pyomo concrete model
        """

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


class Transform(BaseModel):
    """
    An object for carrying a generic linear node transformation.
    """
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    transform_name: Optional[str] = None
    rhs: list = []
    lhs: list = []

    def __init__(self, **data):
        super().__init__(**data)
        if self.transform_name is None:
            self.transform_name = 'transform_' + str(self.uid)

    def add_rhs_term(self, var, rule, weight):
        """
        Adds a right hand side (RHS) term to the transform
        Args:
            var: pyomo var name
            rule: TransformationRule object
            weight: linear factor (float)

        """
        term = {'var': var, 'rule': rule, 'weight': weight}
        self.rhs.append(term)

    def add_lhs_term(self, var, rule, weight):
        """
        Adds a left hand side (RHS) term to the transform
        Args:
            var: pyomo var name
            rule: TransformationRule object
            weight: linear factor (float)

        """
        term = {'var': var, 'rule': rule, 'weight': weight}
        self.lhs.append(term)

    def initialise_transform(self, model):
        # Check if we need to create pos/neg components
        for i in range(len(self.lhs)):
            rule = self.lhs[i]['rule']
            if rule is not TransformRule.Both:
                var = self.lhs[i]['var']
                if hasattr(model, var.pos) is False:
                    var.constrain_pos_neg(model)

        for i in range(len(self.rhs)):
            rule = self.rhs[i]['rule']
            if rule is not TransformRule.Both:
                var = self.rhs[i]['var']
                if hasattr(model, var.pos) is False:
                    var.constrain_pos_neg(model)


class Path(BaseModel):
    """ A path is a sequence of distinct vertices (nodes). """
    edge_ports: List[tuple] = []  # list of edge name tuples
    vertices: list  # list of node names
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    path_name: Optional[str] = None
    units = Units.KW
    regularise: bool = False

    flow_value: Optional[str]
    contingency_neg: Optional[str]
    contingency_pos: Optional[str]
    path_tariff: Optional[str]
    slack: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        if self.path_name is None:
            self.path_name = 'path_' + str(self.uid)
        self.flow_value = 'flow_value_' + self.path_name

    def add_vertices(self, vertex_list):
        if type(vertex_list) is not list:
            raise ConfigurationError('Please enter path vertices (nodes) as a list.')
        self.vertices = vertex_list

    def verify_path(self):
        pass

    def initialise_path(self, model):
        setattr(model, self.flow_value, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

    def add_objective(self, model):
        objective = 0

        if self.regularise is True:
            objective += sum(getattr(model, self.flow_value)[p, t] * getattr(model, self.flow_value)[p, t] \
                             for p in model.Expansion for t in model.Time) * 0.0000001

        return objective


"""

    Commodity agnostic ports and nodes

"""


class TellegenNode(Node):
    """A node that implements a Tellegen constraint requiring that port values sum to zero."""
    node_rule = NodeRule.Tellegen

    def verify_node(self):
        # Check that all ports on the node have the same units
        u = None
        for p in self.ports.values():
            if u is not None:
                assert p.units == u, 'Tellegen node ports must have the same units.'
            else:
                u = p.units


class FlexPort(Port):
    """ Flexible port """
    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    opt_type = OptimisationType.Variable


class Source(Port):
    """ A source of a commodity. """
    flows: int = Flows.Export
    opt_type: int = OptimisationType.Parameter

    # Source should have non positive initial values
    non_pos_check = validator("initial_value", allow_reuse=True)(nonpositive_generation)


class Sink(Port):
    """ The sink for a commodity. """
    flows = Flows.Import
    opt_type = OptimisationType.Parameter
    import_constraint = FlowConstraint.NoConstraint

    # Sink should have non negative initial values
    non_neg_check = validator("initial_value", allow_reuse=True)(nonnegative_load)

    def add_sink_profile(self, electrical_demand):
        self.add_initial_value(electrical_demand)

    def add_sink_profile_from_array(self, array, expansion_periods=1):
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        self.add_initial_value(vals)


class Storage(Port):
    """ Storage for a commodity. """
    flows = Flows.Both
    opt_type = OptimisationType.Variable
    import_constraint = FlowConstraint.Fixed
    export_constraint = FlowConstraint.Fixed
    max_capacity: float
    depth_of_discharge_limit: float = 0  # DoD limit is the percent soc to which you can discharge the storage
    min_soc: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    initial_state_of_charge: float
    fixed_storage_capacity: bool = True
    var_opex: float = 0.
    regularise: bool = False
    # next variable is for allowing soc to go below min so as to avoid optimisation failing if there infeasible ev trips
    enable_trip_slack: bool = False
    # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
    soc_conserv: Union[float, None] = None
    soc_conserv_cost: Union[float, None] = None
    available: Union[ArrayType, list, None] = None

    # All our optional fields/fields created when building pyomo model
    soc_value: Optional[str]
    optimised_capacity: Optional[str]
    trip_slack: Optional[Union[ArrayType, list]]
    cons_slack: Optional[str]
    trip_slack: Optional[str]
    optimised_capacity: Optional[str]

    @root_validator()
    def dod_checks(cls, values):
        # Check which dod representation we have
        dod_lim = values.get('depth_of_discharge_limit')
        max_cap = values.get('max_capacity')
        init_soc = values.get('initial_state_of_charge')
        # Check dod representation
        if 0 <= dod_lim <= 1:
            # Assume decimal representation
            min_soc = max_cap * dod_lim
        elif 1 < dod_lim <= 100:
            # Assume percentage representation
            min_soc = max_cap * dod_lim / 100.0
        else:
            raise ValueError('DoD must be entered as decimal fraction or percentage of max capacity')
        # Check initial soc is within bounds
        if (init_soc < min_soc) or (init_soc > max_cap):
            raise ValueError(
                'Initial state of charge, {}, must be between min soc, {}, and max capacity, {}'.format(init_soc,
                                                                                                        min_soc,
                                                                                                        max_cap))
        values['min_soc'] = min_soc
        return values

    def __init__(self, **data):
        super().__init__(**data)
        self.import_constraint_value = self.charging_power_limit
        self.export_constraint_value = self.discharging_power_limit
        # Define our pyomo var names
        self.soc_value = 'storage_soc_' + self.port_name
        self.cons_slack = 'con_slack' + self.port_name
        self.trip_slack = 'trip_slack_' + self.port_name
        self.optimised_capacity = 'optimised_storage_capacity_' + self.port_name

    def initialise_port(self, model):
        super(Storage, self).initialise_port(model)
        setattr(model, self.soc_value, en.Var(model.Expansion, model.Time, initialize=0,
                                              bounds=(self.min_soc, self.max_capacity)))  # Actual SOC

        def soc_conservative_rule(model, p, t):  # a rule for enforcing conservativness while plugged in
            if self.available[t]:
                return getattr(model, self.soc_value)[p, t] + getattr(model, self.cons_slack)[
                    p, t] - self.soc_conserv >= 0
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            assert self.soc_conserv_cost is not None, 'soc_conserv requires soc_conserv_cost'
            assert self.available is not None, 'soc_conserve requires available'
            setattr(model, self.cons_slack,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, f"cons_soc_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=soc_conservative_rule))

        # def min_soc_rule_slack(model,p,t):    # ensure soc stays above min charge but has slack variable for EV infeasible trips
        #     return getattr(model, self.soc_value)[p, t] + getattr(model, self.min_soc_slack) >= 0

        if self.fixed_storage_capacity is False:
            setattr(model, self.optimised_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))
        else:
            setattr(model, self.optimised_capacity, en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

        def cap_limit(model, p, t):  # Ensure SOC is within max capacity
            return getattr(model, self.soc_value)[p, t] <= getattr(model, self.optimised_capacity)

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
            setattr(model, self.trip_slack,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
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

    def add_objective(self, model):
        super(Storage, self).add_objective(model)
        objective = 0

        # To get unique solution
        if self.regularise is True:
            objective += sum(
                getattr(model, self.pos)[p, t] * getattr(model, self.pos)[p, t] + \
                getattr(model, self.neg)[p, t] * getattr(model, self.neg)[p, t]
                for p in model.Expansion for t in model.Time) * 0.0000001

        if self.enable_trip_slack:
            objective += sum(getattr(model, self.trip_slack)[p, t] for p in model.Expansion for t in
                             model.Time) * model.bigM * 20  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            objective += sum(getattr(model, self.cons_slack)[p, t] for p in model.Expansion for t in
                             model.Time) * self.soc_conserv_cost

        return objective


class Demand(Sink):
    import_constraint = FlowConstraint.NoConstraint


class ControlledLoadOrGen(FlexPort):
    """ A controlled load or generation has a max/min power, as well as a max/min utilisation.
    The load/generation must be operated within the min and max utilisation (per time unit). """
    min_utilisation: Union[float, None] = None  # Per time unit (minute)
    max_utilisation: float = None
    max_power: float = None
    min_power: float = None
    units: int = Units.KW

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

    def add_demand_profile_from_array(self, array, expansion_periods=1):
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        self.add_initial_value(vals)


class ControlledLoad(ControlledLoadOrGen):
    max_power: confloat(ge=0)
    min_power: confloat(ge=0)
    flows = Flows.Import


class ControlledGen(ControlledLoadOrGen):
    max_power: confloat(le=0)
    min_power: confloat(le=0)
    flows = Flows.Export


"""

    Electrical ports and nodes

"""


class ElectricalNode(Node):
    units = Units.KW


class ElectricalDemand(Sink):
    """ Fixed electrical demand"""
    units = Units.KW
    import_constraint = FlowConstraint.NoConstraint

    def add_demand_profile(self, electrical_demand):
        self.add_initial_value(electrical_demand)

    def add_demand_profile_from_array(self, array, expansion_periods=1):
        if type(array) is np.ndarray:
            assert (array >= 0).all(), 'power demand must be non negative'
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        self.add_initial_value(vals)


class ElectricalGeneration(Source):
    """ Electrical generation which can be fixed (non-curtailable) or variable (curtailable) """
    units = Units.KW
    export_constraint = FlowConstraint.NoConstraint
    curtailable: bool = False

    # All our optional fields/fields created when building pyomo model
    port_name_max: Optional[str]

    def add_generation_profile(self, generation):
        assert type(generation) is dict, 'Generation profile must be dict.'
        self.add_initial_value(generation)

    def add_generation_profile_from_array(self, array, expansion_periods=1):
        keys = [(x, i) for x in range(expansion_periods) for i in range(len(array))]
        vals = dict(zip(keys, array))
        self.add_initial_value(vals)

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
    units = Units.KW


class ElectricalPort(FlexPort):
    """ Flexible electrical port """
    units = Units.KW


class FixedElectricalPort(ElectricalPort):
    """ An electrical port with fixed values (parameters)."""
    opt_type = OptimisationType.Parameter


class Inverter(ElectricalNode):
    """ An inverter is a node with one AC port and at least one DC port.
    Flows from AC to DC, and DC to AC, are subject to conversion efficiencies."""
    max_import: Union[float, None]
    max_export: Union[float, None]
    dc_ac_efficiency: confloat(ge=0, le=1)
    ac_dc_efficiency: confloat(ge=0, le=1)
    dc_ports: dict = {}
    ac_port_name: str = None  # There should generally only be one ac port, so we can just keep its name
    node_rule: int = NodeRule.Custom

    def add_dc_port(self, port_name):
        p = ElectricalPort()
        self.dc_ports[port_name] = p
        self.ports[port_name] = p

    def add_ac_port(self, port_name):
        if self.ac_port_name is not None:
            raise ConfigurationError('AC port already specified for this inverter.')
        else:
            p = ElectricalPort()
            p.set_flow_constraints(max_export=self.max_export, max_import=self.max_import)
            self.ac_port_name = port_name
            self.ports[port_name] = p

    def verify_node(self):
        # Check that all ports are either ac or dc
        all_port_names = [x for x in self.ports.keys()]
        named_ports = [self.ac_port_name]
        named_ports.extend([x for x in self.dc_ports.keys()])
        assert set(all_port_names) == set(named_ports), 'All ports on inverter must be ac or dc.'

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

            return getattr(model, ac_port.pos)[p, t] * self.ac_dc_efficiency + \
                   getattr(model, ac_port.neg)[p, t] / self.dc_ac_efficiency == - (dc_pos + dc_neg)

        ac_port = self.ports[self.ac_port_name]
        setattr(model, f"con_inverter_{self.node_name}", en.Constraint(
            model.Expansion, model.Time, rule=inverter_ac_output_must_track_efficiency))


class EV(ElectricalNode):
    charge_mode: str = None
    available: Union[ArrayType, list]
    usage: Union[ArrayType, list]
    cp_name: str = 'cp'
    tod_charging: Union[ArrayType, list, None] = None
    interval_duration: int
    # Battery attributes
    max_capacity: float
    depth_of_discharge_limit: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    initial_state_of_charge: float

    # next variable is for allowing soc to go below min so as to avoid optimisation failing if there infeasible ev trips
    trip_slack: bool = False
    # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
    soc_conserv: Union[float, None] = None
    soc_conserv_cost: Union[float, None] = None
    V0G_delta: Optional[Union[ArrayType, list]]
    V0G_SOC: Optional[Union[ArrayType, list]]
    V0G_trip_infeasibility: Optional[Union[ArrayType, list]]
    charge_status: Optional[str]

    # notation for having an init function that runs after the pydantic init
    # this will first run pydantic's init, which does all the validation
    # then it will run our defined commands
    def __init__(self, **data) -> None:
        super().__init__(**data)
        # EV always has a storage port
        self.ports['vehicle'] = ElectricalStorage(**data)
        self.ports['vehicle'].enable_trip_slack = self.trip_slack
        # Process any constraints on the storage port
        if self.soc_conserv is not None:  # todo validator
            assert self.soc_conserv_cost is not None, 'soc_conserv requires soc_conserve_cost'
            self.ports['vehicle'].soc_conserv = self.soc_conserv  # kWh
            self.ports['vehicle'].soc_conserv_cost = self.soc_conserv_cost  # dollars per kwh
            self.ports['vehicle'].available = self.available

        # EV always has a fixed trip port
        self.ports['usage'] = ElectricalDemand()
        self.ports['usage'].add_demand_profile_from_array(self.usage, expansion_periods=1)
        # Customise connection point port type based on the charge mode
        if self.charge_mode == 'V0G':
            assert self.trip_slack is True, 'Trip slack must be enabled for V0G charge mode.'
            self.ports[self.cp_name] = ElectricalDemand()
            self.process_V0G_charging(self.interval_duration)
            self.ports[self.cp_name].add_demand_profile_from_array(self.V0G_delta, expansion_periods=1)
        else:
            self.ports[self.cp_name] = ElectricalPort()
            self.ports[self.cp_name].add_active_periods_from_array(self.available, expansion_periods=1)
            if self.charge_mode == 'V1G':
                self.ports[self.cp_name].set_flow_constraints(max_import=self.charging_power_limit, max_export=0.)

        # EV needs a custom transformation because of the positive load convention
        self.create_ev_transformation()

    def create_ev_transformation(self):
        # Create appropriate transformation: vehicle = cp - usage
        t = Transform()
        t.add_lhs_term(self.ports['vehicle'], TransformRule.Both, 1)
        t.add_rhs_term(self.ports['usage'], TransformRule.Both, -1)
        t.add_rhs_term(self.ports[self.cp_name], TransformRule.Both, 1)
        self.add_transformation(t)
        self.node_rule = NodeRule.Transform

    def process_V0G_charging(self, interval_duration):
        success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration)
        self.V0G_delta = ev_delta
        self.V0G_SOC = ev_soc
        if self.tod_charging is not None:
            if success:
                self.charge_status = 'success'
            else:  # force convenience charging
                success, ev_soc, ev_delta, trip_infeasibility = self.V0G_charging(interval_duration, force_conv=True)
                self.charge_status = 'time of day infeasible, convenience success' if success else 'infeasible'
                self.V0G_delta = ev_delta
                self.V0G_SOC = ev_soc

        else:
            self.charge_status = 'success' if success else 'infeasible'
        self.V0G_trip_infeasibility = trip_infeasibility

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

        return success, soc[1:], delta, trip_infeasibility

    def verify_node(self):
        super(EV, self).verify_node()
        if self.charge_mode == 'V0G':
            assert self.ports[self.cp_name].initial_value != 0, 'V0G connection pt port needs demand profile added.'
        else:
            assert self.ports[self.cp_name].active_periods is not None, 'Add available periods to EV connection pt port'
        assert self.ports['usage'].initial_value != 0, 'EV usage port needs usage profile added.'

    def initialise_node(self, model):
        super(EV, self).initialise_node(model)
        if self.charge_mode == 'V0G':
            # Fix the battery state of charge, the slack variable, and battery charging/discharging
            self.fix_port_variable(model, self.ports['vehicle'].soc_value, self.V0G_SOC, expansion_periods=1)
            self.fix_port_variable(model, self.ports['vehicle'].trip_slack, self.V0G_trip_infeasibility,
                                   expansion_periods=1)
            power_profile = np.array(self.V0G_delta) + np.array(self.usage) * -1
            self.fix_port_variable(model, self.ports['vehicle'].port_name, power_profile, expansion_periods=1)


"""

    Carbon ports and nodes

"""


class CarbonSource(Port):
    """ For doing carbon emissions from an asset (node) """
    flows = Flows.Export
    export_constraint = FlowConstraint.NoConstraint
    opt_type = OptimisationType.Variable
    units = Units.CO2


class CarbonSink(Port):
    """ For sinking carbon emissions into an aggregation node """
    flows = Flows.Import
    import_constraint = FlowConstraint.NoConstraint
    opt_type = OptimisationType.Variable
    units = Units.CO2


class CarbonAggregation(Node):
    sum: Optional[BaseModel]

    def __init__(self, **data) -> None:
        super().__init__(**data)
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


class CarbonSinkNode(Node):
    node_rule = NodeRule.Custom

    def verify_node(self):
        for port in self.ports.values():
            if port.units is not Units.CO2:
                raise ConfigurationError('All ports on carbon sink node must have carbon units.')


""""

    Below Zero assets

"""


class GasBoiler(Node):
    """ Gas boiler converts gas to thermal energy """
    gas_to_heat_efficiency: float

    def __init__(self, **data) -> None:
        super().__init__(**data)
        gp = GasPort()
        gp.flows = Flows.Import
        tp = ThermalPort()
        tp.flows = Flows.Export
        self.ports = {'gas': gp, 'heat': tp}
        self.add_boiler_transformation(self.ports['gas'], self.ports['heat'], self.gas_to_heat_efficiency)

    def add_boiler_transformation(self, gas_port, heat_port, gas_to_heat_efficiency):
        # Create appropriate transformation
        t = Transform()
        t.add_lhs_term(heat_port, TransformRule.NegativeComponent, -1)
        t.add_rhs_term(gas_port, TransformRule.PositiveComponent, gas_to_heat_efficiency)
        self.add_transformation(t)
        self.node_rule = NodeRule.Transform

class InputOutputPiecewiseNode(Node):
    """ A node with one input and one output.
     The transformation between input and output is defined by an array of input and output pts,
     which are used to construct a linear piecewise function.
     Alternatively, the transformation can be defined by an array of coefficients of a polynomial function."""
    node_rule = NodeRule.Custom
    input_pts: Optional[dict]
    output_pts: Optional[dict]
    temp_coef: Optional[ArrayType]
    input_coef: Optional[ArrayType]
    n_pts: Optional[int] = 5
    max_input: confloat(ge=0.)
    max_output: confloat(le=0.)
    temperature_array: Optional[ArrayType]  # temperature time series

    def __init__(self, **data):
        super().__init__(**data)
        if self.temp_coef is not None:
            assert self.temperature_array is not None, 'if using temperature coefficients please enter temperature array'

    def set_input_output_breakpoints(self, input_array, output_array, time_periods, expansion_periods=1):
        self._validate_input_output_breakpoints(input_array, output_array)
        self._add_input_pts_from_array(input_array, time_periods, expansion_periods)
        self._add_output_pts_from_array(output_array, time_periods, expansion_periods)

    def _validate_input_output_breakpoints(self, input_array, output_array):
        assert len(input_array) == len(output_array), 'input and output arrays should be same length.'
        if (min(input_array) > 0) or (max(input_array) < self.max_input):
            print('Input breakpoints should ideally be defined over the entire input range.')
        if (min(output_array) > self.max_output) or (max(output_array) < 0):
            print('Output breakpoints should ideally be defined over the entire output range.')

    def _add_input_pts_from_array(self, array, time_periods, expansion_periods):
        self.input_pts = add_time_and_expansion_index_to_values(array, time_periods, expansion_periods)

    def _add_output_pts_from_array(self, array, time_periods, expansion_periods):
        self.output_pts = add_time_and_expansion_index_to_values(array, time_periods, expansion_periods)

    def add_input_port(self, port_unit, slack=False):
        p = FlexPort()
        p.units = port_unit
        p.flows = Flows.Import
        p.import_constraint = FlowConstraint.Fixed
        p.set_flow_constraints(max_import=self.max_input, max_export=0., slack=slack)
        self.ports['input'] = p

    def add_output_port(self, port_unit, slack=False):
        p = FlexPort()
        p.units = port_unit
        p.flows = Flows.Export
        p.export_constraint = FlowConstraint.Fixed
        p.set_flow_constraints(max_import=0., max_export=self.max_output, slack=slack)
        self.ports['output'] = p

    def initialise_node(self, model):
        """ Creating and modifying variables """
        super(InputOutputPiecewiseNode, self).initialise_node(model)
        if self.temp_coef is not None:
            # Create x and y points for piecewise function from coefficient array
            x = np.linspace(0, self.max_input, self.n_pts)
            if self.input_pts is not None:
                print('Input points have already been specified, overwriting.')
            if self.output_pts is not None:
                print('Output points have already been specified, overwriting.')
            self.input_pts, self.output_pts = create_input_output_pts_from_coefficients(temp_coef=self.temp_coef,
                                                                                        input_coef=self.input_coef,
                                                                                        temperature_array=self.temperature_array,
                                                                                        xpts=x,
                                                                                        model=model)

        # Bound our input and output variables
        set_var_bounds(var_name=self.ports['input'].port_name, model=model, lb=0., ub=self.max_input)
        set_var_bounds(var_name=self.ports['output'].port_name, model=model, lb=self.max_output, ub=0.)

    def apply_node_constraints(self, model):

        # Get our input/output pyomo variables
        xvar = getattr(model, self.ports['input'].port_name)
        yvar = getattr(model, self.ports['output'].port_name)

        # Get our piecewise points
        xdata = self.input_pts
        ydata = self.output_pts

        # Set the piecewise function up using the variables and the data points.
        con_name = f"piecewise_con_{self.node_name}"
        setattr(model, con_name, en.Piecewise(model.Expansion,
                                              model.Time,
                                              yvar,
                                              xvar,
                                              pw_pts=xdata, pw_constr_type='EQ', f_rule=ydata, pw_repn='SOS2'))

    def get_cop(self, optimiser):
        """ Returns the coefficient of performance (output/input)"""
        _input = optimiser.values(self.ports['input'].port_name)
        _output = optimiser.values(self.ports['output'].port_name)
        cop = np.zeros(len(_input))
        for i in range(len(_input)):
            cop[i] = _output[i] / _input[i]

        return cop * -1


class HeatPump(InputOutputPiecewiseNode):
    """
    A heat pump converts an electrical input to a thermal heating or cooling output.
    """


class Chiller(InputOutputPiecewiseNode):
    """
    A chiller converts an electrical input to a thermal cooling output.
    """

    def __init__(self, **data):
        super().__init__(**data)
        self.add_input_port(Units.KW)
        self.add_output_port(Units.KWT)


""" 
Thermal assets
"""


class HeatingOrCoolingLoad(Sink):

    def __init__(self):
        super(HeatingOrCoolingLoad, self).__init__()
        self.units = Units.KWT


class ThermalPort(Port):

    def __init__(self):
        super(ThermalPort, self).__init__()
        self.units = Units.KWT
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable


"""
Gas assets
"""


class GasPort(Port):

    def __init__(self):
        super(GasPort, self).__init__()
        self.units = Units.JPS
        self.flows = Flows.Both
        self.import_constraint = FlowConstraint.NoConstraint
        self.export_constraint = FlowConstraint.NoConstraint
        self.opt_type = OptimisationType.Variable


class GasDemand(Sink):

    def __init__(self):
        super(GasDemand, self).__init__()
        self.units = Units.Jps

    def add_demand_profile_from_array(self, array, expansion_intervals):
        self.add_sink_profile_from_array(array, expansion_intervals)
