import pytest
from pydantic import ValidationError

from echo.exceptions import ConfigurationError
from echo.models.gas.boiler_fixedcop import GasBoilerFixedCOP

nonnegativefloat_values = [(1, None), (0, None), (-1, ValidationError)]


@pytest.mark.parametrize(
    "override_params, expected_error",
    [
        ({"startup_cop": 0.5, "cop": 1}, None),
        ({"startup_cop": 0, "cop": 1}, None),
        ({"startup_cop": -0.5, "cop": 1}, ValidationError),
        ({"startup_cop": -0.5, "cop": -0.1}, ValidationError),
        ({"startup_cop": 1, "cop": 0.5}, ConfigurationError),
    ],
)
def test_boiler_fixedcop_validation(override_params, expected_error):
    required_params = {"min_input": 1.5, "max_input": 5}
    params = {**required_params, **override_params}
    if expected_error:
        with pytest.raises(expected_error):
            GasBoilerFixedCOP(**params)
    else:
        GasBoilerFixedCOP(**params)


def test_boiler_fixedcop_initialisation():
    required_params = {"min_input": 1.5, "max_input": 5, "cop": 1, "startup_cop": 1}
    node = GasBoilerFixedCOP(**required_params)

    assert len(node.ports) == 2
    assert node.max_output is not None
    assert node.min_output is not None
