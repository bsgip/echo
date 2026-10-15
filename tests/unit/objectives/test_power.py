import pytest

from echo.models.agnostic.storage import Storage
from echo.objectives.power import FinalChargeObjective, NotFullyChargedPenalty


@pytest.mark.parametrize(
    "rate, expected_error",
    [
        (1.0, None),
        (0.0, ValueError),  # 0 is not a pydantic PositiveFloat
        (-1.0, ValueError),  # not a PostiveFloat
    ],
)
def test_notfullychargepenalty_validation(rate, expected_error):
    required_params = {
        "component": Storage(max_capacity=0, charging_power_limit=0, discharging_power_limit=0),
        "rate_array": [],
    }

    if expected_error:
        with pytest.raises(expected_error):
            NotFullyChargedPenalty(rate=rate, **required_params)
    else:
        NotFullyChargedPenalty(rate=rate, **required_params)


@pytest.mark.parametrize(
    "rate, expected_error",
    [
        (1.0, None),
        (0.0, ValueError),  # 0 is not a pydantic PositiveFloat
        (-1.0, ValueError),  # not a PostiveFloat
    ],
)
def test_finalchargeobjective_validation(rate, expected_error):
    required_params = {
        "component": Storage(max_capacity=0, charging_power_limit=0, discharging_power_limit=0),
    }

    if expected_error:
        with pytest.raises(expected_error):
            FinalChargeObjective(rate=rate, **required_params)
    else:
        FinalChargeObjective(rate=rate, **required_params)
