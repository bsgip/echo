import pickle
import uuid
import warnings
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Type, Union

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import pyomo.environ as en
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, PositiveFloat, root_validator, validator

from echo.configuration import FlowConstraint, Flows, NodeRule, OptimisationType, TransformRule, Units
from echo.constants import negative_variable_component, positive_variable_component
from echo.echo_validators import (
    ArrayType,
    check_bound_order,
    dod_checks,
    export_cons_check,
    import_cons_check,
    node_unit_validator,
    nonnegative_costs,
    nonnegative_load,
    nonpositive_generation,
)
from echo.models.base import Edge, Node, Port
from echo.models.pyomo import EchoConcreteModel
from echo.utils import (
    ArrayWrap,
    generate_array_constraint,
    set_float_var_bounds,
    set_var_bounds_from_dict,
    to_initial_values,
)

"""

    Commodity agnostic ports and nodes

"""


class TellegenNode(Node):
    """A node that implements a Tellegen constraint requiring that port values sum to zero."""

    node_rule = NodeRule.Tellegen

    tellegen_unit_check = root_validator(allow_reuse=True)(node_unit_validator)


class FlexPort(Port):
    """Flexible variable port, which can import and export without constraints."""

    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    opt_type = OptimisationType.Variable


class FlexSink(FlexPort):
    """Flexible port, imports only"""

    flows = Flows.Import


class FlexSource(FlexPort):
    """Flexible ports, exports only"""

    flows = Flows.Export


class FixedPort(Port):
    """Fixed port (parameter), can either import or export."""

    opt_type = OptimisationType.Parameter
    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint


class Source(Port):
    """A fixed source of a commodity."""

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
    """A fixed sink for a commodity."""

    flows = Flows.Import
    opt_type = OptimisationType.Parameter
    import_constraint = FlowConstraint.NoConstraint

    non_neg_check = validator("initial_value", allow_reuse=True)(
        nonnegative_load
    )  # Sink should have non negative initial values

    def add_sink_profile(self, sink_values: dict):
        self.add_initial_value(sink_values)

    def add_sink_profile_from_array(self, sink_values, expansion_periods=1, time_periods: int = None):
        self.add_initial_value_from_array(
            array=sink_values, expansion_periods=expansion_periods, time_periods=time_periods
        )


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

    def initialise_port(self, model: en.ConcreteModel, profile: pd.DataFrame):
        super(ControlledLoadOrGen, self).initialise_port(model, profile)

        # Set bounds using min and max power
        set_float_var_bounds(model=model, var_name=self.port_name, ub=self.max_power, lb=self.min_power)

        if self.min_utilisation is not None:

            def sum_of_energy_must_be_greater_than_min(model):
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    >= self.min_utilisation
                    * self.max_power
                    * model.interval_duration
                    * model.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_min_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_greater_than_min),
            )

        if self.max_utilisation is not None:

            def sum_of_energy_must_be_less_than_max(model):
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    <= self.max_utilisation
                    * self.max_power
                    * model.interval_duration
                    * model.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_max_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_less_than_max),
            )


class ControlledLoad(ControlledLoadOrGen):
    max_power: float = Field(ge=0)
    min_power: float = Field(ge=0)
    flows = Flows.Import


class ControlledGen(ControlledLoadOrGen):
    max_power: float = Field(le=0)
    min_power: float = Field(le=0)
    flows = Flows.Export


class OffOrConstrainedPort(FlexPort):
    """A port that is either off (0) or on, and when it is on it is constrained between a min and max value."""

    lower_bound: float
    upper_bound: float

    bounds_check = root_validator(allow_reuse=True)(check_bound_order)  # checks that lower bound < upper bound

    @property
    def active(self):
        return "active_" + self.port_name

    def initialise_port(self, model: en.ConcreteModel, profile: pd.DataFrame):
        super(OffOrConstrainedPort, self).initialise_port(model, profile)
        setattr(model, self.active, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        # Apply constraints such that if active=1, the port is bounded, and if active=0, the port is 0.
        def on_off_constraint1(model, p, t):
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.active)[p, t] * self.lower_bound

        def on_off_constraint2(model, p, t):
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * self.upper_bound

        setattr(model, "on_off1_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint1))
        setattr(model, "on_off2_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint2))


class BoundedPort(FlexPort):
    """A flex port with an upper and lower bound"""

    upper_bound: Union[ArrayType, float]
    lower_bound: Union[ArrayType, float]

    bound_check = root_validator(allow_reuse=True)(check_bound_order)  # check lower bound < upper bound

    def initialise_port(self, model: en.ConcreteModel, profile: pd.DataFrame):
        super(BoundedPort, self).initialise_port(model, profile)
        # Set bounds on our port variable
        ub_dict = generate_array_constraint(self.upper_bound, time_periods=len(model.Time), expansion_periods=1)
        lb_dict = generate_array_constraint(self.lower_bound, time_periods=len(model.Time), expansion_periods=1)
        set_var_bounds_from_dict(getattr(model, self.port_name), ub=ub_dict, lb=lb_dict)


class BoundedLoad(BoundedPort):
    """A port where the load has to be within a max and min value which is specified at each timestep."""

    import_constraint = FlowConstraint.NoConstraint

    # Do additional validation to make sure both bounds are >= 0
    upper_bound_check = validator("upper_bound", allow_reuse=True)(nonnegative_costs)
    lower_bound_check = validator("lower_bound", allow_reuse=True)(nonnegative_costs)

    def initialise_port(self, model: en.ConcreteModel, profile: pd.DataFrame):
        super(BoundedLoad, self).initialise_port(model, profile)


class Storage(Port):
    """Same as old storage but without all the EV attributes"""

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
        return "storage_soc_" + self.port_name

    @property
    def optimised_capacity(self):
        return "optimised_storage_capacity_" + self.port_name

    @property
    def soc_constraint(self):
        return "soc_cons_" + self.port_name

    def __init__(self, **data):
        super().__init__(**data)
        self.import_constraint_value = self.charging_power_limit
        self.export_constraint_value = self.discharging_power_limit

    def initialise_port(self, model: en.ConcreteModel, profile: pd.DataFrame):
        super(Storage, self).initialise_port(model, profile)
        self.create_storage_variables(model)
        self.apply_soc_constraints(model)

    def create_storage_variables(self, model):
        # Create soc variable and bound it
        setattr(
            model,
            self.soc_value,
            en.Var(
                model.Expansion,
                model.Time,
                initialize=self.initial_state_of_charge,
                bounds=(self.min_soc, self.max_capacity),
            ),
        )
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
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kWh = model.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def SOC_rule(model, p, t):
            if p == 0 and t == 0:
                return (
                    soc[p, t]
                    == self.initial_state_of_charge
                    + pos[p, t] * kw_to_kWh * self.charging_efficiency
                    + neg[p, t] * kw_to_kWh / self.discharging_efficiency
                )
            elif t == 0:
                return (
                    soc[p, t]
                    == soc[p - 1, max_t]
                    + pos[p, t] * kw_to_kWh * self.charging_efficiency
                    + neg[p, t] * kw_to_kWh / self.discharging_efficiency
                )
            else:
                return (
                    soc[p, t]
                    == soc[p, t - 1]
                    + pos[p, t] * kw_to_kWh * self.charging_efficiency
                    + neg[p, t] * kw_to_kWh / self.discharging_efficiency
                )

        def SOC_rule_perfect_efficiency(model, p, t):
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kWh
            elif t == 0:
                return soc[p, t] == soc[p - 1, max_t] + power[p, t] * kw_to_kWh
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kWh

        if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
            setattr(
                model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency)
            )
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
            total += (
                sum(
                    getattr(model, self.pos)[p, t] * getattr(model, self.pos)[p, t]
                    + getattr(model, self.neg)[p, t] * getattr(model, self.neg)[p, t]
                    for p in model.Expansion
                    for t in model.Time
                )
                * 0.0000001
            )

        if self.storage_capacity_cost is not None:
            total += getattr(model, self.optimised_capacity) * self.storage_capacity_cost

        self.objective += total


class MobileStorage(Storage):
    """New Storage + EV attributes"""

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
        return "con_slack" + self.port_name

    @property
    def trip_slack(self):
        return "trip_slack_" + self.port_name

    @root_validator
    def check_soc_conserv_has_cost(cls, values):
        soc_conserv = values.get("soc_conserv")
        soc_conserv_cost = values.get("soc_conserv_cost")
        available = values.get("available")
        if soc_conserv is not None:
            assert soc_conserv_cost is not None, "soc_conserv requires soc_conserv_cost"
            assert available is not None, "soc_conserve requires available"
        return values

    def initialise_port(self, model: en.ConcreteModel, profile: pd.DataFrame):
        super(Storage, self).initialise_port(model, profile)
        self.create_storage_variables(model)
        self.apply_modified_soc_constraints(model)
        self.apply_conserv_soc_constraints(model)

    def apply_conserv_soc_constraints(self, model):
        def soc_conservative_rule(model, p, t):  # a rule for enforcing conservativness while plugged in
            if self.available[t]:
                return (
                    getattr(model, self.soc_value)[p, t]
                    + getattr(model, self.cons_slack)[p, t]
                    - self.soc_conserv[p, t]
                    >= 0
                )
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            self.soc_conserv.set_periods(len(model.Expansion), len(model.Time))
            # self.soc_conserv = generate_array_constraint(self.soc_conserv, len(model.Time), len(model.Expansion))
            setattr(
                model, self.cons_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
            )
            setattr(
                model,
                f"cons_soc_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=soc_conservative_rule),
            )

    def apply_modified_soc_constraints(self, model):
        # Get some variables to make constraints easier to write
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kWh = model.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def SOC_rule_slack(model, p, t):
            if p == 0 and t == 0:
                return (
                    soc[p, t]
                    == self.initial_state_of_charge
                    + pos[p, t] * kw_to_kWh * self.charging_efficiency
                    + neg[p, t] * kw_to_kWh / self.discharging_efficiency
                    + slack[p, t]
                )
            elif t == 0:
                return (
                    soc[p, t]
                    == soc[p - 1, max_t]
                    + pos[p, t] * kw_to_kWh * self.charging_efficiency
                    + neg[p, t] * kw_to_kWh / self.discharging_efficiency
                    + slack[p, t]
                )
            else:
                return (
                    soc[p, t]
                    == soc[p, t - 1]
                    + pos[p, t] * kw_to_kWh * self.charging_efficiency
                    + neg[p, t] * kw_to_kWh / self.discharging_efficiency
                    + slack[p, t]
                )

        def SOC_rule_perfect_efficiency_slack(model, p, t):
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kWh + slack[p, t]
            elif t == 0:
                return soc[p, t] == soc[p, t - 1] + power[p - 1, max_t] * kw_to_kWh + slack[p, t]
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kWh + slack[p, t]

        if self.enable_trip_slack is True:
            # Create a slack variable
            setattr(
                model, self.trip_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
            )

            slack = getattr(model, self.trip_slack)  # get slack variable for writing constraints
            # Apply the modified soc constraint, which will overwrite the previously created one
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(
                    model,
                    self.soc_constraint,
                    en.Constraint(model.Expansion, model.Time, rule=SOC_rule_perfect_efficiency_slack),
                )
            else:
                self.constrain_pos_neg(model)
                pos = getattr(model, self.pos)  # get pos variable for writing constraints
                neg = getattr(model, self.neg)  # get neg variable for writing constraints
                setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=SOC_rule_slack))

    def add_objective(self, model):
        super(MobileStorage, self).add_objective(model)
        total = 0

        if self.enable_trip_slack:
            total += (
                sum(getattr(model, self.trip_slack)[p, t] for p in model.Expansion for t in model.Time)
                * model.bigM
                * 20
            )  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            total += (
                sum(getattr(model, self.cons_slack)[p, t] for p in model.Expansion for t in model.Time)
                * self.soc_conserv_cost
            )

        self.objective += total
