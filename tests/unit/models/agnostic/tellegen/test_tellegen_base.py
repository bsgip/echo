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


def test_tellegennode_add_ports_from_list_validates_port_units():
    with pytest.raises(ConfigurationError):
        node = TellegenNode()

        # We can add the first three ports (all have same units)
        node.add_ports_from_list(["electrical1", "electical2", "electrical3"], Port, units=Units.KW)
        assert len(node.ports) == 3

        # This fails because we are mixing units
        node.add_ports_from_list(["gas1", "gas2", "gas3"], Port, units=Units.JPS)


def test_tellgennode_verify_node_validates_port_flow_direction():
    # Flows all import not allowed
    with pytest.raises(ConfigurationError):
        node = TellegenNode()
        node.add_ports_from_list(
            ["electrical1", "electical2", "electrical3"],
            Port,
            units=Units.KW,
            flows=Flows.Import,
            import_constraint=FlowConstraint.Fixed,
            import_constraint_value=0,
            flow_type=OptimisationType.Parameter,
        )
        node.verify_node()

    # Flows all export not allowed
    with pytest.raises(ConfigurationError):
        node = TellegenNode()
        node.add_ports_from_list(
            ["electrical1", "electical2", "electrical3"],
            Port,
            units=Units.KW,
            flows=Flows.Export,
            export_constraint=FlowConstraint.Fixed,
            export_constraint_value=0,
            flow_type=OptimisationType.Parameter,
        )
        node.verify_node()
