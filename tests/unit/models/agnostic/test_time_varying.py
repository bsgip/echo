import pytest

from echo.configuration import Units
from echo.exceptions import ConfigurationError
from echo.models.agnostic.time_varying import TimeVaryingPiecewiseIONode


def test_timevarying_node():
    # Synthesise `input_points` and `output_points` dicts
    MAX_VALUE = 10
    MIN_VALUE = 5
    TIME_PERIODS = 6
    points = {(0, i): list(range(MIN_VALUE, MAX_VALUE + 1)) for i in range(TIME_PERIODS)}

    required_params = {
        "input_port_unit": Units.KW,
        "output_port_unit": Units.KW,
    }

    node = TimeVaryingPiecewiseIONode(
        input_points=points,
        output_points=points,
        **required_params,
    )
    # Verify bounds set correctly
    assert node.min_input == MIN_VALUE
    assert node.max_input == MAX_VALUE
    assert node.min_output == MIN_VALUE
    assert node.max_output == MAX_VALUE


@pytest.mark.parametrize(
    "min_input, max_input, input_periods, min_output, max_output, output_periods, expected_error",
    [
        (5, 10, 6, 5, 10, 6, None),
        (5, 10, 6, 5, 10, 7, ConfigurationError),  # time periods not equal (6 != 7)
        (5, 8, 6, 5, 10, 6, ConfigurationError),  # input value range (5 to 8) < output value range (5 to 10)
    ],
)
def test_timevarying_node_validation_piecewise_arrays(
    min_input,
    max_input,
    input_periods,
    min_output,
    max_output,
    output_periods,
    expected_error,
):
    required_params = {
        "input_port_unit": Units.KW,
        "output_port_unit": Units.KW,
    }

    input_points = {(0, i): list(range(min_input, max_input + 1)) for i in range(input_periods)}
    output_points = {(0, i): list(range(min_output, max_output + 1)) for i in range(output_periods)}

    if expected_error:
        with pytest.raises(expected_error):
            TimeVaryingPiecewiseIONode(
                input_points=input_points,
                output_points=output_points,
                **required_params,
            )
    else:
        TimeVaryingPiecewiseIONode(
            input_points=input_points,
            output_points=output_points,
            **required_params,
        )
