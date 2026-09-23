import pytest
from pydantic import ValidationError

from echo.configuration import Units
from echo.models.agnostic.flex import FlexPort, FlexSink
from echo.models.thermal.parameterised_heatpump import ParameterisedHeatPump

values = [(1, None), (0, ValidationError), (-1, ValidationError)]
positivefloat_attributes = [
    "nominal_heating_cop",
    "nominal_cooling_cop",
    "max_heating_capacity",
    "max_cooling_capacity",
    "heat_intake_rejection_coefficient",
]
test_data = [({attribute: value}, error) for attribute in positivefloat_attributes for value, error in values]


@pytest.mark.parametrize("param_to_override, expected_error", test_data)
def test_heatpump_validation_heat_intake_rejection_coefficient(param_to_override, expected_error):
    required_params = {
        "nominal_heating_cop": 1,
        "nominal_cooling_cop": 1,
        "max_heating_capacity": 1,
        "max_cooling_capacity": 1,
    }
    params = {**required_params, **param_to_override}
    if expected_error:
        with pytest.raises(expected_error):
            ParameterisedHeatPump(**params)
    else:
        ParameterisedHeatPump(**params)


@pytest.mark.parametrize("heat_intake_rejection_port", [False, True])
def test_heatpump_initialisation(heat_intake_rejection_port: bool):
    required_params = {
        "nominal_heating_cop": 1,
        "nominal_cooling_cop": 1,
        "max_heating_capacity": 1,
        "max_cooling_capacity": 1,
    }
    node = ParameterisedHeatPump(heat_intake_rejection_port=heat_intake_rejection_port, **required_params)

    num_ports = 3 if heat_intake_rejection_port else 2
    assert len(node.ports) == num_ports

    # electrical input port
    ref = node.electrical_input_port_ref
    assert ref in node.ports
    assert isinstance(node.ports[ref], FlexSink)
    assert node.ports[ref].units == Units.KW

    # thermal output port
    ref = node.thermal_output_port_ref
    assert ref in node.ports
    assert isinstance(node.ports[ref], FlexPort)
    assert node.ports[ref].units == Units.KWT

    # optional heat rejection port
    if heat_intake_rejection_port:
        ref = node.heat_intake_rejection_port_ref
        assert ref in node.ports
        assert isinstance(node.ports[ref], FlexPort)
        assert node.ports[ref].units == Units.KWT
