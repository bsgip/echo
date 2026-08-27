import pandas as pd
import pyomo.environ as en
from pydantic import PositiveFloat, root_validator
from pyomo.core.expr import EqualityExpression, InequalityExpression

from echo.configuration import FlowConstraint, Flows, OptimisationType
from echo.exceptions import validate
from echo.models.base import Port
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeExpandableType,
    TimeSeriesData,
    expand_as_array,
    set_float_var_bounds,
)
from echo.validators import (
    ArrayType,
    dod_checks,
)


class Storage(Port):
    """Same as old storage but without all the EV attributes"""

    flows = Flows.Both
    flow_type = OptimisationType.Variable
    import_constraint = FlowConstraint.Fixed
    export_constraint = FlowConstraint.Fixed
    max_capacity: float
    depth_of_discharge_limit: float = 0  # DoD limit is the percent soc to which you can discharge the storage
    min_soc: float = 0
    charging_power_limit: float
    discharging_power_limit: float
    charging_efficiency: float = 1
    discharging_efficiency: float = 1
    fixed_storage_capacity: bool = True
    storage_capacity_cost: PositiveFloat | None = None
    regularise: bool = False
    initial_state_of_charge: float | None

    dod_check = root_validator(allow_reuse=True)(dod_checks)

    @property
    def soc_value(self) -> str:
        return "storage_soc_" + self.port_name

    @property
    def optimised_capacity(self) -> str:
        return "optimised_storage_capacity_" + self.port_name

    @property
    def soc_constraint(self) -> str:
        return "soc_cons_" + self.port_name

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self.import_constraint_value = self.charging_power_limit
        self.export_constraint_value = self.discharging_power_limit

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        self.create_storage_variables(model)
        self.apply_soc_constraints(model)

    def create_storage_variables(self, model: EchoConcreteModel) -> None:
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

            def cap_limit(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
                # Ensure SOC is within max capacity
                return getattr(model, self.soc_value)[p, t] <= getattr(model, self.optimised_capacity)

            setattr(model, f"cap_lim_{self.port_name}", en.Constraint(model.Expansion, model.Time, rule=cap_limit))
        else:
            setattr(model, self.optimised_capacity, en.Param(initialize=self.max_capacity, domain=en.NonNegativeReals))

    def apply_soc_constraints(self, model: EchoConcreteModel) -> None:
        """Extract some variables to make constraints easier to write"""
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kwh = model.scenario_settings.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def soc_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return (
                    soc[p, t]
                    == self.initial_state_of_charge
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                )
            elif t == 0:
                return (
                    soc[p, t]
                    == soc[p - 1, max_t]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                )
            else:
                return (
                    soc[p, t]
                    == soc[p, t - 1]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                )

        def soc_rule_perfect_efficiency(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kwh
            elif t == 0:
                return soc[p, t] == soc[p - 1, max_t] + power[p, t] * kw_to_kwh
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kwh

        if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
            setattr(
                model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=soc_rule_perfect_efficiency)
            )
        else:
            self.constrain_pos_neg(model)
            pos = getattr(model, self.pos)  # get pos variable for writing constraints
            neg = getattr(model, self.neg)  # get neg variable for writing constraints
            setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=soc_rule))

    def add_objective(self, model: EchoConcreteModel) -> None:
        super().add_objective(model)
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
    soc_conserv: TimeExpandableType | None = None
    soc_conserv_cost: float | None = None
    # soc_conserve: scalarOrArray
    available: ArrayType | list | None = None

    @property
    def cons_slack(self) -> str:
        return "con_slack" + self.port_name

    @property
    def trip_slack(self) -> str:
        return "trip_slack_" + self.port_name

    @root_validator
    def check_soc_conserv_has_cost(cls, values: dict) -> dict:
        soc_conserv = values.get("soc_conserv")
        soc_conserv_cost = values.get("soc_conserv_cost")
        available = values.get("available")
        if soc_conserv is not None:
            validate(soc_conserv_cost is not None, "soc_conserv requires soc_conserv_cost")
            validate(available is not None, "soc_conserve requires available")
        return values

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super(Storage, self).add_port_to_model(model, profile)
        self.create_storage_variables(model)
        if self.enable_trip_slack:
            self.apply_modified_soc_constraints(model)
        else:
            self.apply_soc_constraints(model)
        self.apply_conserv_soc_constraints(model)

    def apply_conserv_soc_constraints(self, model: EchoConcreteModel) -> None:
        def soc_conservative_rule(
            model: EchoConcreteModel,
            p: int,
            t: int,
        ) -> InequalityExpression | type[en.Constraint.Skip]:
            """A rule for enforcing conservativeness while plugged in"""
            if expanded_soc_conserv and self.available is not None and self.available[t]:
                return (
                    getattr(model, self.soc_value)[p, t]
                    + getattr(model, self.cons_slack)[p, t]
                    - expanded_soc_conserv[p, t]
                    >= 0
                )
            else:
                return en.Constraint.Skip

        if self.soc_conserv is not None:
            expanded_soc_conserv = expand_as_array(
                TimeSeriesData(
                    value=self.soc_conserv,
                    num_expansion_intervals=len(model.Expansion),
                    num_time_intervals=len(model.Time),
                )
            )
            setattr(
                model, self.cons_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
            )
            setattr(
                model,
                f"cons_soc_{self.port_name}",
                en.Constraint(model.Expansion, model.Time, rule=soc_conservative_rule),
            )

    def apply_modified_soc_constraints(self, model: EchoConcreteModel) -> None:
        """Get some variables to make constraints easier to write"""
        max_t = len(model.Time)  # maximum time interval t
        kw_to_kwh = model.scenario_settings.interval_duration / 60  # conversion from kW to kWh
        soc = getattr(model, self.soc_value)
        power = getattr(model, self.port_name)

        def soc_rule_slack(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return (
                    soc[p, t]
                    == self.initial_state_of_charge
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                    + slack[p, t]
                )
            elif t == 0:
                return (
                    soc[p, t]
                    == soc[p - 1, max_t]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                    + slack[p, t]
                )
            else:
                return (
                    soc[p, t]
                    == soc[p, t - 1]
                    + pos[p, t] * kw_to_kwh * self.charging_efficiency
                    + neg[p, t] * kw_to_kwh / self.discharging_efficiency
                    + slack[p, t]
                )

        def soc_rule_perfect_efficiency_slack(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            if p == 0 and t == 0:
                return soc[p, t] == self.initial_state_of_charge + power[p, t] * kw_to_kwh + slack[p, t]
            elif t == 0:
                return soc[p, t] == soc[p, t - 1] + power[p - 1, max_t] * kw_to_kwh + slack[p, t]
            else:
                return soc[p, t] == soc[p, t - 1] + power[p, t] * kw_to_kwh + slack[p, t]

        if self.enable_trip_slack is True:
            """Create a slack variable"""
            setattr(
                model, self.trip_slack, en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals)
            )

            # get slack variable for writing constraints
            slack = getattr(model, self.trip_slack)

            # Apply the modified soc constraint, which will overwrite the previously created one
            if (self.charging_efficiency == 1) and (self.discharging_efficiency == 1):
                setattr(
                    model,
                    self.soc_constraint,
                    en.Constraint(model.Expansion, model.Time, rule=soc_rule_perfect_efficiency_slack),
                )
            else:
                self.constrain_pos_neg(model)
                pos = getattr(model, self.pos)  # get pos variable for writing constraints
                neg = getattr(model, self.neg)  # get neg variable for writing constraints
                setattr(model, self.soc_constraint, en.Constraint(model.Expansion, model.Time, rule=soc_rule_slack))

    def add_objective(self, model: EchoConcreteModel) -> None:
        super().add_objective(model)
        total = 0

        if self.enable_trip_slack:
            total += (
                sum(getattr(model, self.trip_slack)[p, t] for p in model.Expansion for t in model.Time)
                * model.big_m
                * 20
            )  # we want this to be more important than import/export constraints

        if self.soc_conserv is not None:
            total += (
                sum(getattr(model, self.cons_slack)[p, t] for p in model.Expansion for t in model.Time)
                * self.soc_conserv_cost
            )

        self.objective += total
