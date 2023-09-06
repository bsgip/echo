from dataclasses import dataclass

from pyomo.environ import ConcreteModel, Param, RangeSet


@dataclass
class ScenarioSettings:
    """Settings specific to describing an Echo scenario"""

    interval_duration: int  # Duration of each interval, in minutes
    number_of_intervals: int  # Total number of intervals
    number_of_expansion_intervals: int  # Number of expansion intervals
    discount_rate: int


@dataclass
class EngineSettings:
    """High level settings for the underlying optimisation engine"""

    engine: str
    engine_executable: str
    smallM: float  # A small fudge factor for reducing the size of the solution set and achieving a unique optimisation solution
    bigM: int  # A bigM value for integer optimisation


class EchoConcreteModel(ConcreteModel):
    """Extension to pyomo's ConcreteModel that documents all the echo specific variables that
    decorate the underlying ConcreteModel"""

    smallM: Param  # A small fudge factor for reducing the size of the solution set and achieving a unique solution
    bigM: Param  # A bigM value for integer optimisation
    Time: RangeSet  # We use RangeSet to create a index for each of the time periods that we will optimise within.
    Expansion: RangeSet  # index for expansion periods
    discount_rates: Param

    scenario_settings: ScenarioSettings
