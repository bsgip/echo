import pytest
from pydantic import ValidationError

from echo.models.agnostic.flex import OffOrConstrainedPort


@pytest.mark.parametrize(
    "lower_bound,upper_bound,expected_error",
    [
        (0, 100, None),
        (0.1, 0.2, None),
        (100, 0, ValidationError),  # lower bound > upper bound
        (50, 50, ValidationError),  # lower bound == upper bound
    ],
)
def test_offorconstrainedport_validation(lower_bound: float, upper_bound: float, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            OffOrConstrainedPort(lower_bound=lower_bound, upper_bound=upper_bound)
    else:
        OffOrConstrainedPort(lower_bound=lower_bound, upper_bound=upper_bound)
