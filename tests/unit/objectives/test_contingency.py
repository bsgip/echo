import pytest
from pydantic import ValidationError

from echo.models.base import Path
from echo.objectives.contingency import ContingencyNegative, ContingencyPositive


@pytest.mark.parametrize(
    "duration, expected_error",
    [
        (1.0, None),
        (0.0, ValidationError),  # 0 is not a pydantic PositiveFloat
        (-1.0, ValidationError),  # not a PostiveFloat
    ],
)
def test_contingencypositive_validation(duration, expected_error):
    required_params = {
        "component": Path(vertices=[]),
    }

    if expected_error:
        with pytest.raises(expected_error):
            ContingencyPositive(duration=duration, **required_params)
    else:
        ContingencyPositive(duration=duration, **required_params)


@pytest.mark.parametrize(
    "duration, expected_error",
    [
        (1.0, None),
        (0.0, ValidationError),  # 0 is not a pydantic PositiveFloat
        (-1.0, ValidationError),  # not a PostiveFloat
    ],
)
def test_contingencynegative_validation(duration, expected_error):
    required_params = {
        "component": Path(vertices=[]),
    }

    if expected_error:
        with pytest.raises(expected_error):
            ContingencyNegative(duration=duration, **required_params)
    else:
        ContingencyNegative(duration=duration, **required_params)
