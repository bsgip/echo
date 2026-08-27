import pandas as pd
import pyomo.environ as en
from pydantic import root_validator
from pyomo.core.expr import EqualityExpression

from echo.configuration import Units
from echo.exceptions import ConfigurationError
from echo.models.agnostic.flex import FlexSink
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.validators import node_unit_validator


class AggregationNode(Node):
    """Arbitrary commodity aggregation node.

    This node has an additional variable, 'total', which equals the sum of all ports defined on the node.
    port_units attribute is used for validation, all ports must be the same commodity.
    """

    port_units: Units

    aggregator_unit_check = root_validator(allow_reuse=True)(node_unit_validator)

    @property
    def total(self) -> None:
        return "total_value_" + self.node_name

    def verify_node(self) -> None:
        super().verify_node()

    def add_port(self, name: str, port: FlexSink | None = None) -> None:
        if port is None:
            port = FlexSink()

        if self.ports.get(name) is None:
            if port.units == Units.NA:
                port.units = self.port_units
            if port.units != self.port_units:
                raise ValueError(
                    f"All ports on Aggregation node must match the node units {self.port_units}."
                    f"Received new port with units {port.units} for node {self.node_name}"
                )
            self.ports[name] = port
        else:
            raise ConfigurationError(f"Port with name {name} is already defined on node {self.node_name}")

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)
        # Create a variable for the total value
        setattr(model, self.total, en.Var(model.Expansion, model.Time, initialize=0, domain=en.Reals))

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def sum_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            a = 0
            for port in self.ports.values():
                a += getattr(model, port.port_name)[p, t]
            return getattr(model, self.total)[p, t] == a

        setattr(model, "total_sum_con_" + self.node_name, en.Constraint(model.Expansion, model.Time, rule=sum_rule))
