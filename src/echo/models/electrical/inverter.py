import pandas as pd
import pyomo.environ as en
from pydantic import Field
from pyomo.core.expr.relational_expr import EqualityExpression

from echo.exceptions import validate
from echo.models.base import Node
from echo.models.electrical.base import ElectricalPort
from echo.models.scenario import EchoConcreteModel


class Inverter(Node):
    """An inverter is a node with one AC port and at least one DC port.
    Flows from AC to DC, and DC to AC, are subject to conversion efficiencies.

    Ports can be specified at construction time using the `ac_port_name` and `dc_ports_names` or the ports can be
    added later by making one call to `add_ac_port` and as many calls to `add_dc_port` as required. It is best not
    to mix these two approaches.

    When creating ports through the constructor, the ports will be assigned default uids. If you need to flexibility
    of specifying uids for the ports then use the `add_ac_port` and `add_dc_ports` remembering to supply `uid` values.
    """

    max_import: float | None
    max_export: float | None
    dc_ac_efficiency: float = Field(default=1.0, ge=0, le=1)
    ac_dc_efficiency: float = Field(default=1.0, ge=0, le=1)
    ac_port_name: str | None = None
    dc_port_names: list[str] = Field(default_factory=list)

    def __init__(
        self,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if self.ac_port_name:
            self._add_ac_port(port_name=self.ac_port_name)
        for port_name in self.dc_port_names:
            self._add_port(port_name=port_name)

    def _add_port(self, port_name: str, uid: str | None = None) -> None:
        p = ElectricalPort(port_name=port_name, uid=uid)
        self.ports[port_name] = p

    def _add_ac_port(self, port_name: str, uid: str | None = None) -> None:
        p = ElectricalPort(port_name=port_name, uid=uid)
        p.set_flow_constraints(max_export=self.max_export, max_import=self.max_import)
        self.ports[port_name] = p

    def add_dc_port(self, port_name: str, uid: str | None = None) -> None:
        self.dc_port_names.append(port_name)
        self._add_port(port_name=port_name, uid=uid)

    def add_ac_port(self, port_name: str, uid: str | None = None) -> None:
        self.ac_port_name = port_name
        self._add_ac_port(port_name=self.ac_port_name, uid=uid)

    def verify_node(self) -> None:
        # Check that we have at least one ac and one dc port
        validate(self.ac_port_name is not None, "Define at least one ac port on inverter.")
        validate(self.dc_port_names is not None, "Define at least one dc port on inverter.")
        # Check that all ports are either ac or dc
        all_port_names = [x for x in self.ports.keys()]
        named_ports = [self.ac_port_name] + self.dc_port_names
        validate(
            set(all_port_names) == set(named_ports),
            "All ports on inverter must be ac or dc.",
        )

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        super().add_node_to_model(model, profile)

        ac_port = self.ports[self.ac_port_name]
        # Split ac port into pos/neg, so we can apply the correct efficiencies
        ac_port.constrain_pos_neg(model)

        def inverter_ac_output_must_track_efficiency(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Apply efficiency constraints"""
            dc_total = 0
            for dc_port_name in self.dc_port_names:
                dc_port = self.ports[dc_port_name]
                dc_total += getattr(model, dc_port.port_name)[p, t]

            return (
                getattr(model, ac_port.pos)[p, t] * self.ac_dc_efficiency
                + getattr(model, ac_port.neg)[p, t] / self.dc_ac_efficiency
                == dc_total * -1
            )

        setattr(
            model,
            f"con_inverter_{self.node_name}",
            en.Constraint(
                model.Expansion,
                model.Time,
                rule=inverter_ac_output_must_track_efficiency,
            ),
        )
