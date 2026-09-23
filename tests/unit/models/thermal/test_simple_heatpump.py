import pytest
from pydantic import ValidationError

from echo.configuration import FlowConstraint, Units
from echo.models.agnostic.flex import FlexPort, FlexSink
from echo.models.thermal import SimpleHeatPump


def test_simple_heatpump(cooling_cop_dict, heating_cop_dict):
    """Test creation and assert default ports."""
    hp = SimpleHeatPump(
        cooling_cop_time_series=cooling_cop_dict,
        heating_cop_time_series=heating_cop_dict,
    )
    assert len(hp.ports) == 2


positivefloat_values = [(1, None), (0, ValidationError), (-1, ValidationError)]
positivefloat_attributes = [
    "max_cooling_capacity",
    "max_heating_capacity",
    "cooling_cop_constant",
    "heating_cop_constant",
]
test_data = [
    ({attribute: value}, error) for attribute in positivefloat_attributes for value, error in positivefloat_values
]


@pytest.mark.parametrize("param_to_override, expected_error", test_data)
def test_simple_heatpump_validation_floats(param_to_override, expected_error):
    required_params = {}
    params = {**required_params, **param_to_override}
    if expected_error:
        with pytest.raises(expected_error):
            SimpleHeatPump(**params)
    else:
        SimpleHeatPump(**params)


def test_simple_heatpump_validation_nonnegative_cop(cooling_cop_dict, heating_cop_dict):
    """Test non negative cop validation error"""
    with pytest.raises(Exception):
        cooling_cop_dict_neg = cooling_cop_dict.copy()
        cooling_cop_dict_neg[(0, 0)] *= -1
        SimpleHeatPump(
            cooling_cop_time_series=cooling_cop_dict_neg,
            heating_cop_time_series=heating_cop_dict,
        )
    with pytest.raises(Exception):
        heating_cop_dict_neg = heating_cop_dict.copy()
        heating_cop_dict_neg[(0, 0)] *= -1
        SimpleHeatPump(
            cooling_cop_time_series=cooling_cop_dict,
            heating_cop_time_series=heating_cop_dict_neg,
        )


@pytest.mark.parametrize(
    "max_cooling_capacity, max_heating_capacity", [(None, None), (1.0, None), (None, 1.0), (1.0, 1.0)]
)
def test_simple_heatpump_initialisation(max_cooling_capacity, max_heating_capacity):
    node = SimpleHeatPump(max_cooling_capacity=max_cooling_capacity, max_heating_capacity=max_heating_capacity)

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
    assert node.ports[ref].import_constraint == FlowConstraint.Fixed if max_cooling_capacity else FlowConstraint.NA
    assert node.ports[ref].import_constraint_value == (max_cooling_capacity if max_cooling_capacity else None)
    assert node.ports[ref].export_constraint == FlowConstraint.Fixed if max_heating_capacity else FlowConstraint.NA
    assert node.ports[ref].export_constraint_value == (-max_heating_capacity if max_heating_capacity else None)
