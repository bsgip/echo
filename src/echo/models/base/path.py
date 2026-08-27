from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

import pyomo.environ as en
import shortuuid
from pydantic import Field

from echo.configuration import Units
from echo.models.base import BaseModel
from echo.models.base.port import Port
from echo.models.scenario import EchoConcreteModel


class Path(BaseModel):
    """A path is a sequence of distinct vertices (nodes)."""

    edge_ports: list[tuple[Port, Port]] = []  # list of edge name tuples
    vertices: list  # list of node names
    uid: str = Field(default_factory=shortuuid.uuid)
    path_name: str | None = None
    units = Units.KW
    regularise: bool = False
    objective: en.numeric_expr.NumericExpression | float = 0

    flow_value: str = ""
    contingency_neg: str | None
    contingency_pos: str | None
    path_tariff: str | None
    slack: str | None

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if self.path_name is None:
            self.path_name = "path_" + str(self.uid)
        self.flow_value = "flow_value_" + self.path_name

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
