import pyomo.environ as en
from pydantic import root_validator
from pyomo.core.expr import EqualityExpression

from echo.exceptions import validate
from echo.models.base import Node
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    node_unit_validator,
)


class TellegenNode(Node):
    """A node that implements a Tellegen constraint requiring that port values sum to zero."""

    tellegen_unit_check = root_validator(allow_reuse=True)(node_unit_validator)

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        def tellegen_node_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            a = 0
            for port in node_ports.values():
                a += getattr(model, port.port_name)[p, t]
            return a == 0

        node_ports = self.ports
        con_name = "reliability_con_" + self.node_name
        setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=tellegen_node_rule))

    def verify_node(self) -> None:
        super().verify_node()

        validate(
            len(self.ports) >= 2,
            f"A tellegen node must have at least two ports. Offending node has the name: {self.node_name}",
        )
