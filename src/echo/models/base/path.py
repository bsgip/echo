from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

import pyomo.environ as en
import shortuuid
from attrs import define, field

from echo.configuration import Units
from echo.models.base.port import Port
from echo.models.scenario import EchoConcreteModel


@define
class Path:
    """A path is a sequence of distinct vertices (nodes)."""

    vertices: list  # list of node names

    edge_ports: list[tuple[Port, Port]] = field(factory=list)  # list of edge name tuples
    units: Units = Units.KW
    regularise: bool = False
    objective: en.numeric_expr.NumericExpression | float = 0

    contingency_neg: str | None = None
    contingency_pos: str | None = None
    path_tariff: str | None = None
    slack: str | None = None

    uid: str = field(factory=shortuuid.uuid)
    path_name: str = field()

    @path_name.default
    def _set_path_name_default(self) -> str:
        return "path_" + str(self.uid)

    flow_value: str = field()

    @flow_value.default
    def _set_flow_value_default(self) -> str:
        return "flow_value_" + self.path_name

    def add_vertices(self, vertex_list: list) -> None:
        if hasattr(vertex_list[0], "node_name"):
            vertex_list = [i.node_name for i in vertex_list]
        self.vertices = vertex_list

    def add_path_to_model(self, model: EchoConcreteModel) -> None:
        setattr(
            model,
            self.flow_value,
            en.Var(model.Expansion, model.Time, initialize=0, domain=en.NonNegativeReals),
        )

    def add_objective(self, model: EchoConcreteModel) -> None:
        total = 0

        if self.regularise is True:
            total += (
                sum(
                    getattr(model, self.flow_value)[p, t] * getattr(model, self.flow_value)[p, t]
                    for p in model.Expansion
                    for t in model.Time
                )
                * 0.0000001
            )

        self.objective += total
