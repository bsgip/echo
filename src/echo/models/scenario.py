import os
from dataclasses import dataclass
from typing import Optional

from pyomo.environ import ConcreteModel, Param, RangeSet


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
        smallM: small bias value (float). A small fudge factor for reducing the size
            of the solution set and achieving a unique optimisation solution.
        bigM: big bias value (int). A bigM value for integer optimisation
    """

    engine: str
    engine_executable: str
    smallM: float
    bigM: int


class EchoConcreteModel(ConcreteModel):
    """Extension to pyomo's ConcreteModel that documents all the echo specific variables that
    decorate the underlying ConcreteModel"""

    smallM: Param  # A small fudge factor for reducing the size of the solution set and achieving a unique solution
    bigM: Param  # A bigM value for integer optimisation
    Time: RangeSet  # We use RangeSet to create a index for each of the time periods that we will optimise within.
    Expansion: RangeSet  # index for expansion periods
    discount_rates: Param

    scenario_settings: ScenarioSettings


def engine_settings_from_environment(optimiser_engine: Optional[str] = None) -> EngineSettings:
    """Configure the optimiser through setting appropriate environmental variables."""

    DEFAULT_OPTIMISER_ENGINE = "cplex"

    # optimiser_engine is None or "" (empty string)
    if not optimiser_engine:
        optimiser_engine = os.environ.get("OPTIMISER_ENGINE", DEFAULT_OPTIMISER_ENGINE)
    optimiser_engine = optimiser_engine.lower()

    return EngineSettings(
        engine=optimiser_engine,
        engine_executable=os.environ.get("OPTIMISER_ENGINE_EXECUTABLE", ""),
        bigM=5000000,  # This value has been arbitrarily chosen
        smallM=0.0001,  # This value has been arbitrarily chosen
    )


def can_optimiser_do_non_linear_optimisation(optimiser: str) -> bool:
    """Returns True if optimiser can *only* do linear optimisations"""
    linear_optimisers = ["cbc"]  # TODO Make this list complete
    return optimiser not in linear_optimisers
