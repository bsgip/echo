import pytest
from pydantic import ValidationError

from echo.exceptions import ConfigurationError
from echo.models.gas.boiler_tempcontrolled import TempControlledBoiler

nonnegativefloat_values = [(1, None), (0, None), (-1, ValidationError)]


@pytest.mark.parametrize(
    "override_params, expected_error",
    [
        ({"startup_cop": 0.5, "cop": 1}, None),
        ({"startup_cop": 0, "cop": 1}, None),
        ({"startup_cop": 1, "cop": 0.5}, ConfigurationError),
    ],
)
def test_boiler_fixedcop_validation(override_params, expected_error):
    required_params = {"min_input": 1.5, "max_input": 5, "deg_to_kw": 1}
    params = {**required_params, **override_params}
    if expected_error:
        with pytest.raises(expected_error):
            TempControlledBoiler(**params)
    else:
        TempControlledBoiler(**params)


def test_boiler_fixedcop_initialisation():
    required_params = {"min_input": 1.5, "max_input": 5, "cop": 1, "startup_cop": 1, "deg_to_kw": 1}
    node = TempControlledBoiler(**required_params)

    assert len(node.ports) == 2
    assert node.max_output is not None
    assert node.min_output is not None
    assert node.return_t.endswith(node.node_name)
    assert node.exit_t.endswith(node.node_name)
