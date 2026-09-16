import pytest
from pydantic import ValidationError

from echo.exceptions import ConfigurationError
from echo.models.agnostic.storage import MobileStorage, Storage


@pytest.mark.parametrize(
    "storage_params",
    [
        {"max_capacity": 0, "charging_power_limit": 0},  # missing discharging_power_limit
        {"max_capacity": 0, "discharging_power_limit": 0},  # missing charging_power_limit
        {"charging_power_limit": 0, "discharging_power_limit": 0},  # missing max_capacity
    ],
)
def test_storage_validation_missing_fields(storage_params):
    with pytest.raises(ValidationError):
        Storage(**storage_params)


@pytest.mark.parametrize(
    "storage_capacity_cost, expected_error",
    [
        (5.0, None),
        (0.0, ValidationError),  # 0 is not a pydantic PositiveFloat
        (-7.0, ValidationError),  # not a PostiveFloat
    ],
)
def test_storage_validation_storage_capactity_cost(
    storage_capacity_cost: float, expected_error: ValidationError | None
):
    storage_params = {"max_capacity": 0, "charging_power_limit": 0, "discharging_power_limit": 0}
    if expected_error:
        with pytest.raises(ValidationError):
            Storage(storage_capacity_cost=storage_capacity_cost, **storage_params)
    else:
        Storage(storage_capacity_cost=storage_capacity_cost, **storage_params)


@pytest.mark.parametrize(
    "storage_params, expected_error",
    [
        ({"depth_of_discharge_limit": 0.5}, None),
        ({"depth_of_discharge_limit": -0.5}, ValidationError),  # Dod can't be negative
        ({"depth_of_discharge_limit": 110}, ValidationError),  # DoD can't be > 100%
    ],
)
def test_storage_validation_depth_of_discharge_check(storage_params, expected_error):
    common_storage_params = {"max_capacity": 0, "charging_power_limit": 0, "discharging_power_limit": 0}
    if expected_error:
        with pytest.raises(ValidationError):
            Storage(**common_storage_params, **storage_params)
    else:
        Storage(**common_storage_params, **storage_params)


# NOTE: This test is fails due to a bug that needs to be resolved.
# Details on the bug can be found here: https://github.com/bsgip/echo/issues/124
#
# @pytest.mark.parametrize(
#     "initial_state_of_charge, expected_error",
#     [
#         (50, None),  # initial soc = min soc
#         (75, None),  # min soc < initial soc < max capacity
#         (100, None),  # initital soc = max capacity
#         (0, ValidationError),  # initial soc < min soc
#         (25, ValidationError),  # initial soc < min soc
#         (101, ValidationError),  # initial soc > max capacity
#     ],
# )
# def test_storage_validation_initial_state_of_charge_check(initial_state_of_charge, expected_error):
#     # min_capacity = max_capacity * depth_of_discharge_limit = 50
#     storage_params = {
#         "max_capacity": 100,
#         "depth_of_discharge_limit": 0.5,
#         "charging_power_limit": 0,
#         "discharging_power_limit": 0,
#         # (see function dod_checks)
#     }
#     if expected_error:
#         with pytest.raises(ValidationError):
#             Storage(initial_state_of_charge=initial_state_of_charge, **storage_params)
#     else:
#         Storage(initial_state_of_charge=initial_state_of_charge, **storage_params)


@pytest.mark.parametrize(
    "conserv_params, expected_error",
    [
        ({"soc_conserv": None}, None),  # when soc_conserv is None no validation is triggered
        ({"soc_conserv": 0, "soc_conserv_cost": None, "available": []}, ConfigurationError),  # soc_conserv_cost is None
        ({"soc_conserv": 0, "soc_conserv_cost": 0, "available": None}, ConfigurationError),  # available is None
    ],
)
def test_mobile_storage_validation(conserv_params, expected_error):
    storage_params = {"max_capacity": 0, "charging_power_limit": 0, "discharging_power_limit": 0}

    if expected_error:
        with pytest.raises(expected_error):
            MobileStorage(**conserv_params, **storage_params)
    else:
        MobileStorage(**conserv_params, **storage_params)
