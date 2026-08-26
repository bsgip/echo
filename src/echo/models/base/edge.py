from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

import pyomo.environ as en
import shortuuid
from pydantic import Field
from pyomo.core.expr.relational_expr import EqualityExpression

from echo.configuration import Flows
from echo.exceptions import ConfigurationError
from echo.models.base import BaseModel
from echo.models.base.port import Port
from echo.models.base.types import ConstraintValueType
from echo.models.scenario import EchoConcreteModel


class Edge(BaseModel):
    """
    Edges are used to connect nodes. For an edge (x, y) where x and y are nodes,
    the edge value is equal to the flow from x->y plus the flow from y->x.
    """

    uid: str = Field(default_factory=shortuuid.uuid)
    edge_name: str | None = None
    vertices: tuple[Port, Port]
    nodes: tuple[str, str] | None  # tuple of node names - todo make this required
    tariff: list | None | None

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if self.edge_name is None:
            self.edge_name = "edge_" + str(self.uid)

    def add_vertices(self, obj1: Port, obj2: Port) -> None:
        """Adds edge vertices (which are ports on nodes)

        Args:
            obj1: port object
            obj2: port object

        Returns:
            None
        """
        self.vertices = (obj1, obj2)

    def verify_edge(self) -> None:
        """Verifies that flows on ports associated with either end of an edge are the same.

        Returns:
            None

        Raises:
            ConfigurationError: If the flows on the ports at either end of an edge are not the same.
        """

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        if (port1.flows is Flows.Export) and (port2.flows is Flows.Export):
            raise ConfigurationError("Port flow constraints do not allow any flow along the edge.")
        if (port1.flows is Flows.Import) and (port2.flows is Flows.Import):
            raise ConfigurationError("Port flow constraints do not allow any flow along the edge.")

    def add_edge_to_model(self, model: EchoConcreteModel) -> None:
        """Applies edge constraint: ``port1 = -1 *port2`` to a concrete model.

        Args:
            model: pyomo concrete model

        Returns:
            None
        """

        port1 = self.vertices[0]
        port2 = self.vertices[1]

        def edge_constraint_rule(model: EchoConcreteModel, p: int, t: int) -> EqualityExpression:
            """Generates the edge constraint rule.

            Args:
                model: The concrete model from which to draw data.
                p: Index representing capacity expansion
                t: Index representing time.

            Returns:
                EqualityExpression: The transform rule.

            Raises:
                Exception: If an improper TransformRule is used.
            """

            return getattr(model, port1.port_name)[p, t] + getattr(model, port2.port_name)[p, t] == 0

        con_name = "edge_con_" + port1.port_name + "_" + port2.port_name
        setattr(
            model,
            con_name,
            en.Constraint(model.Expansion, model.Time, rule=edge_constraint_rule),
        )

    def get_max_flow_along_edge(self, forwards: bool = True) -> ConstraintValueType | None:
        """Returns the max flow along an edge.

        Args:
            forwards: True is flow is from the 0th port to the 1st port in self.vertices. False if from 1st to the 0th.
                Defaults to True.

        Returns:
            ConstraintValueType: The max flow across this edge.
        """

        max_flow = None

        if forwards is True:
            port1 = self.vertices[0]
            port2 = self.vertices[1]
        else:
            port1 = self.vertices[1]
            port2 = self.vertices[0]

        if port1.export_constraint_value is not None:
            max_flow = port1.export_constraint_value

        if port2.import_constraint_value is not None:
            if max_flow is not None:
                max_flow = min(max_flow, port2.import_constraint_value)
            else:
                max_flow = port2.import_constraint_value

        return max_flow
