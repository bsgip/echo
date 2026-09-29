import pytest

from echo.configuration import FlowConstraint, Flows, OptimisationType, Units
from echo.exceptions import ConfigurationError
from echo.models.agnostic.tellegen.base import TellegenNode
from echo.models.base.port import Port


def test_tellegennode_validation():
    # Arrange
    common_port_params = {
        "flows": Flows.Import,
        "import_constraint": FlowConstraint.NoConstraint,
        "flow_type": OptimisationType.Variable,
    }
    electrical_ports = {f"elec_port_{i}": Port(units=Units.KW, **common_port_params) for i in range(3)}
    gas_ports = {f"gas_port_{i}": Port(units=Units.JPS, **common_port_params) for i in range(3)}
    ports = {**electrical_ports, **gas_ports}

    # Act
    with pytest.raises(ConfigurationError):
        TellegenNode(ports=ports)

    with pytest.raises(ConfigurationError):
        node = TellegenNode()
        node.ports = ports

    # This should raise an error due to mixing of different units on ports
    # There is a corresponding [github issue](https://github.com/bsgip/echo/issues/126)
    # with pytest.raises(ConfigurationError):
    #     node = TellegenNode()
    #     node.add_ports_from_list(["electrical1", "electical2", "electrical3"], Port, units=Units.KW)
    #     node.add_ports_from_list(["gas1", "gas2", "gas3"], Port, units=Units.JPS)
