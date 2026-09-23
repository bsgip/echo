import pytest
from pydantic import ValidationError

from echo.configuration import Units
from echo.models.thermal.base import ThermalNode

positivefloat_values = [(1, None), (0, ValidationError), (-1, ValidationError)]
positivefloat_attributes = ["temp_to_energy_coef"]
positivefloat_data = [
    ({attribute: value}, error) for attribute in positivefloat_attributes for value, error in positivefloat_values
]


nonnegativefloat_values = [(1, None), (0, None), (-1, ValidationError)]
nonnegativefloat_attributes = [
    "loss_factor",
    "gain_factor",
]
nonnegativefloat_data = [
    ({attribute: value}, error) for attribute in nonnegativefloat_attributes for value, error in nonnegativefloat_values
]


@pytest.mark.parametrize("param_to_override, expected_error", [*positivefloat_data, *nonnegativefloat_data])
def test_thermalnode_validation_floats(param_to_override, expected_error):
    required_params = {
        "temp_ub": {},
        "temp_lb": {},
        "external_temp": {},
    }
    params = {**required_params, **param_to_override}
    if expected_error:
        with pytest.raises(expected_error):
            ThermalNode(**params)
    else:
        ThermalNode(**params)


def test_thermalnode_initialisation():
    node_name = "node-name"
    required_params = {
        "temp_ub": {},
        "temp_lb": {},
        "external_temp": {},
    }
    node = ThermalNode(node_name=node_name, **required_params)
    assert node.internal_temp.endswith(node_name)
    assert node.is_gain.endswith(node_name)
    assert node.losses.endswith(node_name)
    assert node.gains.endswith(node_name)
