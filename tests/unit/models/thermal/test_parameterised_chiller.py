import pytest
from pydantic import ValidationError

from echo.models.thermal import ParameterisedChiller


@pytest.mark.parametrize(
    "nominal_cop, max_cooling_capacity, expected_error",
    [
        (1, 1, None),
        (0, 1, ValidationError),  # nominal cop 0
        (1, 0, ValidationError),  # max_cooling_capacity 0
        (-0.5, 1, ValidationError),  # nominal cop -ve
        (1, -0.5, ValidationError),  # max_cooling_capacity -ve
    ],
)
def test_parameterisedchiller_validation(nominal_cop, max_cooling_capacity, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            ParameterisedChiller(nominal_cop=nominal_cop, max_cooling_capacity=max_cooling_capacity)
    else:
        ParameterisedChiller(nominal_cop=nominal_cop, max_cooling_capacity=max_cooling_capacity)


def test_parameterisedchiller_initialisation():
    required_params = {
        "nominal_cop": 1,
        "max_cooling_capacity": 1,
    }

    node = ParameterisedChiller(**required_params)
    assert len(node.ports) == 2

    node = ParameterisedChiller(heat_rejection_port=True, **required_params)
    assert len(node.ports) == 3
