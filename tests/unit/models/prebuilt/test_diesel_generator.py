import pytest
from pydantic import ValidationError

from echo.models.prebuilt.diesel_generator import DieselGenerator

nonnegativefloat_values = [(1, None), (0, None), (-1, ValidationError)]
nonnegativefloat_attributes = [
    "cop",
    "startup_efficiency",
    "C02Intensity",
]
test_data = [
    ({attribute: value}, error) for attribute in nonnegativefloat_attributes for value, error in nonnegativefloat_values
]


@pytest.mark.parametrize("params, expected_error", test_data)
def test_diesel_generator_validation(params, expected_error):
    required_params = {
        "min_output": -1.5,
        "max_output": -5,
    }
    if expected_error:
        with pytest.raises(expected_error):
            DieselGenerator(**params, **required_params)
    else:
        DieselGenerator(**params, **required_params)


def test_diesel_generator_initialisation():
    required_params = {
        "min_output": -1.5,
        "max_output": -5,
    }
    node = DieselGenerator(**required_params)

    assert len(node.ports) == 3
