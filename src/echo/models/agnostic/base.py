import numpy as np
from attrs import define, field

from echo.configuration import FlowConstraint, Flows, OptimisationType
from echo.models.base import Port
from echo.utils import (
    TimeExpandableType,
)
from echo.validators import (
    nonnegative_load_validator,
    nonpositive_generation_validator,
)


@define
class FixedPort(Port):
    """Fixed port (parameter), can either import or export."""

    flows: Flows = Flows.Both
    import_constraint: FlowConstraint = FlowConstraint.NoConstraint
    export_constraint: FlowConstraint = FlowConstraint.NoConstraint
    flow_type: OptimisationType = OptimisationType.Parameter


@define
class Source(Port):
    """A fixed source of a commodity."""

    flows: Flows = Flows.Export
    export_constraint: FlowConstraint = FlowConstraint.NoConstraint
    flow_type: OptimisationType = OptimisationType.Parameter
    initial_value: dict[tuple[int, int], float] | float = field(default=0, validator=nonpositive_generation_validator)

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


@define
class Sink(Port):
    """A fixed sink for a commodity."""

    flows: Flows = Flows.Import
    import_constraint: FlowConstraint = FlowConstraint.NoConstraint
    flow_type: OptimisationType = OptimisationType.Parameter

    initial_value: dict[tuple[int, int], float] | float = field(default=0, validator=nonnegative_load_validator)

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


@define
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
