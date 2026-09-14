import pytest
import numpy as np

from echo.validators import is_non_negative, is_non_positive


@pytest.mark.parametrize(
    "value,should_raise_value_error",
    [
        (-1.0, True),  # floats
        (0.0, False),
        (1.0, False),
        ([1, 2, 49], False),  # lists
        ([1, 2, -49], True),
        ([-1, -2, -49], True),
        ({0, 1.5, 2.7, 150.3}, False),  # sets
        ({0, 1.5, 2.7, -150.3}, True),
        ({0, -1.5, -2.7, -150.3}, True),
        ({0: 0, 1: 1, 2: 2}, False),  # dicts
        ({0: 0, 1: -1, 2: -2}, True),
        (np.array([1, 2, -49]), True),  # numpy arrays
        (np.array([-1, -2, -49]), True),
    ],
)
def test_is_non_negative(value, should_raise_value_error):
    if should_raise_value_error:
        with pytest.raises(ValueError):
            is_non_negative(value, "")
    else:
        is_non_negative(value, "")


@pytest.mark.parametrize(
    "value,should_raise_value_error",
    [
        (-1.0, False),  # floats
        (0.0, False),
        (1.0, True),
        ([-1, -2, -49], False),  # lists
        ([-1, -2, 49], True),
        ([1, 2, 49], True),
        ({0, -1.5, -2.7, -150.3}, False),  # sets
        ({0, -1.5, -2.7, 150.3}, True),
        ({0, 1.5, 2.7, 150.3}, True),
        ({0: 0, 1: -1, 2: -2}, False),  # dicts
        ({0: 0, 1: 1, 2: 2}, True),
        (np.array([-1, -2, 49]), True),  # numpy arrays
        (np.array([1, 2, 49]), True),
    ],
)
def test_is_non_positive(value, should_raise_value_error):
    if should_raise_value_error:
        with pytest.raises(ValueError):
            is_non_positive(value, "")
    else:
        is_non_positive(value, "")
