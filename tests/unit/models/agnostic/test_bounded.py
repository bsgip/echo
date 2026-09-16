import pytest
from pydantic import ValidationError

from echo.models.agnostic.bounded import BoundedLoad, BoundedPort


@pytest.mark.parametrize(
    "lower_bound,upper_bound,expected_error",
    [
        (0, 100, None),
        (0.1, 0.2, None),
        (100, 0, ValidationError),  # lower bound > upper bound
        (50, 50, ValidationError),  # lower bound == upper bound
    ],
)
def test_boundedport_validation(lower_bound: float, upper_bound: float, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            BoundedPort(lower_bound=lower_bound, upper_bound=upper_bound)
    else:
        BoundedPort(lower_bound=lower_bound, upper_bound=upper_bound)


@pytest.mark.parametrize(
    "lower_bound,upper_bound,expected_error",
    [
        (0, 100, None),
        (0.1, 0.2, None),
        (100, 0, ValidationError),  # lower bound > upper bound
        (50, 50, ValidationError),  # lower bound == upper bound
        (-100, 100, ValidationError),  # lower bound -ve
        (-100, -50, ValidationError),  # both bounds -ve
    ],
)
def test_boundedload_validation(lower_bound: float, upper_bound: float, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            BoundedLoad(lower_bound=lower_bound, upper_bound=upper_bound)
    else:
        BoundedLoad(lower_bound=lower_bound, upper_bound=upper_bound)
