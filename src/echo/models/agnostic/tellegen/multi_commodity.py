from collections.abc import Iterable
from functools import partial

import pyomo.environ as en
from pyomo.core.expr import EqualityExpression

from echo.models.base import Node, Port
from echo.models.scenario import EchoConcreteModel


class MultiCommodityTellegenNode(Node):
    """
    A node with ports that have multiple commodities.
    A tellegen constraint is applied per commodity.
    """

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        """Apply Tellegen constraint for same commodity ports."""

        def tellegen_node_rule(
            commodity_ports: Iterable[Port],
            model: EchoConcreteModel,
            p: int,
            t: int,
        ) -> EqualityExpression:
            net_flow = 0
            for port in commodity_ports:
                port_flow = getattr(model, port.port_name)
                net_flow += port_flow[p, t]
            return net_flow == 0

        commodities = dict()
        for p in self.ports.values():
            if commodities.get(p.units) is None:
                commodities[p.units] = [p]
            else:
                commodities[p.units].append(p)

        for commodity_type, commodity_ports in commodities.items():
            setattr(
                model,
                "node_con_" + str(commodity_type) + self.node_name,
                en.Constraint(
                    model.Expansion,
                    model.Time,
                    rule=partial(tellegen_node_rule, commodity_ports),
                ),
            )
