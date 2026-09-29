import pytest

from echo.models.electrical.ev import EVBase


@pytest.mark.parametrize(
    "params,expected_usage_power_limit",
    [({"usage_power_limit": 0.5, "discharging_power_limit": 0.9}, 0.5), ({"discharging_power_limit": 0.9}, 0.9)],
)
def test_evbase_initialisation(params, expected_usage_power_limit):
    required_params = {
        "max_capacity": 1,
        "charging_power_limit": 1,
    }
    ev = EVBase(**params, **required_params)
    assert ev.usage_power_limit == expected_usage_power_limit
