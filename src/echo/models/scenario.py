import os
from dataclasses import dataclass

from pyomo.core.base.set import FiniteScalarRangeSet
from pyomo.environ import ConcreteModel, Param


@dataclass
class ScenarioSettings:
    """Settings specific to describing an Echo scenario"""

    interval_duration: int  # Duration of each interval, in minutes
    number_of_intervals: int  # Total number of intervals
    number_of_expansion_intervals: int  # Number of expansion intervals
    discount_rate: int = 0


@dataclass
class EngineSettings:
    """High level settings for the underlying optimisation engine

    Args:
        engine: the name (str) of the optimiser e.g. "cplex"
        engine_executable: the path to the executable (str). An empty string causes echo
            to try to determine the path to the solver.
        small_m: small bias value (float). A small fudge factor for reducing the size
            of the solution set and achieving a unique optimisation solution.
        big_m: big bias value (int). A big_m value for integer optimisation
    """

    engine: str
    engine_executable: str
    small_m: float
    big_m: int


class EchoConcreteModel(ConcreteModel):
    """Extension to pyomo's ConcreteModel that documents all the echo specific variables that
    decorate the underlying ConcreteModel"""

    small_m: Param  # A small fudge factor for reducing the size of the solution set and achieving a unique solution
    big_m: Param  # A big_m value for integer optimisation
    Time: FiniteScalarRangeSet  # We use RangeSet to create a index for each of the time periods that we will optimise within.
    Expansion: FiniteScalarRangeSet  # index for expansion periods
    discount_rates: Param

    scenario_settings: ScenarioSettings


def engine_settings_from_environment(optimiser_engine: str | None = None) -> EngineSettings:
    """Configure the optimiser through setting appropriate environmental variables."""

    if not optimiser_engine:
        optimiser_engine = os.environ.get(
            "OPTIMISER_ENGINE", "cplex"
        )  # Default to cplex, as we seem to want quadratic costs

    return EngineSettings(
        engine=optimiser_engine,
        engine_executable=os.environ.get("OPTIMISER_ENGINE_EXECUTABLE", ""),
        big_m=5000000,  # This value has been arbitrarily chosen
        small_m=0.0001,  # This value has been arbitrarily chosen
    )
