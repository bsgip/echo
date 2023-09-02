from typing import Literal, Optional

from pyomo.environ import ConcreteModel, Param, RangeSet


class EchoConcreteModel(ConcreteModel):
    """Extension to pyomo's ConcreteModel that documents all the echo specific variables that
    decorate the underlying ConcreteModel"""

    smallM: Param  # A small fudge factor for reducing the size of the solution set and achieving a unique solution
    bigM: Param  # A bigM value for integer optimisation
    Time: RangeSet  # We use RangeSet to create a index for each of the time periods that we will optimise within.
    Expansion: RangeSet  # index for expansion periods
    discount_rates: Param
