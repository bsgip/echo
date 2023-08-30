from typing import Literal, Optional

from pyomo.environ import ConcreteModel, Param, RangeSet

from echo.models.base import Path


class EchoConcreteModel(ConcreteModel):
    """Extension to pyomo's ConcreteModel that documents all the echo specific variables that
    decorate the underlying ConcreteModel"""

    interval_duration: int  # Duration of each interval, in minutes
    number_of_intervals: int  # Total number of intervals
    number_of_expansion_intervals: int  # Number of expansion intervals

    paths: dict[tuple, Path]
    smallM: Param  # A small fudge factor for reducing the size of the solution set and achieving a unique optimisation solution
    bigM: Param  # A bigM value for integer optimisation
    Time: RangeSet  # We use RangeSet to create a index for each of the time periods that we will optimise within.
    Expansion: Optional[RangeSet]  # index for expansion periods

    dr: Literal["discount_rates"]
    discount_rates: Param
