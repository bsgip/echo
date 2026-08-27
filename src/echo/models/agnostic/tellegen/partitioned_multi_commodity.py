from collections.abc import Iterable
from functools import partial

import pyomo.environ as en
from pydantic import Field, root_validator
from pyomo.core.expr import EqualityExpression

from echo.exceptions import ConfigurationError
from echo.models.base import Node, Port
from echo.models.scenario import EchoConcreteModel
from echo.validators import (
    validate_partition_ports,
)


class PartitionedMultiCommodityTellegenNode(Node):
    """
    A node with partitions of ports, ports in each partition may have multiple commodities.
    A tellegen constraint is applied per partition per commodity.
    """

    partitions: dict[str, list[Port]] = Field(default_factory=dict)
    default_partition: str = "default_partition"

    partition_port_uniqueness_check = root_validator(allow_reuse=True)(validate_partition_ports)

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if len(self.ports):
            if len(self.partitions):
                raise ValueError(
                    "Expect user to define either ports dictionary or partitions dictionary, "
                    "but not both on an instance of PartitionedMultiCommodityTellegenNode."
                    f"Offending instance {self.node_name}"
                )
            else:
                # If user defined ports but not partitions, assign all ports to a default partition
                self.partitions = {self.default_partition: list(self.ports.values())}
        else:
            self.ports = {_p.port_name: _p for port_set in self.partitions.values() for _p in port_set}

    def add_port(self, name: str, port: Port, partition: str | None = None) -> None:
        """Override base add_port method, add addition argument which is partition name to which add the port.

        If partition is not specified, adds to the default partition.
        """
        if partition is None:
            partition = self.default_partition
        if self.ports.get(name) is None:
            self.ports[name] = port
            if not self.partitions.get(partition):
                """If partition with this name does not exist in the partition dictionary, add new item."""
                self.partitions[partition] = [port]
            else:
                self.partitions[partition].append(port)
        else:
            raise ConfigurationError(f"Port with name {name} is already defined on node {self.node_name}")

    def apply_node_constraints(self, model: EchoConcreteModel) -> None:
        """Apply Tellegen constraint for same commodity ports within each partition."""

        def tellegen_node_rule(
            partition_ports: Iterable[Port],
            model: EchoConcreteModel,
            p: int,
            t: int,
        ) -> EqualityExpression:
            net_flow = 0
            for port in partition_ports:
                port_flow = getattr(model, port.port_name)
                net_flow += port_flow[p, t]
            return net_flow == 0

        partition_commodities = dict()
        for _partition, _ports in self.partitions.items():
            for p in _ports:
                _key = (_partition, p.units)
                if partition_commodities.get(_key) is None:
                    partition_commodities[_key] = [p]
                else:
                    partition_commodities[_key].append(p)

        for partition_commodity_type, partition_ports in partition_commodities.items():
            setattr(
                model,
                "node_con_" + str(partition_commodity_type) + self.node_name,
                en.Constraint(
                    model.Expansion,
                    model.Time,
                    rule=partial(tellegen_node_rule, partition_ports),
                ),
            )
