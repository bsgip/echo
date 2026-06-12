import pandas as pd
from pyomo.core.expr import EqualityExpression
import pyomo.environ as en

from echo.configuration import Flows, Units
from echo.models.agnostic import FlexPort
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel


class CarbonPort(FlexPort):
    """A flexible carbon port"""

    units = Units.CO2


class CarbonSource(CarbonPort):
    """A variable source of CO2"""

    flows = Flows.Export


class CarbonSink(CarbonPort):
    """A variable sink of CO2"""

    flows = Flows.Import


class CarbonAggregation(Node):
    """This node has an additional variable, 'total', which equals the sum of all ports defined on the node."""

    @property
    def total(self) -> str:
        return "total_CO2_" + self.node_name

    def verify_node(self) -> None:
        super().verify_node()

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        # Create a variable for the total CO2
        setattr(model, self.total, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def sum_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            a = 0
            for port in self.ports.values():
                a += getattr(model, port.port_name)[p, t]
            return getattr(model, self.total)[p, t] == a

        setattr(model, "co2_sum_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))
