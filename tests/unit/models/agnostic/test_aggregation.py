import pytest

from echo.configuration import Units
from echo.exceptions import ConfigurationError
from echo.models.agnostic.aggregation import AggregationNode
from echo.models.agnostic.flex import FlexSink
from echo.models.base.port import Port


@pytest.mark.parametrize(
    "raw_ports, expected_error",
    [
        ([FlexSink(units=Units.KW), FlexSink(units=Units.KW)], None),  # ports compatible
        (
            [FlexSink(units=Units.KW), FlexSink(units=Units.JPS)],
            ConfigurationError,
        ),  # Units.JPS mismatch with port_units of Units.KW
        (
            [Port(units=Units.KW), Port(units=Units.KW)],
            None,
        ),  # ports compatible but AggregationNode should accept *only* FlexSink ports TODO: Fix
    ],
)
def test_aggregation_validation(raw_ports, expected_error):
    ports = {f"port_{i}": port for i, port in enumerate(raw_ports)}
    if expected_error:
        with pytest.raises(expected_error):
            AggregationNode(port_units=Units.KW, ports=ports)
    else:
        AggregationNode(port_units=Units.KW, ports=ports)


def test_aggregation_add_port():
    port_name = "new-port"
    node = AggregationNode(port_units=Units.KW)
    node.add_port(name=port_name)
    assert port_name in node.ports
    assert all([p.units == node.port_units for p in node.ports.values()])


def test_aggregation_add_port_supplied():
    units = Units.JPS
    port_name = "new-port"
    port = FlexSink(port_name=port_name, units=units)
    node = AggregationNode(port_units=units)
    node.add_port(name=port.port_name, port=port)
    assert port_name in node.ports
    assert port in node.ports.values()
    assert all([p.units == node.port_units for p in node.ports.values()])
