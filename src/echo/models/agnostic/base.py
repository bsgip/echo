import numpy as np
import pandas as pd
import pyomo.environ as en
from pydantic import root_validator, validator
from pyomo.core.expr import InequalityExpression

from echo.configuration import FlowConstraint, Flows, OptimisationType
from echo.models.agnostic.flex import FlexPort
from echo.models.base import Port
from echo.models.scenario import EchoConcreteModel
from echo.utils import (
    TimeExpandableType,
)
from echo.validators import (
    check_bound_order,
    nonnegative_load,
    nonpositive_generation,
)


class FixedPort(Port):
    """Fixed port (parameter), can either import or export."""

    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Parameter


class Source(Port):
    """A fixed source of a commodity."""

    flows = Flows.Export
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Parameter

    # Source should have non positive initial values
    non_pos_check = validator("initial_value", allow_reuse=True)(nonpositive_generation)

    def add_source_profile(self, source_values: dict) -> None:
        self.set_initial_value(source_values)

    def add_source_profile_from_array(
        self,
        source_values: list[float] | np.ndarray,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:
        self.set_initial_value_from_array(
            array=source_values, expansion_periods=expansion_periods, time_periods=time_periods
        )


class Sink(Port):
    """A fixed sink for a commodity."""

    flows = Flows.Import
    import_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Parameter

    non_neg_check = validator("initial_value", allow_reuse=True)(
        nonnegative_load
    )  # Sink should have non negative initial values

    def add_sink_profile(self, sink_values: dict[tuple[int, int], float]) -> None:
        self.set_initial_value(sink_values)

    def add_sink_profile_from_array(
        self,
        sink_values: list[float] | np.ndarray,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:

        self.set_initial_value_from_array(
            array=sink_values, expansion_periods=expansion_periods, time_periods=time_periods
        )


class Demand(Sink):
    def add_demand_profile(self, demand: dict) -> None:
        self.set_initial_value(demand)

    def add_demand_profile_from_array(
        self,
        demand: TimeExpandableType,
        expansion_periods: int = 1,
        time_periods: int | None = None,
    ) -> None:
        self.set_initial_value_from_array(array=demand, expansion_periods=expansion_periods, time_periods=time_periods)


class OffOrConstrainedPort(FlexPort):
    """A port that is either off (0) or on, and when it is on it is constrained between a min and max value."""

    lower_bound: float
    upper_bound: float

    bounds_check = root_validator(allow_reuse=True)(check_bound_order)  # checks that lower bound < upper bound

    @property
    def active(self) -> str:
        return "active_" + self.port_name

    def add_port_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_port_to_model(model, profile)
        setattr(model, self.active, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Binary))

        # Apply constraints such that if active=1, the port is bounded, and if active=0, the port is 0.
        def on_off_constraint1(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] >= getattr(model, self.active)[p, t] * self.lower_bound

        def on_off_constraint2(model: EchoConcreteModel, p: int, t: int) -> InequalityExpression:
            return getattr(model, self.port_name)[p, t] <= getattr(model, self.active)[p, t] * self.upper_bound

        setattr(model, "on_off1_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint1))
        setattr(model, "on_off2_" + self.port_name, en.Constraint(model.Expansion, model.Time, rule=on_off_constraint2))
