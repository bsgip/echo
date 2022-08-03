import enum
import uuid
import pickle
import uuid
import warnings
from typing import Optional, Union, List, Any, Iterable, Tuple

import matplotlib.pyplot as plt
import networkx as nx
from networkx import Graph
from pydantic import BaseModel as PydanticBaseModel, PositiveFloat, NonNegativeFloat
from pydantic import validator, root_validator, confloat

from echo.configuration import *
from echo.constants import *
from echo.utils import *

DataFrame = TypeVar('pandas.core.frame.DataFrame')

"""

    Base models

"""


class BaseModel(PydanticBaseModel):
    """ Create a modified basemodel with the config we want."""

    class Config:
        validate_assignment = True  # Set to true so that we re-validate when we update a model field
        extra = 'ignore'  # If 'allow', extra attributes can be added after instantiation, if 'ignore', extra attributes are ignored, if 'forbid', extra attributes are not allowed.


class ConfigurationError(Exception):
    pass


class Port(BaseModel):
    # Pydantic attribute declaration follows this format:
    # attribute_name: type = default_value

    units: Units = Units.NA  # Used to ensure that common units are being optimised over at points of interconnection
    initial_value: dict = 0.
    initial_value_ref: Optional[str]  # string ref to df column
    opt_type: OptimisationType = OptimisationType.NA
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    port_name: Optional[str] = None
    flows: Flows = Flows.NA  # What flow directions are possible (import, export, both)
    # Used to define the nature of import / export directions and constraints
    import_constraint: FlowConstraint = FlowConstraint.NA
    import_constraint_value: Union[ArrayType, float, None] = None
    export_constraint: FlowConstraint = FlowConstraint.NA
    export_constraint_value: Union[ArrayType, float, None] = None
    active_periods: Optional[dict]
    slack: bool = False
    objective: Optional[Any] = 0  # this will eventually be a pyomo expression

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
        if self.port_name is None:  # if no name is provided, give it a default name using the uid
            self.port_name = 'port_' + str(self.uid)

    def set_flow_constraints(self, max_import, max_export, slack=False):
        """ Sets the values of port flow constraints.

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

    def process_initial_value(self, initial_val, expansion_periods: int=1, time_periods: int=None ):
        if isinstance(initial_val, dict):
            self.add_initial_value(initial_val)
        elif isinstance(initial_val, str):
            self.initial_value_ref = initial_val
        elif hasattr(initial_val, '__iter__'):
            self.add_initial_value_from_array(initial_val, expansion_periods, time_periods)

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

    def initialise_port(self, model, profile):
        """ Creates pyomo vars, params, and constraints for the port. """

        time_periods = len(model.Time)
        exp_periods = len(model.Expansion)

        domain = en.Reals
        if self.flows is Flows.Export:
            domain = en.NonPositiveReals
        elif self.flows is Flows.Import:
            domain = en.NonNegativeReals

        if self.initial_value_ref is not None:
            initial_val = to_initial_values(profile, self.initial_value_ref, time_periods, exp_periods)
        else:
            initial_val = self.initial_value
        setattr(model, self.port_name, en.Var(model.Expansion, model.Time, initialize=initial_val, domain=domain))

        if self.opt_type is OptimisationType.Parameter:
            getattr(model, self.port_name).fix()  # Fix the variable - equivalent to setting it as an 'en.Param'

        # Import/export capacity constraint with slack rules
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

        if self.import_constraint is FlowConstraint.Fixed:  # only apply import/export constraints to variables
            con_name = 'import_con_' + self.port_name
            # Generate an array of constraints (ie indexed by time and expansion period)
            import_constraint_dict = generate_array_constraint(self.import_constraint_value, time_periods, exp_periods)
            setattr(model, self.import_con_val,
                    en.Param(model.Expansion, model.Time, initialize=import_constraint_dict,
                             domain=en.NonNegativeReals))

            if self.slack is True:
                setattr(model, self.import_slack,
                        en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_rule_slack))
                con_name = 'import_con_max_' + self.port_name
                setattr(model, self.import_slack_max,
                        en.Var(initialize=0, domain=en.NonPositiveReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=import_cap_slack_max_rule))

            else:
                set_var_bounds_from_dict(getattr(model, self.port_name), ub=import_constraint_dict, lb=None)

        if self.export_constraint is FlowConstraint.Fixed:  # only apply these constraints to variables
            con_name = 'export_con_' + self.port_name
            export_constraint_dict = generate_array_constraint(self.export_constraint_value, time_periods, exp_periods)
            setattr(model, self.export_con_val,
                    en.Param(model.Expansion, model.Time, initialize=export_constraint_dict,
                             domain=en.NonPositiveReals))

            if self.slack is True:
                setattr(model, self.export_slack,
                        en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_rule_slack))
                con_name = 'export_con_max_' + self.port_name
                setattr(model, self.export_slack_max,
                        en.Var(initialize=0, domain=en.NonNegativeReals))
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=export_cap_slack_max_rule))

            else:
                set_var_bounds_from_dict(getattr(model, self.port_name), ub=None, lb=export_constraint_dict)

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
        """ Applies a mixed integer constraint that splits a port var into positive and negative components """
        if hasattr(model, self.pos) is False:
            setattr(model, self.pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            setattr(model, self.neg, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonPositiveReals))
            setattr(model, self.is_pos, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

            con_rule = self.factory_pos_neg_flows(self.port_name, self.pos, self.neg)
            con_name = positive_variable_component + negative_variable_component + self.port_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=con_rule))

            def only_pos_or_neg_one(model, p, t):
                return getattr(model, self.pos)[p, t] <= getattr(model, self.is_pos)[p, t] * model.bigM

            setattr(model, f"pos_neg_con1_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_one))

            def only_pos_or_neg_two(model, p, t):
                return getattr(model, self.neg)[p, t] >= (getattr(model, self.is_pos)[p, t] - 1) * model.bigM

            setattr(model, f"pos_neg_con2_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=only_pos_or_neg_two))

    @staticmethod
    def factory_pos_neg_flows(var_name, pos_name, neg_name):
        def constraint(model, expansion_interval, time_interval):
            return getattr(model, var_name)[expansion_interval, time_interval] == \
                   (getattr(model, pos_name)[expansion_interval, time_interval] +
                    getattr(model, neg_name)[expansion_interval, time_interval])

        return constraint

    def add_initial_value(self, initial_value: dict):
        """ Adds initial port value which will be used to initialise the pyomo var/param
        Args:
            initial_value: dict of initial values
        """
        self.initial_value = initial_value

    def add_initial_value_from_array(self, array, expansion_periods: int = 1, time_periods: int = None):
        """ Adds initial port value which is used to initialise the pyomo var/param
        Args:
            array: array, list of initial values. Should have length = time_periods, or length = time_periods*expansion_periods
            time_periods: int, optional number of time periods. If=None, assume that time_periods = len(array)
            expansion_periods: number of expansion periods
        """

        x = ArrayWrap(array)
        if time_periods is None:
            time_periods = len(array)
        x.set_periods(time_periods=time_periods, expansion_periods=expansion_periods)
        vals = x.dict()
        self.add_initial_value(vals)

    def add_active_periods_from_array(self, array, expansion_periods: int = 1, time_periods: int = None):
        """ Adds port active periods
        Args:
            array: array, list of active periods as bool values
            expansion_periods: number of expansion periods (int)
        """
        x = ArrayWrap(array)
        if time_periods is None:
            time_periods = len(array)
        x.set_periods(time_periods=time_periods, expansion_periods=expansion_periods)
        vals = x.dict()
        self.active_periods = vals

    def add_objective(self, model: en.ConcreteModel):
        """ Populates the port attribute 'objectives' with any pyomo expressions that are needed
        Args:
            model: pyomo concrete model
        """
        total = 0
        if self.slack is True:
            if hasattr(model, self.import_slack) is True:
                total += -1 * getattr(model, self.import_slack_max) * model.bigM
                total += -1 * sum(getattr(model, self.import_slack)[p, t] for p in model.Expansion for t in
                                  model.Time) * model.bigM * 0.1
            if hasattr(model, self.export_slack) is True:
                total += getattr(model, self.export_slack_max) * model.bigM
                total += sum(getattr(model, self.export_slack)[p, t] for p in model.Expansion for t in
                             model.Time) * model.bigM * 0.1

        self.objective += total

    def get_port_objective_value(self):
        return en.value(self.objective)


class Transform(BaseModel):
    """ An object for carrying a generic linear node transformation. """
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID
    transform_name: Optional[str] = None
    lhs: list = []
    rhs = 0

    def __init__(self, **data):
        super().__init__(**data)
        if self.transform_name is None:
            self.transform_name = 'transform_' + str(self.uid)

    def add_lhs_term(self, var: Port, rule: TransformRule, weight: ArrayWrap):
        """ Adds a left-hand side (LHS) term to the transform """
        if isinstance(weight, ArrayWrap) is False:
            weight = ArrayWrap(weight)
        term = {'var': var, 'rule': rule, 'weight': weight}
        self.lhs.append(term)

    def initialise_transform(self, model):
        # Check if we need to create pos/neg components, and initialise the weights
        for i in range(len(self.lhs)):
            self.lhs[i]['weight'].set_periods(model.Expansion, model.Time)
            if self.lhs[i]['rule'] is not TransformRule.Both:
                var = self.lhs[i]['var']
                var.constrain_pos_neg(model)


class Node(BaseModel):
    """
    Nodes are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented.
    """
    node_name: Optional[str]
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID
    ports: dict = {}
    node_rule: NodeRule = NodeRule.NA
    transformations: dict = {}
    objective: Optional[Any] = 0  # For adding any node objectives

    @property
    def inflow(self):
        return f"inflow_{self.node_name}"

    def __init__(self, **data):
        super().__init__(**data)
        if self.node_name is None:
            self.node_name = 'node_' + str(self.uid)

    def add_port(self, name: str, port: Port):
        if self.ports.get(name) is None:
            self.ports[name] = port
        else:
            print(f'Port with name {name} is already defined on node {self.node_name}')

    def get_port(self, port_name: str):
        if self.ports.get(port_name) is not None:
            return self.ports.get(port_name)

    def add_flex_port(self, name, unit=Units.NA):
        """ Adds named port of specified type to node.
        Args:
            name: port name as string
            unit: Unit
        """
        self.ports[name] = FlexPort()
        if unit is not Units.NA:
            self.ports[name].units = unit

    def add_electrical_port(self, port_name: str):
        self.add_flex_port(port_name, unit=Units.KW)

    def add_electrical_ports_from_list(self, name_list: list):
        for name in name_list:
            self.add_electrical_port(port_name=name)

    def add_flex_ports_from_list(self, name_list: list, unit=Units.NA):
        for name in name_list:
            self.add_flex_port(name, unit)

    def add_transformation(self, transformation_obj: Transform):
        """ Adds a transformation object to a node.
        Args:
            transformation_obj: Transform
        """
        self.transformations[transformation_obj.uid] = transformation_obj
        self.node_rule = NodeRule.Transform

    def add_input_output_transformation(self, input_port: Port, output_port: Port, input_weight: float):
        t = Transform()
        t.add_lhs_term(var=output_port, rule=TransformRule.Both, weight=1)
        t.add_lhs_term(var=input_port, rule=TransformRule.Both, weight=-input_weight)
        self.add_transformation(t)

    def add_emission_transformation(self, emitting_port: Port, carbon_port: Port, emission_factor):
        """ Creates an emission transformation and adds to the node.
        Args:
            emitting_port: port object that generates emissions when exporting (when negative)
            carbon_port: port object that represents carbon flows out of the node
            emission_factor: a ratio = emissions generated/emitting unit generated (float), or an array of values
        """
        # Create appropriate transformation
        t = Transform()
        t.add_lhs_term(carbon_port, TransformRule.Neg, 1)
        t.add_lhs_term(emitting_port, TransformRule.Neg, -emission_factor)
        self.add_transformation(t)

    def verify_node(self):
        if bool(self.ports) is False:
            raise ConfigurationError('A node must have at least one port.')

        if self.node_rule is NodeRule.NA and len(self.ports) > 1:
            raise ConfigurationError('NodeRule cannot be NA if node has more than one port.')

        if self.node_rule == NodeRule.Transform:
            if not self.transformations:
                raise ConfigurationError(
                    "Node has Transform rule but Transformation object(s) has not been added to node.")

        if self.node_rule == NodeRule.Tellegen:
            assert len(self.ports) >= 2, 'A tellegen node must have at least two ports.'

    def initialise_node(self, model, profile):
        for port in self.ports.values():
            port.verify_port()
            port.initialise_port(model, profile)

    def apply_node_constraints(self, model):

        def reliability(model, p, t):  # Tellegen node rule
            a = 0
            for _, port in node_ports.items():
                a += getattr(model, port.port_name)[p, t]
            return a == 0

        def transform(model, p, t):  # Generic transformation node
            lhs = 0
            for term in current_transform.lhs:
                weight = term['weight']
                var = term['var']
                rule = term['rule']
                if rule is TransformRule.Both:
                    var = term['var'].port_name
                elif rule is TransformRule.Pos:
                    var = term['var'].pos
                elif rule is TransformRule.Neg:
                    var = term['var'].neg
                lhs += getattr(model, var)[p, t] * weight[p, t]
            return lhs == current_transform.rhs

        if self.node_rule == NodeRule.Transform:
            for _, current_transform in self.transformations.items():
                current_transform.initialise_transform(model)  # make sure that all variables have been initialised
                con_name = 'transformation_con_' + self.node_name
                setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=transform))

        if self.node_rule == NodeRule.Tellegen:
            node_ports = self.ports
            con_name = 'reliability_con_' + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=reliability))

    def add_objective(self, model):
        total = 0
        self.objective += total

    def num_ports(self):
        return len(self.ports)

    def get_node_objective_value(self):
        return en.value(self.objective)


class ExpansionNode(Node):
    """ A node with extra attributes for expansion planning."""

    install_cost: float

    @property
    def is_installed(self):
        return f"is_installed_{self.node_name}"

    @property
    def installed_when(self):
        return f"installed_when_{self.node_name}"

    @property
    def max_install(self):
        return f"is_installed_total_{self.node_name}"

    def apply_node_constraints(self, model):
        super(ExpansionNode, self).apply_node_constraints(model)
        self._apply_expansion_constraints(model)

    def _apply_expansion_constraints(self, model):
        # Create an indexed binary variable for which time period if any the node is installed
        setattr(model, self.is_installed, en.Var(model.Expansion, initialize=0, domain=en.Binary))
        # Create an integer variable for which period the asset is installed in, if installed
        setattr(model, self.installed_when, en.Var(initialize=0, domain=en.NonNegativeIntegers))
        # Create a non-indexed var to track whether we ever install the node
        setattr(model, self.max_install, en.Var(initialize=0, domain=en.Binary))

        # Set constraints on integer variable so that it correctly tracks the expansion_planning period in which we install
        def integer_var_con1(model, p):
            return getattr(model, self.installed_when) >= p - model.bigM * getattr(model, self.is_installed)[p] + 1

        def integer_var_con2(model, p):
            return getattr(model, self.installed_when) <= p + model.bigM * (1 - getattr(model, self.is_installed)[p])

        setattr(model, 'install_int_con1_' + self.node_name, en.Constraint(model.Expansion, rule=integer_var_con1))
        setattr(model, 'install_int_con2_' + self.node_name, en.Constraint(model.Expansion, rule=integer_var_con2))

        # Constraints for max_is_installed
        def rule3(model, p):
            return getattr(model, self.is_installed)[p] <= getattr(model, self.max_install)

        setattr(model, 'max_is_installed_con_' + self.node_name, en.Constraint(model.Expansion, rule=rule3))

        # Constraints to force all ports on node to be = 0 before the node is installed
        def install_before_active1(model, p, t):
            prev = 0
            for i in range(p + 1):
                prev += getattr(model, self.is_installed)[i]
            return getattr(model, port_obj.port_name)[p, t] <= model.bigM * prev

        def install_before_active2(model, p, t):
            prev = 0
            for i in range(p + 1):
                prev += getattr(model, self.is_installed)[i]
            return getattr(model, port_obj.port_name)[p, t] >= - model.bigM * prev

        for port_name, port_obj in self.ports.items():
            setattr(model, 'install_b4_run1_' + port_name,
                    en.Constraint(model.Expansion, model.Time, rule=install_before_active1))
            setattr(model, 'install_b4_run2_' + port_name,
                    en.Constraint(model.Expansion, model.Time, rule=install_before_active2))

    def add_objective(self, model):
        super(ExpansionNode, self).add_objective(model)
        total = 0
        total += self.install_cost * getattr(model, self.max_install)
        self.objective += total

class RetirementNode(Node):
    """ Node for retirement planning."""

    replace_cost: float
    nominal_lifetime: int  # node nominal lifetime in number of expansion_planning period units
    initial_life_left: int  # node life left at start of optimisation

    @property
    def replace(self):
        return f"is_replaced_{self.node_name}"

    @property
    def retire(self):
        return f"is_retired_{self.node_name}"

    @property
    def lifetime_remaining(self):
        return f"lifetime_remaining_{self.node_name}"

    def apply_node_constraints(self, model):
        super(RetirementNode, self).apply_node_constraints(model)
        self._apply_retirement_constraints(model)

    def _apply_retirement_constraints(self, model):
        # Create retirement planning variables
        setattr(model, self.retire, en.Var(model.Expansion, initialize=0, domain=en.Binary))
        setattr(model, self.replace, en.Var(model.Expansion, initialize=0, domain=en.Binary))
        setattr(model, self.lifetime_remaining, en.Var(model.Expansion, initialize=self.initial_life_left,
                                                       bounds=(0, self.nominal_lifetime), domain=en.NonNegativeReals))

        def remaining_life_rule(model, p):
            if p == 0:
                return getattr(model, self.lifetime_remaining)[p] == self.initial_life_left
            else:
                new_lifetime = getattr(model, self.replace)[p] * (self.nominal_lifetime + 1)  # Need +1 because we -1 each time period automatically
                retired = getattr(model, self.retire)[p]
                return getattr(model, self.lifetime_remaining)[p] == \
                       getattr(model, self.lifetime_remaining)[p-1] + new_lifetime + retired - 1

        setattr(model, 'life_left_' + self.node_name, en.Constraint(model.Expansion, rule=remaining_life_rule))

        def permanent_retirement_rule(model, p):
            # Forces retirement var to be increasing (ie can only change from 0 to 1, not vice versa)
            if p == 0:
                return en.Constraint.Skip
            else:
                return getattr(model, self.retire)[p] >= getattr(model, self.retire)[p-1]

        setattr(model, 'retirement_con_'+self.node_name, en.Constraint(model.Expansion, rule=permanent_retirement_rule))

        #todo alternative constraint below, forces retirement or replacement at end of lifetime

        # # Big M Constraint: force either retirement or replacement at end of lifetime
        # def eol_rule1(model, p):
        #     replace_or_retire = getattr(model, self.replace)[p] + getattr(model, self.retire)[p]
        #     return getattr(model, self.lifetime_remaining)[p] <= (1 - replace_or_retire) * model.bigM
        #
        # def eol_rule2(model, p):
        #     replace_or_retire = getattr(model, self.replace)[p] + getattr(model, self.retire)[p]
        #     return getattr(model, self.lifetime_remaining)[p] * model.bigM >= (1 - replace_or_retire)
        #
        # setattr(model, 'eol_1_' + self.node_name, en.Constraint(model.Expansion, rule=eol_rule1))
        # setattr(model, 'eol_2_' + self.node_name, en.Constraint(model.Expansion, rule=eol_rule2))

        # Force ports on node to be 0 if retired, using a pair of big M constraints
        for port_name, port_obj in self.ports.items():
            def retire_rule1(model, p, t):
                return getattr(model, port_obj.port_name)[p, t] <= (1 - getattr(model, self.retire)[p]) * model.bigM

            def retire_rule2(model, p, t):
                return getattr(model, port_obj.port_name)[p, t] >= -(1 - getattr(model, self.retire)[p]) * model.bigM

            setattr(model, 'retire_1_'+port_name, en.Constraint(model.Expansion, model.Time, rule=retire_rule1))
            setattr(model, 'retire_2_' + port_name, en.Constraint(model.Expansion, model.Time, rule=retire_rule2))

    def add_objective(self, model):
        super(RetirementNode, self).add_objective(model)
        total = 0
        total += self.replace_cost * sum(getattr(model, self.replace)[p] for p in model.Expansion)
        self.objective += total

class Edge(BaseModel):
    """
    Edges are used to connect nodes. For an edge (x, y) where x and y are nodes,
    the edge value is equal to the flow from x->y plus the flow from y->x.
    """
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID
    edge_name: Optional[str] = None
    vertices: tuple
    nodes: Optional[Tuple[str, str]]  # tuple of node names - todo make this required
    tariff: Optional[Union[list, None]]

    def __int__(self, **data):
        super().__init__(**data)
        if self.edge_name is None:
            self.edge_name = 'edge_' + str(self.uid)

    def add_vertices(self, obj1, obj2):
        """ Adds edge vertices (which are ports on nodes)
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
        """ Applies edge constraint: port1 = -1 *port2
        Args:
            model: pyomo concrete model
        """

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        def edge_constraint_rule(model, p, t):
            return getattr(model, port1.port_name)[p, t] + getattr(model, port2.port_name)[p, t] == 0

        con_name = 'edge_con_' + port1.port_name + '_' + port2.port_name
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


class OptimisationGraph(BaseModel):
    node_obj: dict = {}
    edge_obj: dict = {}
    paths: dict = {}

    def pickle(self):
        return pickle.dumps(self)

    def node_name_list(self):
        return list(self.node_obj.keys())

    def edge_list(self):
        return list(self.edge_obj.keys())

    def convert_to_nx(self) -> nx.Graph:
        """ Converts the OptimisationGraph to a networkx graph, where nx nodes are echo node names and nx edges are nx node pairs"""
        g = nx.Graph()
        g.add_nodes_from(self.node_obj.keys())
        g.add_edges_from(self.edge_obj.keys())
        return g

    def _add_single_node(self, node_obj: Node):
        assert node_obj.node_name not in self.node_obj, 'Node \'{}\' already defined'.format(node_obj.node_name)
        self.node_obj[node_obj.node_name] = node_obj

    def delete_node(self, node_name: str):
        if self.get_node(node_name) is not None:
            del self.node_obj[node_name]
        else:
            print(f'Node {node_name} not found.')

    def delete_edge(self, edge_nodes: Tuple[str, str]):
        if self.get_edge(edge_nodes) is not None:
            del self.edge_obj[edge_nodes]
        else:
            print(f'Edge {edge_nodes} not found.')

    def add_node_obj(self, node: Union[list, Node]):
        """ Adds either a single node or list of nodes to graph"""
        # todo phase out this method
        if type(node) is list:
            for n in node:
                self._add_single_node(n)
        else:
            self._add_single_node(node)

    def add_nodes_from(self, nodes: List[Node]):
        """ Adds a list of nodes to the graph."""
        for n in nodes:
            self._add_single_node(n)

    def add_node(self, node: Node):
        """ Adds a single node to the graph."""
        self._add_single_node(node)

    def get_node(self, node_name: str):
        """ Returns node object given node name"""
        return self.node_obj.get(node_name)

    def get_edge(self, nodes: Tuple[str, str], warn: bool = False):
        """ Retrieves the edge that connects a tuple of nodes, if an edge exists."""
        if self.edge_obj.get(nodes) is not None:
            return self.edge_obj.get(nodes)
        elif self.edge_obj.get(reversed(nodes)) is not None:
            return self.edge_obj.get(reversed(nodes))
        elif warn:
            print('Edge between {} and {} does not exist'.format(nodes[0], nodes[1]))

    def _add_single_edge(self, edge_obj: Edge):
        port1 = edge_obj.vertices[0]
        port2 = edge_obj.vertices[1]
        assert port1.units == port2.units, 'Ports on edge must have matching units.'
        if edge_obj.nodes is None:
            # Want to avoid doing this lookup - very slow
            node1_name = self.lookup_node_names_from_port(port1)
            node2_name = self.lookup_node_names_from_port(port2)
        else:
            node1_name = edge_obj.nodes[0]
            node2_name = edge_obj.nodes[1]
        # Need to check whether an edge already exists between these two nodes
        if self.get_edge(nodes=(node1_name, node2_name)) is not None:
            raise ValueError('An edge between these nodes already exists')

        self.edge_obj[(node1_name, node2_name)] = edge_obj

    def add_edge_obj(self, edge: Union[list, Edge]):
        # todo phase out this method
        if type(edge) is list:
            for e in edge:
                self._add_single_edge(e)
        else:
            self._add_single_edge(edge)

    def add_edges_from(self, edge: List[Edge]):
        for e in edge:
            self._add_single_edge(e)

    def add_edge(self, edge: Edge):
        self._add_single_edge(edge)

    def connect_ports_and_create_edge(self, port1: Port, port2: Port, edge_name: str = None, nodes: Tuple[str] = None,
                                      warn: bool = False):
        """ Creates an edge between port1 and port2 and adds it to the graph"""
        if nodes is None and warn is True:
            print('No edge nodes defined. Defining edge nodes here speeds up constructing of echo graph.')
        e = Edge(vertices=(port1, port2), edge_name=edge_name, nodes=nodes)
        self.add_edge(e)

    def lookup_node_names_from_port(self, port: Port) -> str:
        """ Returns node name of the node that a specified port belongs to, if the port belongs to a node."""
        for node_name, node in self.node_obj.items():
            for _, p in node.ports.items():
                if port == p:
                    return node_name
        raise ConfigurationError(f'Port {port.port_name} is not part of any node, or node has not been added to graph.')

    def get_ports_on_edge_from_nodes(self, node1: str, node2: str) -> (Port, Port):
        """ Returns the ports that are on the edge from node1 to node2. """
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
        assert bool(self.paths) is True, 'Create paths before retrieving sources and sinks.'
        sources_or_sinks = set()
        for _, path in self.paths.items():
            sources_or_sinks.add(path.vertices[0])
            sources_or_sinks.add(path.vertices[-1])
        return sources_or_sinks

    def get_path(self, path_vertices: List[str]):
        """ Looks up a path using a list of path vertices (nodes, or node names)."""
        if hasattr(path_vertices[0], 'node_name'):
            name_key = [node.node_name for node in path_vertices]
            return self.paths[tuple(name_key)]
        else:
            if self.paths.get(tuple(path_vertices)) is not None:
                return self.paths[tuple(path_vertices)]
            else:
                raise ValueError(f'No path with vertices {path_vertices} is defined.')

    def verify_paths(self):
        """ Verifies that our paths meet the assumptions required to correctly do flow tracing."""
        all_nodes = self.get_sources_and_sinks()
        for node in all_nodes:
            for path in self.paths.values():
                if node in path.vertices[1:-1]:
                    # if the source/sink node appears in the middle of another path, the optimiser will fail
                    # A node can't be both a tellegen node and a source/sink node
                    raise ConfigurationError('Source/sink node is being treated as a tellegen node.')

    def create_path_objects(self, sources: List[str], sinks: List[str], path_unit: Units = Units.KW,
                            regularise: bool = False):
        """ Creates path objects according to source/sink lists provided."""
        warnings.warn(
            'Path tracing is still experimental. If you are generating paths to use path tariffs, please consider whether you can convert these tariffs to point/port tariffs.')
        all_paths = {}
        graph = self.convert_to_nx()
        if hasattr(sources[0], 'node_name'):
            sources = [i.node_name for i in sources]
        if hasattr(sinks[0], 'node_name'):
            sinks = [i.node_name for i in sinks]

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

        intersec = source_sink_set.intersection(tellegen_node_set)  # check overlap of tellegen and source/sink nodes
        assert len(intersec) == 0, f"Nodes '{intersec}' are being treated as both tellegen and source/sink."
        self.paths = all_paths

    def _create_path_object(self, vertex_list: list, edge_list: list, regularise: bool, path_unit: int):
        """ Creates a path object """
        p = Path(vertices=vertex_list, regularise=regularise, units=path_unit)  # Create path object
        for edge in edge_list:
            edge_ports = self.get_ports_on_edge_from_nodes(edge[0], edge[1])
            p.edge_ports.append(edge_ports)
        return p

    def apply_path_constraints(self, model: en.ConcreteModel):
        """ Applies path tracing constraints to model """

        def path_flow_rule(model, p, t):
            a = 0
            for _, path in self.paths.items():  # Iterate through all paths in the model
                if path.vertices[0] is current_node_name:  # If the path starts at the current node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
                if path.vertices[-1] is current_node_name:  # If the path ends at the current node
                    a -= getattr(model, path.flow_value)[p, t]  # Subtract the flow value
            return a == getattr(model, current_port.port_name)[p, t] * -1  # Flows out - flows in = -1 * port

        def only_inflow_or_outflow1(model, p, t):
            a = 0
            for _, path in self.paths.items():
                if path.vertices[-1] is current_node_name:  # If the path ends at the current node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
            return a <= getattr(model, current_node_obj.inflow)[
                p, t] * model.bigM  # Incoming paths can only be non-zero if inflow=1

        def only_inflow_or_outflow2(model, p, t):
            a = 0
            for _, path in self.paths.items():
                if path.vertices[0] is current_node_name:  # If the path starts at the node
                    a += getattr(model, path.flow_value)[p, t]  # Add the flow value
            return a <= (1 - getattr(model, current_node_obj.inflow)[
                p, t]) * model.bigM  # Outgoing paths can only be non-zero if inflow=0

        sources_and_sinks = self.get_sources_and_sinks()  # returns concatenated list of all source/sink nodes
        for current_node_name in sources_and_sinks:  # Iterate through the source/sink nodes
            current_node_obj = self.node_obj[current_node_name]  # get the node obj
            for path_vertices, path_obj in self.paths.items():  # Iterate through all paths
                if current_node_name is path_vertices[0]:  # If the path starts at the current node
                    current_port = path_obj.edge_ports[0][0]  # Pick up the first port on the path
                elif current_node_name is path_vertices[-1]:  # If the path ends at the current node
                    current_port = path_obj.edge_ports[-1][-1]  # Pick up the last port on the path

            setattr(model, f"path_flow_con1_{current_node_name}",
                    en.Constraint(model.Expansion, model.Time, rule=path_flow_rule))

            # Create an indicator var for when there are flows into a node
            setattr(model, current_node_obj.inflow, en.Var(model.Expansion, model.Time, initialize=0,
                                                           domain=en.Binary))

            setattr(model, f"path_flow_con2_{current_node_name}",
                    en.Constraint(model.Expansion, model.Time, rule=only_inflow_or_outflow1))

            setattr(model, f"path_flow_con3_{current_node_name}",
                    en.Constraint(model.Expansion, model.Time, rule=only_inflow_or_outflow2))

    def draw_echo_graph(self, with_labels=False, labels=None):
        """ Draws the network with or without node labels """
        nx.draw_networkx(self.convert_to_nx(), with_labels=with_labels, labels=labels)
        plt.show()

    def print_port_names(self):
        """ Prints port name-uid pairs, useful for debugging infeasible optimisation"""
        for n in self.node_obj.values():
            for pn, p in n.ports.items():
                print(pn, ', ', p.port_name)

    def verify_graph(self):
        """ Checks that the graph is connected (all nodes have at least one edge)"""
        assert nx.is_connected(self.convert_to_nx()) is True, 'Graph is not connected.'

    def split_graph_on_edge(self, node1: str, node2: str):
        """ Splits a graph between node1 and node 2, and returns two echo optimisation graphs.
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
            """ Creates a new graph from a list of node names and edge names"""
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


class Path(BaseModel):
    """ A path is a sequence of distinct vertices (nodes). """
    edge_ports: List[tuple] = []  # list of edge name tuples
    vertices: list  # list of node names
    uid: uuid.UUID = Field(default_factory=uuid.uuid4)  # this dynamically sets a unique ID?
    path_name: Optional[str] = None
    units = Units.KW
    regularise: bool = False
    objective: Optional[Any] = 0

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

    def initialise_path(self, model):
        setattr(model, self.flow_value, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

    def add_objective(self, model):
        total = 0

        if self.regularise is True:
            total += sum(getattr(model, self.flow_value)[p, t] * getattr(model, self.flow_value)[p, t] \
                         for p in model.Expansion for t in model.Time) * 0.0000001

        self.objective += total


# def serialize_dict(d):
#     new_d = {}
#     for key, value in d.items():
#         if isinstance(key, tuple):
#             new_key = ':'.join(key)
#             new_d[new_key] = value
#         else:
#             new_d[key] = value
#     return new_d
#
# class CustomEncoder(json.JSONEncoder):
#     def _transform(self, v):
#         res = v
#         if isinstance(v, tuple):
#             res = ':'.join(v)
#         # else other variants
#         return self._encode(res)
#
#     def _encode(self, obj):
#         if isinstance(obj, dict):
#             return serialize_dict(obj)
#         if isinstance(obj, UUID):
#             return str(obj)
#         else:
#             return obj
#
#     def encode(self, obj):
#         return super(CustomEncoder, self).encode(self._encode(obj))
#
#
# def custom_dumps(values, *, default):
#     return CustomEncoder().encode(values)

"""

    Commodity agnostic ports and nodes

"""


class TellegenNode(Node):
    """A node that implements a Tellegen constraint requiring that port values sum to zero."""
    node_rule = NodeRule.Tellegen

    tellegen_unit_check = root_validator(allow_reuse=True)(node_unit_validator)


class FlexPort(Port):
    """ Flexible variable port, which can import and export without constraints."""
    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    opt_type = OptimisationType.Variable


class FlexSink(FlexPort):
    """ Flexible port, imports only"""
    flows = Flows.Import


class FlexSource(FlexPort):
    """ Flexible ports, exports only"""
    flows = Flows.Export


class FixedPort(Port):
    """ Fixed port (parameter), can either import or export."""
    opt_type = OptimisationType.Parameter
    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint


class Source(Port):
    """ A fixed source of a commodity. """
    flows = Flows.Export
    opt_type = OptimisationType.Parameter
    export_constraint = FlowConstraint.NoConstraint

    # Source should have non positive initial values
    non_pos_check = validator("initial_value", allow_reuse=True)(nonpositive_generation)

    def add_source_profile(self, source_values: dict):
        self.add_initial_value(source_values)

    def add_source_profile_from_array(self, source_values, expansion_periods=1, time_periods: int = None):
        self.add_initial_value_from_array(source_values, expansion_periods, time_periods)


class Sink(Port):
    """ A fixed sink for a commodity. """
    flows = Flows.Import
    opt_type = OptimisationType.Parameter
    import_constraint = FlowConstraint.NoConstraint

    non_neg_check = validator("initial_value", allow_reuse=True)(
        nonnegative_load)  # Sink should have non negative initial values

    def add_sink_profile(self, sink_values: dict):
        self.add_initial_value(sink_values)

    def add_sink_profile_from_array(self, sink_values, expansion_periods=1, time_periods: int = None):
        self.add_initial_value_from_array(array=sink_values, expansion_periods=expansion_periods,
                                          time_periods=time_periods)


class Demand(Sink):

    def add_demand_profile(self, demand: dict):
        self.add_initial_value(demand)

    def add_demand_profile_from_array(self, demand, expansion_periods=1, time_periods: int = None):
        self.add_initial_value_from_array(array=demand, expansion_periods=expansion_periods, time_periods=time_periods)


class ControlledLoadOrGen(FlexPort):
    """
    A controlled load or generation has a max/min power, as well as a max/min utilisation.
    Min utilisation is the ratio between the minimum energy consumed/generated, and the maxinimum energy that could be consumed/generated if the load operated at max power.
    Max utilisation is the ratio between the maximum energy consumed/generated, and the maximum energy that could be consumed/generated if the load operated at max power.
    """
    min_utilisation: Union[float, None] = None
    max_utilisation: float = None
    max_power: float = None
    min_power: float = None
    units: Units = Units.KW

    def initialise_port(self, model, profile):
        super(ControlledLoadOrGen, self).initialise_port(model, profile)

        # Set bounds using min and max power
        set_float_var_bounds(model=model, var_name=self.port_name, ub=self.max_power, lb=self.min_power)

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


class ControlledLoad(ControlledLoadOrGen):
    max_power: confloat(ge=0)
    min_power: confloat(ge=0)
    flows = Flows.Import


class ControlledGen(ControlledLoadOrGen):
    max_power: confloat(le=0)
    min_power: confloat(le=0)
    flows = Flows.Export


class OffOrConstrainedPort(FlexPort):
    """ A port that is either off (0) or on, and when it is on it is constrained between a min and max value."""
    lower_bound: float
    upper_bound: float

    bounds_check = root_validator(allow_reuse=True)(check_bound_order)  # checks that lower bound < upper bound

    @property
    def active(self):
        return 'active_' + self.port_name

    def initialise_port(self, model, profile):
        super(OffOrConstrainedPort, self).initialise_port(model, profile)
        setattr(model, self.active, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        # Apply constraints such that if active=1, the port is bounded, and if active=0, the port is 0.
        def on_off_constraint1(model, p, t):
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.active)[p, t] * self.lower_bound

        def on_off_constraint2(model, p, t):
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * self.upper_bound

        setattr(model, 'on_off1_' + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint1))
        setattr(model, 'on_off2_' + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint2))


class BoundedPort(FlexPort):
    """ A flex port with an upper and lower bound"""
    upper_bound: Union[ArrayType, float]
    lower_bound: Union[ArrayType, float]

    bound_check = root_validator(allow_reuse=True)(check_bound_order)  # check lower bound < upper bound

    def initialise_port(self, model, profile):
        super(BoundedPort, self).initialise_port(model, profile)
        # Set bounds on our port variable
        ub_dict = generate_array_constraint(self.upper_bound, time_periods=len(model.Time), expansion_periods=1)
        lb_dict = generate_array_constraint(self.lower_bound, time_periods=len(model.Time), expansion_periods=1)
        set_var_bounds_from_dict(getattr(model, self.port_name), ub=ub_dict, lb=lb_dict)


class BoundedLoad(BoundedPort):
    """ A port where the load has to be within a max and min value which is specified at each timestep."""
    import_constraint = FlowConstraint.NoConstraint

    # Do additional validation to make sure both bounds are >= 0
    upper_bound_check = validator("upper_bound", allow_reuse=True)(nonnegative_costs)
    lower_bound_check = validator("lower_bound", allow_reuse=True)(nonnegative_costs)

    def initialise_port(self, model, profile):
        super(BoundedLoad, self).initialise_port(model, profile)


class Storage(Port):
    """ Same as old storage but without all the EV attributes"""
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
    storage_capacity_cost: Optional[PositiveFloat]
    regularise: bool = False

    dod_check = root_validator(allow_reuse=True)(dod_checks)

    @property
    def soc_value(self):
        return 'storage_soc_' + self.port_name

    @property
    def optimised_capacity(self):
        return 'optimised_storage_capacity_' + self.port_name

    @property
    def soc_constraint(self):
        return 'soc_cons_' + self.port_name

    def __init__(self, **data):
        super().__init__(**data)
        self.import_constraint_value = self.charging_power_limit
        self.export_constraint_value = self.discharging_power_limit

    def initialise_port(self, model, profile):
        super(Storage, self).initialise_port(model, profile)
        self.create_storage_variables(model)
        self.apply_soc_constraints(model)

    def create_storage_variables(self, model):
        # Create soc variable and bound it
        setattr(model, self.soc_value, en.Var(model.Expansion, model.Time, initialize=0,
                                              bounds=(self.min_soc, self.max_capacity)))
        # Apply charging constraints as bounds on port_name variable
        set_float_var_bounds(model, self.port_name, ub=self.charging_power_limit, lb=self.discharging_power_limit)

        if self.fixed_storage_capacity is False:
            setattr(model, self.optimised_capacity, en.Var(initialize=0, domain=en.NonNegativeReals))

            def cap_limit(model, p, t):  # Ensure SOC is within max capacity
                return getattr(model, self.soc_value)[p, t] <= getattr(model, self.optimised_capacity)

            setattr(model, f"cap_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=cap_limit))
        else:
            setattr(model, self.optimised_capacity, en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

    def apply_soc_constraints(self, model):
        # Extract some variables to make constraints easier to write
        max_t = len(model.Time) - 1  # maximum time interval t
        kw_to_kWh = model.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def SOC_rule(model, p, t):
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + pos[p, t] * kw_to_kWh * self.charging_efficiency + \
                       neg[p, t] * kw_to_kWh / self.discharging_efficiency
            elif t == 0:
                return soc[p, t] == soc[p - 1, max_t] + pos[p, t] * kw_to_kWh * self.charging_efficiency + \
                       neg[p, t] * kw_to_kWh / self.discharging_efficiency
            else:
                return soc[p, t] == soc[p, t - 1] + pos[p, t] * kw_to_kWh * self.charging_efficiency + \
                       neg[p, t] * kw_to_kWh / self.discharging_efficiency

        def SOC_rule_perfect_efficiency(model, p, t):
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kWh
            elif t == 0:
                return soc[p, t] == soc[p - 1, max_t] + power[p, t] * kw_to_kWh
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kWh

        if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
            setattr(model, self.soc_constraint,
                    en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency))
        else:
            self.constrain_pos_neg(model)
            pos = getattr(model, self.pos)  # get pos variable for writing constraints
            neg = getattr(model, self.neg)  # get neg variable for writing constraints
            setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=SOC_rule))

    def add_objective(self, model):
        super(Storage, self).add_objective(model)
        total = 0

        # To get unique solution
        if self.regularise is True:
            total += sum(
                getattr(model, self.pos)[p, t] * getattr(model, self.pos)[p, t] + \
                getattr(model, self.neg)[p, t] * getattr(model, self.neg)[p, t]
                for p in model.Expansion for t in model.Time) * 0.0000001

        if self.storage_capacity_cost is not None:
            total += getattr(model, self.optimised_capacity) * self.storage_capacity_cost

        self.objective += total


class MobileStorage(Storage):
    """ New Storage + EV attributes"""
    # next variable is for allowing soc to go below min so as to avoid optimisation failing if there infeasible ev trips
    enable_trip_slack: bool = False
    # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
    # soc_conserv: Union[ArrayType,list,float, None, dict] = None
    soc_conserv: Union[ArrayWrap, None] = None
    soc_conserv_cost: Union[float, None] = None
    # soc_conserve: scalarOrArray
    available: Union[ArrayType, list, None] = None

    @property
    def cons_slack(self):
        return 'con_slack' + self.port_name

    @property
    def trip_slack(self):
        return 'trip_slack_' + self.port_name

    @root_validator
    def check_soc_conserv_has_cost(cls, values):
        soc_conserv = values.get('soc_conserv')
        soc_conserv_cost = values.get('soc_conserv_cost')
        available = values.get('available')
        if soc_conserv is not None:
            assert soc_conserv_cost is not None, 'soc_conserv requires soc_conserv_cost'
            assert available is not None, 'soc_conserve requires available'
        return values

    def initialise_port(self, model, profile):
        super(Storage, self).initialise_port(model, profile)
        self.create_storage_variables(model)
        self.apply_modified_soc_constraints(model)
        self.apply_conserv_soc_constraints(model)

    def apply_conserv_soc_constraints(self, model):

        def soc_conservative_rule(model, p, t):  # a rule for enforcing conservativness while plugged in
            if self.available[t]:
                return getattr(model, self.soc_value)[p, t] + getattr(model, self.cons_slack)[
                    p, t] - self.soc_conserv[p, t] >= - model.bigM * (getattr(model, self.is_pos)[p, t])
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            self.soc_conserv.set_periods(len(model.Expansion), len(model.Time))
            # self.soc_conserv = generate_array_constraint(self.soc_conserv, len(model.Time), len(model.Expansion))
            setattr(model, self.cons_slack,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))
            if not hasattr(model, self.is_pos):
                self.constrain_pos_neg(model)
            setattr(model, f"cons_soc_{self.port_name}",
                    en.Constraint(model.Expansion, model.Time, rule=soc_conservative_rule))

    def apply_modified_soc_constraints(self, model):
        # Get some variables to make constraints easier to write
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kWh = model.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def SOC_rule_slack(model, p, t):
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + pos[p, t] * kw_to_kWh * self.charging_efficiency + \
                       neg[p, t] * kw_to_kWh / self.discharging_efficiency + slack[p, t]
            elif t == 0:
                return soc[p, t] == soc[p - 1, max_t] + pos[p, t] * kw_to_kWh * self.charging_efficiency + \
                       neg[p, t] * kw_to_kWh / self.discharging_efficiency + slack[p, t]
            else:
                return soc[p, t] == soc[p, t - 1] + pos[p, t] * kw_to_kWh * self.charging_efficiency + \
                       neg[p, t] * kw_to_kWh / self.discharging_efficiency + slack[p, t]

        def SOC_rule_perfect_efficiency_slack(model, p, t):
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kWh + slack[p, t]
            elif t == 0:
                return soc[p, t] == soc[p, t - 1] + power[p - 1, max_t] * kw_to_kWh + slack[p, t]
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kWh + slack[p, t]

        if self.enable_trip_slack is True:
            # Create a slack variable
            setattr(model, self.trip_slack,
                    en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals))

            slack = getattr(model, self.trip_slack)  # get slack variable for writing constraints
            # Apply the modified soc constraint, which will overwrite the previously created one
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(model, self.soc_constraint,
                        en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency_slack))
            else:
                self.constrain_pos_neg(model)
                pos = getattr(model, self.pos)  # get pos variable for writing constraints
                neg = getattr(model, self.neg)  # get neg variable for writing constraints
                setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=SOC_rule_slack))

    def add_objective(self, model):
        super(MobileStorage, self).add_objective(model)
        total = 0

        if self.enable_trip_slack:
            total += sum(getattr(model, self.trip_slack)[p, t] for p in model.Expansion for t in
                         model.Time) * model.bigM * 20  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            total += sum(getattr(model, self.cons_slack)[p, t] for p in model.Expansion for t in
                         model.Time) * self.soc_conserv_cost

        self.objective += total


"""

    Electrical ports and nodes

"""


class ElectricalDemand(Demand):
    """ Fixed electrical demand."""
    units = Units.KW


class ElectricalGeneration(Source):
    """ Electrical generation which can be fixed (non-curtailable) or variable (curtailable) """
    units = Units.KW
    curtailable: bool = False

    def add_generation_profile(self, generation: dict):
        self.add_initial_value(generation)

    def add_generation_profile_from_array(self, generation: ArrayType, expansion_periods=1, time_periods: int = None):
        self.add_initial_value_from_array(generation, expansion_periods=expansion_periods, time_periods=time_periods)

    def initialise_port(self, model, profile):
        super(ElectricalGeneration, self).initialise_port(model, profile)
        if self.curtailable is False:
            getattr(model, self.port_name).fix()  # Equivalent to setting a variable to be a parameter after creation
        else:
            # Constrain solar gen to be within initial value (max value)
            set_var_bounds_from_dict(getattr(model, self.port_name), lb=self.initial_value, ub=None)


class ElectricalStorage(Storage):
    units = Units.KW


class MobileElectricalStorage(MobileStorage):
    units = Units.KW


class EV(Node):
    charge_mode: str = None
    available: Union[ArrayType, list, str]
    usage: Union[ArrayType, list, str]
    connection_port_name: str = 'cp'
    tod_charging: Union[ArrayType, list, str, None] = None
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
    trip_slack: bool = False  # todo call this 'enable_trip_slack' so we can give it straight to port
    # next three variables are for having a 'conservative' ev user lower bound on the soc while it is plugged in
    soc_conserv: Union[ArrayWrap, None] = None
    soc_conserv_cost: Union[float, None] = None

    V0G_delta: Optional[Union[ArrayType, list]]
    V0G_SOC: Optional[Union[ArrayType, list]]
    V0G_trip_infeasibility: Optional[Union[ArrayType, list]]
    charge_status: Optional[str]

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # Check that usage is always <= max discharge of battery, otherwise the problem will be infeasible.
        for i in self.usage:
            if i > self.discharging_power_limit * -1:
                raise ValueError('Usage requirement of {} exceeds battery discharge limit of {}.'.format(i,
                                                                                                         self.discharging_power_limit))

        self.ports['vehicle'] = MobileElectricalStorage(**data)  # EV always has a storage port
        self.ports['vehicle'].enable_trip_slack = self.trip_slack  # Apply trip slack

        self.ports['usage'] = ElectricalDemand()  # EV always has a fixed trip port
        self.ports['usage'].add_demand_profile_from_array(self.usage, expansion_periods=1)
        # Customise connection point port type based on the charge mode
        if self.charge_mode == EVChargeMode.V0G:
            self.trip_slack = True  # Set slack to true
            self.ports['vehicle'].enable_trip_slack = self.trip_slack
            self.ports[self.connection_port_name] = ElectricalDemand()
            self.process_V0G_charging(self.interval_duration)
            self.ports[self.connection_port_name].add_demand_profile_from_array(self.V0G_delta, expansion_periods=1)
        else:
            self.ports[self.connection_port_name] = ElectricalPort()
            self.ports[self.connection_port_name].add_active_periods_from_array(self.available, expansion_periods=1)
            if self.charge_mode == EVChargeMode.V1G:
                self.ports[self.connection_port_name].set_flow_constraints(max_import=self.charging_power_limit,
                                                                           max_export=0.)

        # EV needs a custom transformation because of the positive load convention
        self.create_ev_transformation()

    def create_ev_transformation(self):
        # Create appropriate transformation: vehicle = cp - usage
        t = Transform()
        t.add_lhs_term(self.ports['vehicle'], TransformRule.Both, 1)
        t.add_lhs_term(self.ports['usage'], TransformRule.Both, 1)
        t.add_lhs_term(self.ports[self.connection_port_name], TransformRule.Both, -1)
        self.add_transformation(t)

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
        if self.charge_mode == EVChargeMode.V0G:
            assert self.ports[
                       self.connection_port_name].initial_value != 0, 'V0G connection pt port needs demand profile added.'
        else:
            assert self.ports[
                       self.connection_port_name].active_periods is not None, 'Add available periods to EV connection pt port'
        assert self.ports['usage'].initial_value != 0, 'EV usage port needs usage profile added.'

    def initialise_node(self, model, profile):
        super(EV, self).initialise_node(model, profile)
        if self.charge_mode == EVChargeMode.V0G:
            # Fix the battery state of charge, the slack variable, and battery charging/discharging
            fix_port_variable(model, self.ports['vehicle'].soc_value, self.V0G_SOC, expansion_periods=1)
            fix_port_variable(model, self.ports['vehicle'].trip_slack, self.V0G_trip_infeasibility,
                              expansion_periods=1)
            power_profile = np.array(self.V0G_delta) + np.array(self.usage) * -1
            fix_port_variable(model, self.ports['vehicle'].port_name, power_profile, expansion_periods=1)


class ElectricalPort(FlexPort):
    """ Flexible electrical port """
    units = Units.KW


class FixedElectricalPort(FixedPort):
    """ An electrical port with fixed values (parameters). No constraints on whether the port is importing/exporting."""
    units = Units.KW


class Inverter(Node):
    """ An inverter is a node with one AC port and at least one DC port.
    Flows from AC to DC, and DC to AC, are subject to conversion efficiencies."""
    max_import: Union[float, None]
    max_export: Union[float, None]
    dc_ac_efficiency: confloat(ge=0, le=1) = 1.0
    ac_dc_efficiency: confloat(ge=0, le=1) = 1.0
    dc_port_names: Optional[list] = []
    ac_port_name: Optional[str] = None  # There should generally only be one ac port
    node_rule = NodeRule.Custom

    def add_dc_port(self, port_name):
        p = ElectricalPort()
        self.dc_port_names.append(port_name)
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
        # Check that we have at least one ac and one dc port
        assert self.ac_port_name is not None, 'Define at least one ac port on inverter.'
        assert self.dc_port_names is not None, 'Define at least one dc port on inverter.'
        # Check that all ports are either ac or dc
        all_port_names = [x for x in self.ports.keys()]
        named_ports = [self.ac_port_name] + self.dc_port_names
        assert set(all_port_names) == set(named_ports), 'All ports on inverter must be ac or dc.'

    def initialise_node(self, model, profile):
        super(Inverter, self).initialise_node(model, profile)

        ac_port = self.ports[self.ac_port_name]
        # Split ac port into pos/neg, so we can apply the correct efficiencies
        ac_port.constrain_pos_neg(model)

        def inverter_ac_output_must_track_efficiency(model, p, t):  # Apply efficiency constraints
            dc_total = 0
            for dc_port_name in self.dc_port_names:
                dc_port = self.ports[dc_port_name]
                dc_total += getattr(model, dc_port.port_name)[p, t]

            return getattr(model, ac_port.pos)[p, t] * self.ac_dc_efficiency + \
                   getattr(model, ac_port.neg)[p, t] / self.dc_ac_efficiency == dc_total * -1

        setattr(model, f"con_inverter_{self.node_name}", en.Constraint(
            model.Expansion, model.Time, rule=inverter_ac_output_must_track_efficiency))


class BoundedElectricalLoad(BoundedLoad):
    units = Units.KW


"""

    Carbon ports and nodes

"""


class CarbonPort(FlexPort):
    """ A flexible carbon port"""
    units = Units.CO2


class CarbonSource(CarbonPort):
    """ A variable source of CO2 """
    flows = Flows.Export


class CarbonSink(CarbonPort):
    """ A variable sink of CO2 """
    flows = Flows.Import


class CarbonAggregation(Node):
    """ This node has an additional variable, 'total', which equals the sum of all ports defined on the node."""
    node_rule = NodeRule.Custom

    @property
    def total(self):
        return 'total_CO2_' + self.node_name

    def verify_node(self):
        super(CarbonAggregation, self).verify_node()

    def initialise_node(self, model, profile):
        super(CarbonAggregation, self).initialise_node(model, profile)
        # Create a variable for the total CO2
        setattr(model, self.total, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

    def apply_node_constraints(self, model):
        def sum_rule(model, p, t):
            a = 0
            for _, port in self.ports.items():
                a += getattr(model, port.port_name)[p, t]
            return getattr(model, self.total)[p, t] == a

        setattr(model, 'co2_sum_con_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))


"""

Prebuilt nodes

"""


class Battery(Node):

    def __init__(self,
                 port_name,
                 max_capacity: float,
                 initial_state_of_charge: float,
                 charging_power_limit: float,
                 discharging_power_limit: float,
                 storage_capacity_cost: Optional[PositiveFloat] = None,
                 charging_efficiency: float = 1,
                 discharging_efficiency: float = 1,
                 depth_of_discharge_limit: float = 0,
                 fixed_storage_capacity: bool = True,
                 regularise: bool = False,
                 **data):
        super().__init__(**data)
        self.ports[port_name] = ElectricalStorage(max_capacity=max_capacity,
                                                  depth_of_discharge_limit=depth_of_discharge_limit,
                                                  charging_power_limit=charging_power_limit,
                                                  discharging_power_limit=discharging_power_limit,
                                                  charging_efficiency=charging_efficiency,
                                                  discharging_efficiency=discharging_efficiency,
                                                  initial_state_of_charge=initial_state_of_charge,
                                                  fixed_storage_capacity=fixed_storage_capacity,
                                                  storage_capacity_cost=storage_capacity_cost,
                                                  regularise=regularise)


class Solar(Node):

    def __init__(self,
                 port_name: str,
                 profile: Union[ArrayType, dict],
                 curtailable: bool = False,
                 **data):
        super().__init__(**data)
        self.ports[port_name] = ElectricalGeneration(curtailable=curtailable)
        if type(profile) is dict:
            self.ports[port_name].add_initial_value(profile)
        else:
            self.ports[port_name].add_initial_value_from_array(profile)


class Load(Node):

    def __init__(self,
                 port_name: str,
                 port_unit: int,
                 profile: Union[dict, ArrayType, list],
                 **data):
        super().__init__(**data)
        self.ports[port_name] = Demand(units=port_unit)
        if type(profile) is dict:
            self.ports[port_name].add_initial_value(profile)
        else:
            self.ports[port_name].add_initial_value_from_array(profile)


class FlexNode(Node):

    def __init__(self,
                 port_name: str,
                 port_unit: int,
                 **data):
        super().__init__(**data)
        self.ports[port_name] = FlexPort(units=port_unit)


class FlexElectricalNode(Node):

    def __init__(self,
                 port_name: str,
                 **data):
        super().__init__(**data)
        self.ports[port_name] = FlexPort(units=Units.KW)


class NewInverter(Inverter):

    def __init__(self,
                 ac_port_name: str,
                 dc_port_names: list,
                 **data):
        super().__init__(**data)
        self.add_ac_port(ac_port_name)
        for i in dc_port_names:
            self.add_dc_port(i)


class FlexNodeWithEmissions(Node):

    def __init__(self, emitting_port: str,
                 emitting_port_units: int,
                 carbon_port: str,
                 emissions_factor:
                 Union[float, ArrayType],
                 **data):
        super().__init__(**data)
        self.ports[emitting_port] = FlexPort(units=emitting_port_units)
        self.ports[carbon_port] = CarbonSource()
        self.add_emission_transformation(emitting_port=self.ports[emitting_port],
                                         carbon_port=self.ports[carbon_port],
                                         emission_factor=emissions_factor)


# New ports


class InputOutputNode(Node):
    """
    An input-output node has one input port and one output port.
    A custom transformation can be defined between input and output.
    """
    input_port_unit: Units
    output_port_unit: Units
    # Optional parameters for controlling input/output port flows
    max_output: Optional[float]  # output might be neg or pos, leave it open
    min_output: Optional[float]
    max_input: Optional[NonNegativeFloat]  # input should generally be non negative
    min_input: Optional[NonNegativeFloat]
    node_rule: NodeRule = NodeRule.Custom


class DieselGenerator(InputOutputNode):
    """
    A diesel generator node. Converts diesel into electricity at a fixed rate of cop which is in units of
    kW/liters per second
    """
    input_port_unit = Units.LPS
    output_port_unit = Units.KW
    cop: NonNegativeFloat = 0.4 * 3600  # kW / litres per second
    startup_efficiency: NonNegativeFloat = 0.5  # ratio of efficiency in startup and shutdown period, # todo: ensure between 0-1 (confloat??)
    C02Intensity: NonNegativeFloat = 2.7  # emissions intensity kg per sec / litre per sec = kg/litre

    def __init__(self, **data) -> None:
        super().__init__(**data)
        # add an input and output node, and create appropraite transformations
        self.ports["output"] = OffOrConstrainedPort(upper_bound=self.min_output,
                                                    lower_bound=self.max_output,
                                                    units=self.output_port_unit)

        self.ports["input"] = FlexSink(units=self.input_port_unit)  # the node is importing through this port
        self.ports['co2'] = CarbonSource()
        # todo: add some validators :-)

    def apply_node_constraints(self, model):
        super(DieselGenerator, self).apply_node_constraints(model)

        def node_constraint(model, p, t):
            p_in = getattr(model, self.ports['input'].port_name)
            p_out = getattr(model, self.ports['output'].port_name)

            if (p == 0) and (t == 0):
                out = p_in[p, t] * self.startup_efficiency * self.cop
            else:
                out = (p_in[p, t] * self.startup_efficiency + p_in[p, t - 1] * (1 - self.startup_efficiency)) * self.cop
            return p_out[p, t] == - out

        def carbon_rule(model, p, t):
            p_in = getattr(model, self.ports['input'].port_name)
            c_out = getattr(model, self.ports['co2'].port_name)
            return c_out[p, t] == - p_in[p, t]

        setattr(model, 'node_con_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=node_constraint))
        setattr(model, 'node_con_co2_' + self.node_name, en.Constraint(model.Expansion, model.Time, rule=carbon_rule))
