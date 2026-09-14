import pytest
from pydantic import ValidationError

from echo.models.agnostic.base import Source


@pytest.mark.parametrize(
    "initial_value, expected_error",
    [
        ([-5.0], None),
        ([-0.0001], None),
        ([-42.0, -12.0], None),
        ([-15], None),
        ([0.0], None),
        ([5.0], ValidationError),
        ([42.0, -12.0], ValidationError),
        ([15], ValidationError),
    ],
)
def test_source_port_validation(initial_value, expected_error):
    initial_values_as_dict = {(0, i): v for i, v in enumerate(initial_value)}
    if expected_error:
        with pytest.raises(expected_error):
            Source(initial_value=initial_values_as_dict)
    else:
        Source(initial_value=initial_values_as_dict)


@pytest.mark.parametrize(
    "initial_value, expected_error",
    [
        ([-5.0], None),
        ([-0.0001], None),
        ([-42.0, -12.0], None),
        ([-15], None),
        ([0.0], None),
        ([5.0], ValidationError),
        ([42.0, -12.0], ValidationError),
        ([15], ValidationError),
    ],
)
def test_source_port_process_initial_value_performs_validation(initial_value, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            port = Source()
            port.process_initial_value(initial_value, time_periods=len(initial_value))

    else:
        port = Source()
        port.process_initial_value(initial_value, time_periods=len(initial_value))
