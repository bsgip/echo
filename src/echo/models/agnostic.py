from typing import Optional, Union

import pandas as pd
import pyomo.environ as en
from pydantic import Field, NonNegativeFloat, PositiveFloat, root_validator, validator

from echo.configuration import FlowConstraint, Flows, NodeRule, OptimisationType, Units
from echo.echo_validators import (
    ArrayType,
    check_bound_order,
    dod_checks,
    node_unit_validator,
    nonnegative_costs,
    nonnegative_load,
    nonpositive_generation,
    set_bounds_from_piecewise_pts,
    validate_piecewise_arrays,
)
from echo.models.base import Node, Port
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    ArrayWrap,
    ArrayWrappableType,
    generate_array_constraint,
    populate_values_across_time_and_expansion_indices,
    set_float_var_bounds,
    set_var_bounds_from_dict,
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

    def add_source_profile_from_array(self, source_values, expansion_periods=1, time_periods: Optional[int] = None):
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

    def add_sink_profile_from_array(self, sink_values, expansion_periods=1, time_periods: Optional[int] = None):
        self.add_initial_value_from_array(
            array=sink_values, expansion_periods=expansion_periods, time_periods=time_periods
        )


class Demand(Sink):
    def add_demand_profile(self, demand: dict):
        self.add_initial_value(demand)

    def add_demand_profile_from_array(
        self, demand: ArrayWrappableType, expansion_periods=1, time_periods: Optional[int] = None
    ):
        self.add_initial_value_from_array(array=demand, expansion_periods=expansion_periods, time_periods=time_periods)


class ControlledLoadOrGen(FlexPort):
    """
    A controlled load or generation has a max/min power, as well as a max/min utilisation.
    Min utilisation is the ratio between the minimum energy consumed/generated,
        and the maximum energy that could be consumed/generated if the load operated at max power.
    Max utilisation is the ratio between the maximum energy consumed/generated,
        and the maximum energy that could be consumed/generated if the load operated at max power.
    """

    min_utilisation: Optional[float] = None
    max_utilisation: Optional[float] = None
    max_power: Optional[float] = None
    min_power: Optional[float] = None
    units: Units = Units.KW

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
        super(ControlledLoadOrGen, self).initialise_port(model, profile)

        # Set bounds using min and max power
        set_float_var_bounds(model=model, var_name=self.port_name, ub=self.max_power, lb=self.min_power)

        if self.min_utilisation is not None and self.max_power is not None:
            min_utilisation: float = self.min_utilisation
            max_power: float = self.max_power

            def sum_of_energy_must_be_greater_than_min(model: EchoConcreteModel):
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.scenario_settings.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    >= min_utilisation
                    * max_power
                    * model.scenario_settings.interval_duration
                    * model.scenario_settings.number_of_intervals
                    / 60.0
                )

            setattr(
                model,
                f"cons_{self.port_name}_min_utilisation_req",
                en.Constraint(rule=sum_of_energy_must_be_greater_than_min),
            )

        if self.max_utilisation is not None and self.max_power is not None:
            max_utilisation: float = self.max_utilisation
            max_power = self.max_power

            def sum_of_energy_must_be_less_than_max(model: EchoConcreteModel):
                return (
                    sum(
                        getattr(model, self.port_name)[p, i] * model.scenario_settings.interval_duration / 60.0
                        for p in model.Expansion
                        for i in model.Time
                    )
                    <= max_utilisation
                    * max_power
                    * model.scenario_settings.interval_duration
                    * model.scenario_settings.number_of_intervals
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

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
        super(OffOrConstrainedPort, self).initialise_port(model, profile)
        setattr(model, self.active, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        # Apply constraints such that if active=1, the port is bounded, and if active=0, the port is 0.
        def on_off_constraint1(model: EchoConcreteModel, p, t):
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.active)[p, t] * self.lower_bound

        def on_off_constraint2(model: EchoConcreteModel, p, t):
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * self.upper_bound

        setattr(model, "on_off1_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint1))
        setattr(model, "on_off2_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint2))


class BoundedPort(FlexPort):
    """A flex port with an upper and lower bound"""

    upper_bound: Union[ArrayType, float]
    lower_bound: Union[ArrayType, float]

    bound_check = root_validator(allow_reuse=True)(check_bound_order)  # check lower bound < upper bound

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
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

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
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

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
        super(Storage, self).initialise_port(model, profile)
        self.create_storage_variables(model)
        self.apply_soc_constraints(model)

    def create_storage_variables(self, model: EchoConcreteModel):
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

            def cap_limit(model: EchoConcreteModel, p, t):  # Ensure SOC is within max capacity
                return getattr(model, self.soc_value)[p, t] <= getattr(model, self.optimised_capacity)

            setattr(model, f"cap_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=cap_limit))
        else:
            setattr(model, self.optimised_capacity, en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

    def apply_soc_constraints(self, model: EchoConcreteModel):
        # Extract some variables to make constraints easier to write
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kWh = model.scenario_settings.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def SOC_rule(model: EchoConcreteModel, p, t):
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

        def SOC_rule_perfect_efficiency(model: EchoConcreteModel, p, t):
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

    def add_objective(self, model: EchoConcreteModel):
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

    def initialise_port(self, model: EchoConcreteModel, profile: pd.DataFrame):
        super(Storage, self).initialise_port(model, profile)
        self.create_storage_variables(model)
        self.apply_modified_soc_constraints(model)
        self.apply_conserv_soc_constraints(model)

    def apply_conserv_soc_constraints(self, model: EchoConcreteModel):
        def soc_conservative_rule(
            model: EchoConcreteModel, p, t
        ):  # a rule for enforcing conservativeness while plugged in
            if self.soc_conserv and self.available is not None and self.available[t]:
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

    def apply_modified_soc_constraints(self, model: EchoConcreteModel):
        # Get some variables to make constraints easier to write
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kWh = model.scenario_settings.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def SOC_rule_slack(model: EchoConcreteModel, p, t):
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

        def SOC_rule_perfect_efficiency_slack(model: EchoConcreteModel, p, t):
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

    def add_objective(self, model: EchoConcreteModel):
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
    node_rule = NodeRule.Custom


class TimeVaryingPiecewiseIONode(InputOutputNode):
    """
    Node with an input and output port. The relationship between input and output is defined at each time
    interval by an array of input-->output point pairs, which are used to construct a piecewise constraint.
    """

    input_pts: Optional[dict]  # dict where the keys are planning-time period tuple, and value is input pt array
    output_pts: Optional[dict]  # dict where the keys are planning-time period tuple, and value is output pt array

    # These values are automatically calculated by the 'set_bounds_from_piecewise_pts' validator
    input_ub: Optional[float] = None
    input_lb: Optional[float] = None
    output_ub: Optional[float] = None
    output_lb: Optional[float] = None

    piecewise_check = root_validator(allow_reuse=True)(validate_piecewise_arrays)  # validate input/output pts
    populate_bounds = root_validator(allow_reuse=True)(
        set_bounds_from_piecewise_pts
    )  # set attributes input_ub, input_lb, output_ub, output_lb from input pts/output pts

    def __init__(self, **data):
        super().__init__(**data)
        # Create an input port and an outport port with the correct units
        self.ports["input"] = FlexPort(units=self.input_port_unit)
        self.ports["output"] = FlexPort(units=self.output_port_unit)

    def verify_node(self):
        assert self.input_pts is not None, "No input points defined"
        assert self.output_pts is not None, "No output points defined"

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(TimeVaryingPiecewiseIONode, self).initialise_node(model, profile)
        # Bound input and output port variables, otherwise piecewise constraint will fail
        set_float_var_bounds(model=model, var_name=self.ports["input"].port_name, ub=self.input_ub, lb=self.input_lb)
        set_float_var_bounds(model=model, var_name=self.ports["output"].port_name, ub=self.output_ub, lb=self.output_lb)

    def apply_node_constraints(self, model: EchoConcreteModel):
        xvar = getattr(model, self.ports["input"].port_name)
        yvar = getattr(model, self.ports["output"].port_name)
        xdata = self.input_pts
        ydata = self.output_pts

        con_name = "piecewise_con_" + self.node_name
        setattr(
            model,
            con_name,
            en.Piecewise(
                model.Expansion, model.Time, yvar, xvar, pw_pts=xdata, pw_constr_type="EQ", f_rule=ydata, pw_repn="SOS2"
            ),
        )


class SinglePiecewiseIONode(TimeVaryingPiecewiseIONode):
    """
    The relationship between input and output for all time intervals
    is given by an array of input-->output point pairs, which are used to construct a piecewise constraint.
    """

    def add_input_pts(self, array, time_periods, expansion_periods=1):
        """Tiles input points across time and expansion periods."""
        self.input_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)

    def add_output_pts(self, array, time_periods, expansion_periods=1):
        """Tiles output points across time and expansion periods."""
        self.output_pts = populate_values_across_time_and_expansion_indices(array, time_periods, expansion_periods)


class TimeDelayNode(InputOutputNode):
    """A time delay node is an input-output node that implements a fixed delay between input and output."""

    time_delay: int  # number of time intervals delay between input and output
    node_rule: NodeRule = NodeRule.Custom

    def __init__(self, **data):
        super().__init__(**data)
        self.ports["input"] = FlexSink(units=self.input_port_unit)
        self.ports["output"] = FlexSource(units=self.output_port_unit)

    def apply_node_constraints(self, model: EchoConcreteModel):
        def time_delay_rule(model: EchoConcreteModel, p, t):
            """This is a modified tellegen rule,
            where the sum=0 applies over staggered time periods according to the time delay"""
            a = getattr(model, self.ports["input"].port_name)
            b = getattr(model, self.ports["output"].port_name)
            if t < self.time_delay:
                return b[p, t] == 0
            else:
                return b[p, t] == a[p, int(t - self.time_delay)] * -1

        con_name = "time_delay_con_" + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=time_delay_rule))
