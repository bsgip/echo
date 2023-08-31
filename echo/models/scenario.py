from dataclasses import dataclass


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
