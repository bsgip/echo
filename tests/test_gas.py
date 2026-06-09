
from echo.configuration import FlowConstraint, Flows, OptimisationType, Units
from echo.models.gas import FixedGasPort, FlexGasPort


def test_build_flex_gas_port():
    "Test FlexGasPort instantiation and defaults."
    flex_gas_port = FlexGasPort(port_name="flexible_gas_port")

    assert flex_gas_port.port_name == "flexible_gas_port"
    assert flex_gas_port.units == Units.JPS
    assert flex_gas_port.flows == Flows.Both
    assert flex_gas_port.import_constraint == FlowConstraint.NoConstraint
    assert flex_gas_port.export_constraint == FlowConstraint.NoConstraint
    assert flex_gas_port.flow_type == OptimisationType.Variable


def test_fixed_gas_port():
    """Test FixedGasPort instantiation and defaults."""

    fixed_gas_port = FixedGasPort(port_name="fixed_gas_port")

    assert fixed_gas_port.units == Units.JPS
    assert fixed_gas_port.flows == Flows.Both
    assert fixed_gas_port.import_constraint == FlowConstraint.NoConstraint
    assert fixed_gas_port.export_constraint == FlowConstraint.NoConstraint
    assert fixed_gas_port.flow_type == OptimisationType.Parameter
