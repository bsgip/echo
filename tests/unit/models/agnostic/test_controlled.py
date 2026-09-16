import pytest
from pydantic import ValidationError

from echo.models.agnostic.controlled import ControlledGen, ControlledLoad


@pytest.mark.parametrize(
    "min_power,max_power,expected_error",
    [
        (0, 0, None),
        (0, 100, None),
        (100, 0, None),
        (-85, 0, ValidationError),  # min_power -ve
        (0, -15, ValidationError),  # max_power -ve
    ],
)
def test_controlledload_validation(min_power: float, max_power: float, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            ControlledLoad(min_power=min_power, max_power=max_power)
    else:
        ControlledLoad(min_power=min_power, max_power=max_power)


@pytest.mark.parametrize(
    "min_power,max_power,expected_error",
    [
        (0, 0, None),
        (0, -100, None),
        (-100, 0, None),
        (85, 0, ValidationError),  # min_power +ve
        (0, 15, ValidationError),  # max_power +ve
    ],
)
def test_controlledgen_validation(min_power: float, max_power: float, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            ControlledGen(min_power=min_power, max_power=max_power)
    else:
        ControlledGen(min_power=min_power, max_power=max_power)
