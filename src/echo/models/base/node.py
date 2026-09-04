from __future__ import annotations  # Deprecating in python 3.15 in favour of lazy annotations (PEP 649 and 749)

from collections.abc import Iterable

import pandas as pd
import pyomo.environ as en
import shortuuid
from pydantic import Field

from echo.exceptions import ConfigurationError
from echo.models.base import BaseModel
from echo.models.base.port import Port
from echo.models.scenario import EchoConcreteModel


class Node(BaseModel):
    """
    Nodes are collections of one or more ports that can include non-trivial relationships between the ports,
    this allows transformations to be implemented.
    """

    node_name: str = ""
    uid: str = Field(default_factory=shortuuid.uuid)
    ports: dict[str, Port] = {}
    objective: en.numeric_expr.NumericExpression | float = 0  # For adding any node objectives

    @property
    def inflow(self) -> str:
        return f"inflow_{self.node_name}"

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if not self.node_name:
            self.node_name = "node_" + str(self.uid)

    def add_port(self, name: str, port: Port) -> None:
        if self.ports.get(name) is None:
            self.ports[name] = port
        else:
            raise ConfigurationError(f"Port with name {name} is already defined on node {self.node_name}")

    def add_ports_from_list(self, names: Iterable[str], port_type: type[Port], **kwargs) -> None:
        """Creates a set of ports (using port_type) and adds them to this Node. The ports will be constructed
        using port_type and the supplied kwargs"""

        for name in names:
            self.add_port(name, port_type(**kwargs))

    def get_port(self, port_name: str) -> Port | None:
        """Returns the Port object with the name port_name.

        Args:
            port_name: The name of the Port.

        Returns:
            Port: The port object with the name port_name, or None if the port isn't found
        """

        return self.ports.get(port_name)

    def num_ports(self) -> int:
        """Returns the number of ports associated with this node.

        Returns:
            The number of ports for this node.
        """
        return len(self.ports)

    def verify_node(self) -> None:
        """Checks there is at least one port associated with this node.

        Raises:
            ConfigurationError: If there are no ports present on this node.
        """

        if len(self.ports) < 1:
            raise ConfigurationError("A node must have at least one port.")

        for port in self.ports.values():
            port.verify_port()

    def add_node_to_model(self, model: EchoConcreteModel, profile: pd.DataFrame) -> None:
        """Add this node to a concrete model.

        Args:
            model: The concrete model to add the node to.
            profile: The data associated with this node.
        """

        self.verify_node()
        for port in self.ports.values():
            port.add_port_to_model(model, profile)

    # @abc.abstractmethod
    def add_objective(self, model: EchoConcreteModel) -> None:
        """Define objective/s and add to self.objective. To be overwritten.

        Should be implemented as an expression that needs to be concatanated to self.objective. For example:

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

        Args:
            model: The model to add the objective/s to.

        Returns:
            None
        """
        pass

    # @abc.abstractmethod
    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        """Apply constraints associated with this node to a concrete model.

        Intended to be overridden in subclasses.

        Define constraints as functions that returns a Constraint, EqualityExpression or InequalityExpression.

        Define a subfunction of the form detailed in the example below, then apply with setattr. For example:

        def apply_node_constraints(self, model: EchoConcreteModel) -> None:
            def tellegen_node_rule(model: EchoConcreteModel, p: int, t:int) -> EqualityExpression:
                a = 0
                for port in node_ports.values():
                    a += getattr(model, port.port_name)[p, t]
                return a == 0

            node_ports = self.ports
            con_name = "reliability_con_" + self.node_name
            setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=tellegen_node_rule))

        Args:
            model: The model to add the constraints to.

        Returns:
            None
        """
        pass

    def get_port_name_to_port_dict_name_map(self) -> dict[str, str]:
        """Map the port name key in self.ports to the corresponding Port.port_name.

        Returns:

        """
        return {port.port_name: port_dict_name for port_dict_name, port in self.ports.items()}
