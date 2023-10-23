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
    def total(self):
        return "total_CO2_" + self.node_name

    def verify_node(self):
        super(CarbonAggregation, self).verify_node()

    def initialise_node(self, model: EchoConcreteModel, profile):
        super(CarbonAggregation, self).initialise_node(model, profile)
        # Create a variable for the total CO2
        setattr(model, self.total, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

    def apply_node_constraints(self, model: EchoConcreteModel):
        def sum_rule(model: EchoConcreteModel, p, t):
            a = 0
            for _, port in self.ports.items():
                a += getattr(model, port.port_name)[p, t]
            return getattr(model, self.total)[p, t] == a

        setattr(model, "co2_sum_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))
