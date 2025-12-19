import warnings
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Type, Union, cast

import networkx as nx
import pandas as pd
import pyomo.environ as en
import shortuuid
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, validator

from echo.configuration import (
    FlowConstraint,
    Flows,
    OptimisationType,
    TransformRule,
    Units,
)
from echo.constants import negative_variable_component, positive_variable_component
from echo.exceptions import ConfigurationError, validate
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeExpandableType,
    TimeSeriesData,
    domain_from_flow,
    expand_as_array,
    expand_as_dict,
    generate_array_constraint,
    set_var_bounds_from_dict,
    to_initial_values,
)
from echo.validators import ArrayType, export_cons_check, import_cons_check


class BaseModel(PydanticBaseModel):
    """Create a modified base model with the config we want."""

    class Config:
        validate_assignment = True  # Set to true so that we re-validate when we update a model field
        extra = "ignore"  # extra attributes are ignored
        arbitrary_types_allowed = True


ConstraintValueType = Union[ArrayType, float]


class Port(BaseModel):
    # Pydantic attribute declaration follows this format:
    # attribute_name: type = default_value

    units: Units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
    initial_value: dict = 0
    initial_value_ref: Optional[str]  # string ref to df column
    initial_value_scaling: Optional[int]  # scaling factor for initial values
    flow_type: OptimisationType = OptimisationType.NA
    uid: Optional[str] = Field(default_factory=shortuuid.uuid)
    port_name: str = ""
    flows: Flows = Flows.NA  # What flow directions are possible (import, export, both)
    # Used to define the nature of import / export directions and constraints
    import_constraint: FlowConstraint = FlowConstraint.NA
    import_constraint_value: Optional[ConstraintValueType] = None
    export_constraint: FlowConstraint = FlowConstraint.NA
    export_constraint_value: Optional[ConstraintValueType] = None
    active_periods: Optional[dict[tuple[int, int], Any]] = None
    slack: bool = False
    objective: Union[float, en.numeric_expr.NumericExpression] = 0  # this will eventually be a pyomo expression

    # Validators for import/export constraint values
    import_con_sign = validator("import_constraint_value", allow_reuse=True)(import_cons_check)
    export_con_sign = validator("export_constraint_value", allow_reuse=True)(export_cons_check)

    @property
    def pos(self):
        return positive_variable_component + self.port_name

    @property
    def neg(self):
        return negative_variable_component + self.port_name

    @property
    def is_pos(self):
        return f"is_pos_{self.port_name}"

    @property
    def import_con_val(self):
        return f"import_con_val_{self.port_name}"

    @property
    def export_con_val(self):
        return f"export_con_val_{self.port_name}"

    @property
    def import_slack(self):
        return f"import_slack_{self.port_name}"

    @property
    def import_slack_max(self):
        return f"import_slack_max_{self.port_name}"

    @property
    def export_slack(self):
        return f"export_slack_{self.port_name}"

    @property
    def export_slack_max(self):
        return f"export_slack_max_{self.port_name}"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.port_name:  # if no name is provided, give it a default name using the uid
            self.port_name = "port_" + str(self.uid)

    def set_flow_constraints(
        self,
        max_import: Optional[ConstraintValueType],
        max_export: Optional[ConstraintValueType],
        slack: Optional[bool] = False,
    ):
        """Sets the values of port flow constraints.

        Args:
            max_import: max allowable import into port (float, array, or None)
            max_export: max allowable export out of port (float, array, or None)
            slack: bool, whether we want to allow slack in the constraint
        """
        if max_import is not None:
            self.import_constraint = FlowConstraint.Fixed
            self.import_constraint_value = max_import

        if max_export is not None:
            self.export_constraint = FlowConstraint.Fixed
            self.export_constraint_value = max_export

        if slack is not None:
            self.slack = slack

    def process_initial_value(self, initial_val, expansion_periods: int = 1, time_periods: Optional[int] = None):
        if isinstance(initial_val, dict):
            self.set_initial_value(initial_val)
        elif isinstance(initial_val, str):
            self.initial_value_ref = initial_val
        elif hasattr(initial_val, "__iter__"):
            self.set_initial_value_from_array(initial_val, expansion_periods, time_periods)

    def verify_port(self):
        """Used to verify that a port has been set up appropriately"""
        if self.flows is Flows.NA:
            raise ConfigurationError("The flows value cannot be set to a value of NA.")

        if (self.flows is Flows.Import) or (self.flows is Flows.Both):
            if self.import_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Import FlowConstraint cannot be set to a value of NA.")
            if self.import_constraint is FlowConstraint.Fixed and self.import_constraint_value is None:
                raise ConfigurationError(
                    "The Import flow constraint value cannot be set to None when an Import constraint exists."
                )

        if (self.flows is Flows.Export) or (self.flows is Flows.Both):
            if self.export_constraint is FlowConstraint.NA:
                raise ConfigurationError("The Export FlowConstraint cannot be set to a value of NA.")
            if self.export_constraint is FlowConstraint.Fixed and self.export_constraint_value is None:
                raise ConfigurationError(
                    "The Export flow constraint value cannot be set to None when an Export constraint exists."
                )

        if self.flow_type is OptimisationType.NA:
            raise ConfigurationError("The Optimisation Type has to be configured before instantiation.")

        if self.units is Units.NA:
            raise ConfigurationError("The Units parameter has to be configured before instantiation.")

    def _add_flow_variable_to_model(self, model: EchoConcreteModel, initial_value, domain):
        setattr(
            model,
            self.port_name,
            en.Var(model.Expansion, model.Time, initialize=initial_value, domain=domain),
        )

    def _add_active_period_constraints_to_model(self, model: EchoConcreteModel):
        port_active_periods = self.active_periods

        def on_off_rule1(model: EchoConcreteModel, p, t):
            return getattr(model, self.port_name)[p, t] <= port_active_periods[p, t] * model.bigM

        def on_off_rule2(model: EchoConcreteModel, p, t):
            return getattr(model, self.port_name)[p, t] >= -port_active_periods[p, t] * model.bigM

        setattr(
            model,
            f"active_con1_{self.port_name}",
            en.Constraint(model.Expansion, model.Time, rule=on_off_rule1),
        )
        setattr(
            model,
            f"active_con2_{self.port_name}",
            en.Constraint(model.Expansion, model.Time, rule=on_off_rule2),
        )

    def _add_import_constraints_to_model(self, model: EchoConcreteModel):
        # Add import constraint parameter
        time_periods = len(model.Time)
        exp_periods = len(model.Expansion)
        # Generate an array of constraints (ie indexed by time and expansion period)
        import_constraint_dict = generate_array_constraint(self.import_constraint_value, time_periods, exp_periods)
        setattr(
            model,
            self.import_con_val,
            en.Param(
                model.Expansion,
                model.Time,
                initialize=import_constraint_dict,
                domain=en.NonNegativeReals,
            ),
        )

        if self.slack:
            self._add_slack_import_constraints_to_model(model=model)
        else:
            set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=import_constraint_dict, lb=None)

    def _add_slack_import_constraints_to_model(self, model: EchoConcreteModel):
        """Adds import capacity constraint with slack rules"""

        # Add export capacity slack constraint
        def import_cap_rule_slack(model: EchoConcreteModel, p, t):
            return (
                getattr(model, self.port_name)[p, t] + getattr(model, self.import_slack)[p, t]
                <= getattr(model, self.import_con_val)[p, t]
            )

        con_name = "import_con_" + self.port_name
        setattr(
            model,
            self.import_slack,
            en.Var(
                model.Expansion,
                model.Time,
                initialize=0,
                domain=en.NonPositiveReals,
            ),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=import_cap_rule_slack),
        )

        # Add import capacity slack max constraint
        def import_cap_slack_max_rule(model: EchoConcreteModel, p, t):
            return getattr(model, self.import_slack)[p, t] >= getattr(model, self.import_slack_max)

        con_name = "import_con_max_" + self.port_name
        setattr(
            model,
            self.import_slack_max,
            en.Var(initialize=0, domain=en.NonPositiveReals),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=import_cap_slack_max_rule),
        )

    def _add_export_constraints_to_model(self, model: EchoConcreteModel):
        # Add export constraint parameter
        time_periods = len(model.Time)
        exp_periods = len(model.Expansion)
        # Generate an array of constraints (ie indexed by time and expansion period)
        export_constraint_dict = generate_array_constraint(self.export_constraint_value, time_periods, exp_periods)
        setattr(
            model,
            self.export_con_val,
            en.Param(
                model.Expansion,
                model.Time,
                initialize=export_constraint_dict,
                domain=en.NonPositiveReals,
            ),
        )

        if self.slack:
            self._add_slack_export_constraints_to_model(model=model)
        else:
            set_var_bounds_from_dict(model=model, var_name=self.port_name, ub=None, lb=export_constraint_dict)

    def _add_slack_export_constraints_to_model(self, model: EchoConcreteModel):
        """Adds import capacity constraint with slack rules"""

        # Add export capacity slack constraint
        def export_cap_rule_slack(model: EchoConcreteModel, p, t):
            return (
                getattr(model, self.port_name)[p, t] + getattr(model, self.export_slack)[p, t]
                >= getattr(model, self.export_con_val)[p, t]
            )

        con_name = "export_con_" + self.port_name
        setattr(
            model,
            self.export_slack,
            en.Var(
                model.Expansion,
                model.Time,
                initialize=0,
                domain=en.NonNegativeReals,
            ),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=export_cap_rule_slack),
        )

        # Add export capacity slack max constraint
        def export_cap_slack_max_rule(model: EchoConcreteModel, p, t):
            return getattr(model, self.export_slack)[p, t] <= getattr(model, self.export_slack_max)

        con_name = "export_con_max_" + self.port_name
        setattr(
            model,
            self.export_slack_max,
            en.Var(initialize=0, domain=en.NonNegativeReals),
        )
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=export_cap_slack_max_rule),
        )

    def _determine_initial_value(self, time_periods: int, expansion_periods: int, profile: pd.DataFrame):
        initial_value_scaling = self.initial_value_scaling or 1
        if self.initial_value_ref is not None:
            initial_val = to_initial_values(
                profile,
                self.initial_value_ref,
                time_periods,
                expansion_periods,
                scaling=initial_value_scaling,
            )
        else:
            # TODO: add scaling for explicit initial value
            initial_val = self.initial_value
        return initial_val

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame):
        """Creates pyomo vars, params, and constraints for the port."""
        initial_value = self._determine_initial_value(
            time_periods=len(model.Time), expansion_periods=len(model.Expansion), profile=profile
        )

        domain = domain_from_flow(self.flows)

        # Flow is always represented with a pyomo variable.
        # This gives us flexibility for converting between a variable and parameter with fix/unfix
        self._add_flow_variable_to_model(model=model, initial_value=initial_value, domain=domain)

        # Convert flow variable to parameter if requested.
        if self.flow_type is OptimisationType.Parameter:
            getattr(model, self.port_name).fix()  # Fix the variable - equivalent to setting it as an 'en.Param'

        if self.import_constraint is FlowConstraint.Fixed:  # only apply import/export constraints to variables
            self._add_import_constraints_to_model(model=model)

        if self.export_constraint is FlowConstraint.Fixed:  # only apply these constraints to variables
            self._add_export_constraints_to_model(model=model)

        if self.active_periods is not None:
            self._add_active_period_constraints_to_model(model=model)

    def constrain_pos_neg(self, model: EchoConcreteModel):
        """Applies a mixed integer constraint that splits a port var into positive and negative components"""
        if hasattr(model, self.pos) is False:
            setattr(model, self.pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, self.neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
            setattr(model, self.is_pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

            con_rule = self.factory_pos_neg_flows(self.port_name, self.pos, self.neg)
            con_name = positive_variable_component + negative_variable_component + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

            def only_pos_or_neg_one(model: EchoConcreteModel, p, t):
                return getattr(model, self.pos)[p, t] <= getattr(model, self.is_pos)[p, t] * model.bigM

            setattr(
                model,
                f"pos_neg_con1_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_one),
            )

            def only_pos_or_neg_two(model: EchoConcreteModel, p, t):
                return getattr(model, self.neg)[p, t] >= (getattr(model, self.is_pos)[p, t] - 1) * model.bigM

            setattr(
                model,
                f"pos_neg_con2_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_two),
            )

    @staticmethod
    def factory_pos_neg_flows(var_name, pos_name, neg_name):
        def constraint(model: EchoConcreteModel, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == (
                getattr(model, pos_name)[expansion_interval, time_interval]
                + getattr(model, neg_name)[expansion_interval, time_interval]
            )

        return constraint

    def set_initial_value(self, initial_value: dict):
        """Sets initial port value which will be used to initialise the pyomo var/param
        Args:
            initial_value: dict of initial values
        """
        self.initial_value = initial_value

    def set_initial_value_from_timeseriesdata(self, time_series_data: TimeSeriesData):
        self.set_initial_value(expand_as_dict(time_series_data))

    def set_initial_value_from_array(
        self, array: TimeExpandableType, expansion_periods: int = 1, time_periods: Optional[int] = None
    ):
        """Sets initial port value which is used to initialise the pyomo var/param

        Args:
            array: array, list of initial values. Should have either: length = time_periods,
                or length = time_periods*expansion_periods
            time_periods: int, optional number of time periods. If=None, assume that time_periods = len(array)
            expansion_periods: number of expansion periods
        """
        if time_periods is None:
            time_periods = len(array)

        time_series_data = TimeSeriesData(
            value=array, num_time_intervals=time_periods, num_expansion_intervals=expansion_periods
        )
        self.set_initial_value_from_timeseriesdata(time_series_data=time_series_data)

    def set_active_periods_from_array(self, array: Any, expansion_periods: int = 1, time_periods: Optional[int] = None):
        """Sets port active periods
        Args:
            array: array, list of active periods as bool values
            expansion_periods: number of expansion periods (int)
        """
        if time_periods is None:
            time_periods = len(array)

        time_series_data = TimeSeriesData(
            value=array, num_time_intervals=time_periods, num_expansion_intervals=expansion_periods
        )
        self.active_periods = expand_as_dict(time_series_data)

    def add_objective(self, model: EchoConcreteModel):
        """Populates the port attribute 'objectives' with any pyomo expressions that are needed
        Args:
            model: pyomo concrete model
        """
        total = 0
        if self.slack is True:
            if hasattr(model, self.import_slack) is True:
                total += -1 * getattr(model, self.import_slack_max) * model.bigM
                total += (
                    -1
                    * sum(getattr(model, self.import_slack)[p, t] for p in model.Expansion for t in model.Time)
                    * model.bigM
                    * 0.1
                )
            if hasattr(model, self.export_slack) is True:
                total += getattr(model, self.export_slack_max) * model.bigM
                total += (
                    sum(getattr(model, self.export_slack)[p, t] for p in model.Expansion for t in model.Time)
                    * model.bigM
                    * 0.1
                )

        self.objective += total


@dataclass
class TransformTerm:
    var: Port
    rule: TransformRule
    weight: TimeExpandableType


class Transform(BaseModel):
    """An object for carrying a generic linear node transformation."""

    uid: str = Field(default_factory=shortuuid.uuid)
    lhs: list[TransformTerm] = []
    rhs = 0

    def __init__(self, lhs_terms: list[TransformTerm] = [], **data):
        super().__init__(**data)
        if lhs_terms:
            self.lhs = lhs_terms

    @property
    def transform_name(self):
        return "transform_" + str(self.uid)

    def _add_transform_to_model(self, model: EchoConcreteModel):
        # Check if we need to create pos/neg components
        for term in self.lhs:
            if term.rule is not TransformRule.Both:
                var = term.var
                var.constrain_pos_neg(model)


class Node(BaseModel):
    """
    Nodes are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented.
    """

    node_name: str = ""
    uid: str = Field(default_factory=shortuuid.uuid)
    ports: dict[str, Port] = {}
    objective: Union[float, en.numeric_expr.NumericExpression] = 0  # For adding any node objectives

    @property
    def inflow(self):
        return f"inflow_{self.node_name}"

    def __init__(self, **data):
        super().__init__(**data)
        if not self.node_name:
            self.node_name = "node_" + str(self.uid)

    def add_port(self, name: str, port: Port):
        if self.ports.get(name) is None:
            self.ports[name] = port
        else:
            raise ConfigurationError(f"Port with name {name} is already defined on node {self.node_name}")

    def add_ports_from_list(self, names: Iterable[str], port_type: Type[Port], **kwargs):
        """Creates a set of ports (using port_type) and adds them to this Node. The ports will be constructed
        using port_type and the supplied kwargs"""
        for name in names:
            self.add_port(name, port_type(**kwargs))

    def get_port(self, port_name: str):
        if self.ports.get(port_name) is not None:
            return self.ports.get(port_name)

    def verify_node(self):
        if bool(self.ports) is False:
            raise ConfigurationError("A node must have at least one port.")

    def add_node_to_model(self, model: EchoConcreteModel, profile):
        for port in self.ports.values():
            port.verify_port()
            port.add_port_to_model(model, profile)

    def add_objective(self, model: EchoConcreteModel):
        total = 0

        self.objective += total

    def num_ports(self):
        return len(self.ports)

    def apply_node_constraints(self, model: EchoConcreteModel):
        """This should be overridden in the base class"""
        pass

    def get_port_name_to_port_dict_name_map(self):
        return {port.port_name: port_dict_name for port_dict_name, port in self.ports.items()}


class TransformNode(Node):
    """Implements node constraints using Transforms"""

    transformations: dict[str, Transform] = {}

    def add_transformation(self, transformation_obj: Transform):
        """Adds a transformation object to a node.
        Args:
            transformation_obj: Transform
        """
        self.transformations[transformation_obj.uid] = transformation_obj

    def add_input_output_transformation(self, input_port: Port, output_port: Port, input_weight: float):
        lhs_terms = [
            TransformTerm(var=output_port, rule=TransformRule.Both, weight=1),
            TransformTerm(var=input_port, rule=TransformRule.Both, weight=-input_weight),
        ]
        t = Transform(lhs_terms=lhs_terms)
        self.add_transformation(t)

    def add_emission_transformation(self, emitting_port: Port, carbon_port: Port, emission_factor: float):
        """Creates an emission transformation and adds to the node.
        Args:
            emitting_port: port object that generates emissions when exporting (when negative)
            carbon_port: port object that represents carbon flows out of the node
            emission_factor: a ratio = emissions generated/emitting unit generated (float), or an array of values
        """
        lhs_terms = [
            TransformTerm(var=carbon_port, rule=TransformRule.Neg, weight=1),
            TransformTerm(var=emitting_port, rule=TransformRule.Neg, weight=-emission_factor),
        ]
        t = Transform(lhs_terms=lhs_terms)
        self.add_transformation(t)

    def verify_node(self):
        super(TransformNode, self).verify_node()

        if not self.transformations:
            raise ConfigurationError("Node has Transform rule but Transformation object(s) has not been added to node.")

    def apply_node_constraints(self, model: EchoConcreteModel):
        def transform(model: EchoConcreteModel, p, t):  # Generic transformation node
            lhs = 0
            for term in current_transform.lhs:
                weight = expand_as_array(
                    TimeSeriesData(
                        value=term.weight,
                        num_expansion_intervals=len(model.Expansion),
                        num_time_intervals=len(model.Time),
                    )
                )
                rule = term.rule
                if rule is TransformRule.Both:
                    var_name = term.var.port_name
                elif rule is TransformRule.Pos:
                    var_name = term.var.pos
                elif rule is TransformRule.Neg:
                    var_name = term.var.neg
                else:
                    raise Exception(f"Unsupported transform rule {rule} for term {term}")
                lhs += getattr(model, var_name)[p, t] * weight[p, t]
            return lhs == current_transform.rhs

        for current_transform in self.transformations.values():
            current_transform._add_transform_to_model(model)  # make sure that all variables have been initialised
            con_name = "transformation_con_" + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=transform))


class Edge(BaseModel):
    """
    Edges are used to connect nodes. For an edge (x, y) where x and y are nodes,
    the edge value is equal to the flow from x->y plus the flow from y->x.
    """

    uid: str = Field(default_factory=shortuuid.uuid)
    edge_name: Optional[str] = None
    vertices: tuple[Port, Port]
    nodes: Optional[tuple[str, str]]  # tuple of node names - todo make this required
    tariff: Optional[Union[list, None]]

    def __init__(self, **data):
        super().__init__(**data)
        if self.edge_name is None:
            self.edge_name = "edge_" + str(self.uid)

    def add_vertices(self, obj1: Port, obj2: Port):
        """Adds edge vertices (which are ports on nodes)
        Args:
            obj1: port object
            obj2: port object
        """
        self.vertices = (obj1, obj2)

    def verify_edge(self):
        port1 = self.vertices[0]
        port2 = self.vertices[1]

        if (port1.flows is Flows.Export) and (port2.flows is Flows.Export):
            raise ConfigurationError("Port flow constraints do not allow any flow along the edge.")
        if (port1.flows is Flows.Import) and (port2.flows is Flows.Import):
            raise ConfigurationError("Port flow constraints do not allow any flow along the edge.")

    def add_edge_to_model(self, model: EchoConcreteModel):
        """Applies edge constraint: ``port1 = -1 *port2``

        Args:
            model: pyomo concrete model
        """

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        def edge_constraint_rule(model: EchoConcreteModel, p, t):
            return getattr(model, port1.port_name)[p, t] + getattr(model, port2.port_name)[p, t] == 0

        con_name = "edge_con_" + port1.port_name + "_" + port2.port_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=edge_constraint_rule))

    def get_max_flow_along_edge(self, forwards: bool = True):
        max_flow = None
        if forwards is True:
            port1 = self.vertices[0]
            port2 = self.vertices[1]
        else:
            port1 = self.vertices[1]
            port2 = self.vertices[0]
        if port1.export_constraint_value is not None:
            max_flow = port1.export_constraint_value
        if port2.import_constraint_value is not None:
            if max_flow is not None:
                max_flow = min(max_flow, port2.import_constraint_value)
            else:
                max_flow = port2.import_constraint_value
        return max_flow


class Path(BaseModel):
    """A path is a sequence of distinct vertices (nodes)."""

    edge_ports: list[tuple[Port, Port]] = []  # list of edge name tuples
    vertices: list  # list of node names
    uid: str = Field(default_factory=shortuuid.uuid)
    path_name: Optional[str] = None
    units = Units.KW
    regularise: bool = False
    objective: Union[float, en.numeric_expr.NumericExpression] = 0

    flow_value: str = ""
    contingency_neg: Optional[str]
    contingency_pos: Optional[str]
    path_tariff: Optional[str]
    slack: Optional[str]

    def __init__(self, **data):
        super().__init__(**data)
        if self.path_name is None:
            self.path_name = "path_" + str(self.uid)
        self.flow_value = "flow_value_" + self.path_name

    def add_vertices(self, vertex_list: list):
        if hasattr(vertex_list[0], "node_name"):
            vertex_list = [i.node_name for i in vertex_list]
        self.vertices = vertex_list

    def add_path_to_model(self, model: EchoConcreteModel):
        setattr(
            model,
            self.flow_value,
            en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals),
        )

    def add_objective(self, model: EchoConcreteModel):
        total = 0

        if self.regularise is True:
            total += (
                sum(
                    getattr(model, self.flow_value)[p, t] * getattr(model, self.flow_value)[p, t]
                    for p in model.Expansion
                    for t in model.Time
                )
                * 0.0000001
            )

        self.objective += total


class OptimisationGraph(BaseModel):
    node_obj: dict[str, Node] = {}  # Nodes keyed by their node_name
    edge_obj: dict[tuple[str, str], Edge] = {}
    paths: dict[tuple, Path] = {}

    def __init__(self, **data):
        super().__init__(**data)

    def node_name_list(self):
        return list(self.node_obj.keys())

    def edge_list(self):
        return list(self.edge_obj.keys())

    def convert_to_nx(self) -> nx.Graph:
        """Converts the OptimisationGraph to a networkx graph, where nx nodes are echo node names and nx edges are
        nx node pairs"""
        g = nx.Graph()
        g.add_nodes_from(self.node_obj.keys())
        g.add_edges_from(self.edge_obj.keys())
        return g

    def _add_single_node(self, node_obj: Node):
        validate(node_obj.node_name not in self.node_obj, "Node '{}' already defined".format(node_obj.node_name))
        self.node_obj[node_obj.node_name] = node_obj

    def delete_node(self, node_name: str):
        if self.get_node(node_name) is not None:
            del self.node_obj[node_name]
        else:
            print(f"Node {node_name} not found.")

    def delete_edge(self, edge_nodes: tuple[str, str]):
        if self.get_edge(edge_nodes) is not None:
            del self.edge_obj[edge_nodes]
        else:
            print(f"Edge {edge_nodes} not found.")

    def add_node_obj(self, node: Union[list, Node]):
        """Adds either a single node or list of nodes to graph"""
        # todo phase out this method
        if isinstance(node, list):
            for n in node:
                self._add_single_node(n)
        else:
            self._add_single_node(node)

    def add_nodes_from(self, nodes: list[Node]):
        """Adds a list of nodes to the graph."""
        for n in nodes:
            self._add_single_node(n)

    def add_node(self, node: Node):
        """Adds a single node to the graph."""
        self._add_single_node(node)

    def get_node(self, node_name: str):
        """Returns node object given node name"""
        return self.node_obj.get(node_name)

    def get_edge(self, nodes: tuple[str, str], warn: bool = False):
        """Retrieves the edge that connects a tuple of nodes, if an edge exists."""
        if self.edge_obj.get(nodes) is not None:
            return self.edge_obj.get(nodes)

        reversed_nodes = (nodes[1], nodes[0])
        edge = self.edge_obj.get(reversed_nodes)
        if edge is not None:
            return edge
        elif warn:
            print("Edge between {} and {} does not exist".format(nodes[0], nodes[1]))

    def _add_single_edge(self, edge_obj: Edge):
        port1 = edge_obj.vertices[0]
        port2 = edge_obj.vertices[1]
        validate(port1.units == port2.units, f"Ports on edge must have matching units. {port1.units} != {port2.units}")
        if edge_obj.nodes is None:
            # Want to avoid doing this lookup - very slow
            node1_name = self.lookup_node_names_from_port(port1)
            node2_name = self.lookup_node_names_from_port(port2)
        else:
            node1_name = edge_obj.nodes[0]
            node2_name = edge_obj.nodes[1]
        # Need to check whether an edge already exists between these two nodes
        if self.get_edge(nodes=(node1_name, node2_name)) is not None:
            raise ValueError("An edge between these nodes already exists")

        self.edge_obj[(node1_name, node2_name)] = edge_obj

    def add_edge_obj(self, edge: Union[list[Edge], Edge]):
        # todo phase out this method
        if isinstance(edge, list):
            for e in edge:
                self._add_single_edge(e)
        else:
            self._add_single_edge(edge)

    def add_edges_from(self, edge: list[Edge]):
        for e in edge:
            self._add_single_edge(e)

    def add_edge(self, edge: Edge):
        self._add_single_edge(edge)

    def connect_ports_and_create_edge(
        self,
        port1: Port,
        port2: Port,
        edge_name: Optional[str] = None,
        nodes: Optional[tuple[str]] = None,
        warn: bool = False,
    ):
        """Creates an edge between port1 and port2 and adds it to the graph"""
        if nodes is None and warn is True:
            print("No edge nodes defined. Defining edge nodes here speeds up constructing of echo graph.")
        e = Edge(vertices=(port1, port2), edge_name=edge_name, nodes=nodes)
        self.add_edge(e)

    def lookup_node_names_from_port(self, port: Port) -> str:
        """Returns node name of the node that a specified port belongs to, if the port belongs to a node."""
        for node_name, node in self.node_obj.items():
            for p in node.ports.values():
                if port == p:
                    return node_name
        raise ConfigurationError(f"Port {port.port_name} is not part of any node, or node has not been added to graph.")

    def get_ports_on_edge_from_nodes(self, node1: str, node2: str) -> Optional[tuple[Port, Port]]:
        """Returns the ports that are on the edge from node1 to node2."""
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

        return None

    def get_sources_and_sinks(self):
        """Returns a set that contains all source and sink nodes."""
        validate(bool(self.paths) is True, "Create paths before retrieving sources and sinks.")
        sources_or_sinks = set()
        for path in self.paths.values():
            sources_or_sinks.add(path.vertices[0])
            sources_or_sinks.add(path.vertices[-1])
        return sources_or_sinks

    def get_path(self, path_vertices: Union[list[Node], list[str]]):
        """Looks up a path using a list of path vertices (nodes, or node names)."""
        if isinstance(path_vertices[0], Node):
            name_key = [cast(Node, node).node_name for node in path_vertices]
            return self.paths[tuple(name_key)]
        else:
            if self.paths.get(tuple(path_vertices)) is not None:
                return self.paths[tuple(path_vertices)]
            else:
                raise ValueError(f"No path with vertices {path_vertices} is defined.")

    def verify_paths(self):
        """Verifies that our paths meet the assumptions required to correctly do flow tracing."""
        all_nodes = self.get_sources_and_sinks()
        for node in all_nodes:
            for path in self.paths.values():
                if node in path.vertices[1:-1]:
                    # if the source/sink node appears in the middle of another path, the optimiser will fail
                    # A node can't be both a tellegen node and a source/sink node
                    raise ConfigurationError("Source/sink node is being treated as a tellegen node.")

    def create_path_objects(
        self,
        sources: Union[list[Node], list[str]],
        sinks: Union[list[Node], list[str]],
        path_unit: Units = Units.KW,
        regularise: bool = False,
    ):
        """Creates path objects according to source/sink lists provided."""
        warnings.warn(
            "Path tracing is still experimental. If you are generating paths to use path tariffs, please consider "
            + "whether you can convert these tariffs to point/port tariffs."
        )
        all_paths = {}
        graph = self.convert_to_nx()
        if isinstance(sources[0], Node):
            sources = [cast(Node, i).node_name for i in sources]
        if isinstance(sinks[0], Node):
            sinks = [cast(Node, i).node_name for i in sinks]

        tellegen_node_set = set()  # create a set to store list of nodes that are treated as tellegen nodes
        source_sink_set = set(sources + sinks)  # create a set of nodes that are treated as sinks/sources
        for source_node in sources:
            for sink_node in sinks:
                if source_node is not sink_node:
                    # Find all the paths, just using the node names
                    simple_paths = nx.all_simple_paths(graph, source_node, sink_node)
                    simple_edges = nx.all_simple_edge_paths(graph, source_node, sink_node)
                    for vertex_list, edge_list in zip(simple_paths, simple_edges):
                        tellegen_node_set.update(vertex_list[1:-1])  # update set of tellegen nodes
                        p = self._create_path_object(vertex_list, edge_list, regularise, path_unit)  # create path
                        all_paths[tuple(vertex_list)] = p

        intersection = source_sink_set.intersection(tellegen_node_set)  # check overlap of tellegen and src/sink nodes
        validate(len(intersection) == 0, f"Nodes '{intersection}' are being treated as both tellegen and source/sink.")
        self.paths = all_paths

    def _create_path_object(self, vertex_list: list, edge_list: list, regularise: bool, path_unit: Units):
        """Creates a path object"""
        p = Path(vertices=vertex_list, regularise=regularise, units=path_unit)  # Create path object
        for edge in edge_list:
            edge_ports = self.get_ports_on_edge_from_nodes(edge[0], edge[1])
            validate(edge_ports is not None, f"get_ports_on_edge_from_nodes return None for edges {edge[0]}, {edge[1]}")
            p.edge_ports.append(edge_ports)
        return p

    def apply_path_constraints(self, model: EchoConcreteModel):
        """Applies path tracing constraints to model"""

        def path_flow_rule(model: EchoConcreteModel, p, t):
            a = 0
            for path in self.paths.values():  # Iterate through all paths in the model
                if path.vertices[0] is current_node_name:  # If the path starts at the current node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
                if path.vertices[-1] is current_node_name:  # If the path ends at the current node
                    a -= getattr(model, path.flow_value)[p, t]  # Subtract the flow value
            return a == getattr(model, current_port.port_name)[p, t] * -1  # Flows out - flows in = -1 * port

        def only_inflow_or_outflow1(model: EchoConcreteModel, p, t):
            a = 0
            for path in self.paths.values():
                if path.vertices[-1] is current_node_name:  # If the path ends at the current node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
            return (
                a <= getattr(model, current_node_obj.inflow)[p, t] * model.bigM
            )  # Incoming paths can only be non-zero if inflow=1

        def only_inflow_or_outflow2(model: EchoConcreteModel, p, t):
            a = 0
            for path in self.paths.values():
                if path.vertices[0] is current_node_name:  # If the path starts at the node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
            return (
                a <= (1 - getattr(model, current_node_obj.inflow)[p, t]) * model.bigM
            )  # Outgoing paths can only be non-zero if inflow=0

        sources_and_sinks = self.get_sources_and_sinks()  # returns concatenated list of all source/sink nodes
        for current_node_name in sources_and_sinks:  # Iterate through the source/sink nodes
            current_node_obj = self.node_obj[current_node_name]  # get the node obj
            for path_vertices, path_obj in self.paths.items():  # Iterate through all paths
                if current_node_name is path_vertices[0]:  # If the path starts at the current node
                    current_port = path_obj.edge_ports[0][0]  # Pick up the first port on the path
                elif current_node_name is path_vertices[-1]:  # If the path ends at the current node
                    current_port = path_obj.edge_ports[-1][-1]  # Pick up the last port on the path

            setattr(
                model,
                f"path_flow_con1_{current_node_name}",
                en.Constraint(model.Expansion, model.Time, rule=path_flow_rule),
            )

            # Create an indicator var for when there are flows into a node
            setattr(model, current_node_obj.inflow, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

            setattr(
                model,
                f"path_flow_con2_{current_node_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_inflow_or_outflow1),
            )

            setattr(
                model,
                f"path_flow_con3_{current_node_name}",
                en.Constraint(model.Expansion, model.Time, rule=only_inflow_or_outflow2),
            )

    def draw_on_axes(self, axes, with_labels=False, labels=None, **kwargs):
        """Draws the network on a matplotlib plot

        Args:
            axes (matplotlib.axes.Axes): The (sub-)plot on which to draw the network
            with_labels (bool): Set to True to draw labels on the nodes. Defaults to False.
                Uses the node's names as the label.
            labels (dict): Optional way of supplying node labels as a dictionary of labels (strings) keyed by node.
                Default = None.
            **kwargs: Optional keyword arguments for customising the drawing of the network.
                See https://networkx.org/documentation/stable/reference/generated/networkx.drawing.nx_pylab.draw_networkx.html  # noqa: E501
                for more information.

        Examples:
            The following example shows how to draw an already created OptimisationGraph with the name `network`

            >>> import matplotlib.pyplot as plt
            >>> network_figure = plt.figure()
            >>> network_axes = network_figure.add_subplot()
            >>> network.draw_on_axes(axes=network_axes, with_labels=True)
            >>> plt.show()
        """
        nx.draw_networkx(self.convert_to_nx(), ax=axes, with_labels=with_labels, labels=labels, **kwargs)

    def to_cytoscape_json(self) -> str:
        """Converts the optimisation graph to json that can be read by cytoscape (https://js.cytoscape.org/)"""
        import json

        G = self.convert_to_nx()
        nodes = []
        for node in G.nodes():
            nodes.append({"data": {"id": node}})
        for n1, n2 in G.edges():
            nodes.append({"data": {"id": f"{n1}_{n2}", "source": n1, "target": n2}})

        return json.dumps(nodes)

    def print_port_names(self):
        """Prints port name-uid pairs, useful for debugging infeasible optimisation"""
        for n in self.node_obj.values():
            for pn, p in n.ports.items():
                print(pn, ", ", p.port_name)

    def get_port_names_from_nodes(self):
        output = set()
        for n in self.node_obj.values():
            for pn, p in n.ports.items():
                output.add(p.port_name)
        return output

    def get_port_names_from_edges(self):
        output = set()
        for e in self.edge_obj.values():
            output.add(e.vertices[0].port_name)
            output.add(e.vertices[1].port_name)
        return output

    def verify_graph(self):
        """Checks that the graph is connected (all nodes have at least one edge), and warns if there
        are unconnected ports"""
        validate(nx.is_connected(self.convert_to_nx()) is True, "Graph is not connected.")
        # Check graph for ports that are not connected
        ports_on_edges = self.get_port_names_from_nodes()
        ports_on_nodes = self.get_port_names_from_edges()
        diff = ports_on_edges - ports_on_nodes  # check overlap
        if len(diff) != 0:
            warnings.warn(
                f"Ports {diff} are defined on nodes but are not part of an edge. "
                "This may cause erroneous optimisation results."
            )

    def split_graph_on_edge(self, node1: str, node2: str):
        """Splits a graph between node1 and node 2, and returns two echo optimisation graphs.
        The ports on the split edge are kept in the two new graphs."""
        system = self.convert_to_nx()
        # Find the edge that connects these nodes
        if system.has_edge(node1, node2):
            system.remove_edge(node1, node2)
        else:
            raise ValueError('No edge exists between nodes "{}" and "{}"'.format(node1, node2))

        # Get a list of the two sets of nodes
        y = nx.connected_components(system)
        g1_nodes = next(y)
        g2_nodes = next(y)

        g1_subgraph = system.subgraph(g1_nodes)
        g2_subgraph = system.subgraph(g2_nodes)

        def create_new_graph(nodes: list, edges: list):
            """Creates a new graph from a list of node names and edge names"""
            new_graph = OptimisationGraph()
            for n in nodes:
                new_graph.add_node_obj(self.node_obj[n])
            for ed in edges:
                if self.edge_obj.get(ed) is not None:
                    new_graph.add_edge_obj(self.edge_obj[ed])
                else:
                    new_graph.add_edge_obj(self.edge_obj[(ed[1], ed[0])])

            return new_graph

        G1 = create_new_graph(g1_subgraph.nodes, g1_subgraph.edges)
        G2 = create_new_graph(g2_subgraph.nodes, g2_subgraph.edges)

        return G1, G2

    def update_node(self, node_name: str, **kwargs):
        # Update the edge associated with the EV
        found_edge = None
        for edge in self.edge_list():
            if node_name in edge:
                found_edge = edge
                edge_node_1_name = self.lookup_node_names_from_port(self.get_edge(edge).vertices[0])
                edge_node_2_name = self.lookup_node_names_from_port(self.get_edge(edge).vertices[1])
                edge_node_1_port_name = self.get_edge(edge).vertices[0].port_name
                edge_node_2_port_name = self.get_edge(edge).vertices[1].port_name

        if found_edge is None:
            raise ValueError(f"No edges contain node: {node_name}")

        # Inject stateful data
        # If the node has a set_stateful_attrs() function, use that function.
        # If it is not, use node.update(), create a new edge object with the updated ports and delete the old edge.
        # The creation of a new edge and the deletion of the old edge is required as pydantic creates copies of objects
        # upon data injection (under the old way of doing it), which would mean the port on the node and the port
        # defining the edge are no longer the same port, even if they share identical sets of attributes.
        if hasattr(self.get_node(node_name), "set_stateful_attrs"):
            self.get_node(node_name).set_stateful_attrs(**kwargs)
        else:
            self.get_node(node_name).update(**kwargs)

            # Get the correct port objects to build a new edge
            node1 = self.node_obj[edge_node_1_name]
            node2 = self.node_obj[edge_node_2_name]
            edge_node_1_port_dict_name = node1.get_port_name_to_port_dict_name_map()[edge_node_1_port_name]
            edge_node_2_port_dict_name = node2.get_port_name_to_port_dict_name_map()[edge_node_2_port_name]
            port1 = node1.ports[edge_node_1_port_dict_name]
            port2 = node2.ports[edge_node_2_port_dict_name]

            # Update the edge
            self.delete_edge(found_edge)
            self.connect_ports_and_create_edge(port1, port2)

    def inject_data_into_ev(
        self,
        node_name: str,
        available: Optional[Union[ArrayType, list, str]] = None,
        usage: Optional[Union[ArrayType, list, str]] = None,
        initial_state_of_charge: Optional[float] = None,
        interval_duration: Optional[int] = None,
    ):
        """Injects stateful data into an EV node in an OptimisationGraph.

        This is a convenience method to be used for networks constructed by MESNetwork.to_echo(). It will update
        all data in the relevant node and edges through re-initialisation of nodes, and delete and recreated of
        the edge.

        Args:
            node_name: The node_name of the EV to have stateful data injected.
            available: The avability data of the EV to be injected.
            usage: The usage data of the EV to be injected.
            initial_state_of_charge: The initial state of charge of the EV to be injected.
            interval_duration: The interval duration of the EV to be injected.

        Returns:
            None

        """
        node_attributes = {
            "available": available,
            "usage": usage,
            "initial_state_of_charge": initial_state_of_charge,
            "interval_duration": interval_duration,
        }
        self.update_node(node_name=node_name, **node_attributes)
