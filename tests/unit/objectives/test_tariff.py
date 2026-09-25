import pyomo.environ as en
import pytest
from pydantic import ValidationError

from echo.exceptions import ConfigurationError
from echo.objectives.tariff import DemandCharge

SHORTUUID_LENGTH = 22


@pytest.mark.parametrize("parameter_to_remove", ["rate", "window_array"])
def test_demandcharge_initialisation_required_params(parameter_to_remove):
    required_params = {
        "rate": 1,
        "window_array": [],
    }
    del required_params[parameter_to_remove]

    with pytest.raises(ValidationError):
        DemandCharge(import_demand=True, **required_params)


@pytest.mark.parametrize("rate,expected_error", [(1, None), (0, None), (-1, ValidationError)])
def test_demandcharge_validation(rate, expected_error):
    required_params = {
        "window_array": [],
        "import_demand": True,
    }

    if expected_error:
        with pytest.raises(ValidationError):
            DemandCharge(rate=rate, **required_params)
    else:
        DemandCharge(rate=rate, **required_params)


@pytest.mark.parametrize(
    "params,expected_values,expected_error",
    [
        ({"window_array": []}, {"num_reset_periods": 1, "reset_periods": [0], "reset_index": en.RangeSet(0, 0)}, None),
        (
            {"window_array": [1, 2, 3]},
            {"num_reset_periods": 1, "reset_periods": [3], "reset_index": en.RangeSet(0, 0)},
            None,
        ),
        (
            {"window_array": [], "reset_periods": []},
            {"num_reset_periods": 0, "reset_periods": [], "reset_index": en.RangeSet(0, -1)},
            None,
        ),  # TODO This passes the validation but probably shouldn't be allowed.
        (
            {"window_array": [1, 2, 3, 4, 5, 6], "reset_periods": [1, 3, 2]},
            {"num_reset_periods": 3, "reset_periods": [1, 3, 2], "reset_index": en.RangeSet(0, 2)},
            None,
        ),
        (
            {"window_array": [1, 2, 3, 4, 5, 6], "reset_periods": [999999]},
            {"num_reset_periods": 1, "reset_periods": [999999], "reset_index": en.RangeSet(0, 0)},
            ConfigurationError,
        ),  # sum(reset_periods) != len(window_array) i.e 999999 != 6
    ],
)
def test_demandcharge_validation_check_reset_periods(params, expected_values, expected_error):
    required_params = {
        "rate": 1,
        "import_demand": True,
    }
    if expected_error:
        with pytest.raises(expected_error):
            DemandCharge(**required_params, **params)
    else:
        dc = DemandCharge(**required_params, **params)
        assert dc.num_reset_periods == expected_values["num_reset_periods"]
        assert dc.reset_periods == expected_values["reset_periods"]
        assert dc.reset_index == expected_values["reset_index"]


@pytest.mark.parametrize(
    "import_demand,export_demand,expected_error",
    [(True, True, None), (True, False, None), (False, True, None), (False, False, ConfigurationError)],
)
def test_demandcharge_validation_check_import_or_export(import_demand, export_demand, expected_error):
    required_params = {
        "rate": 1,
        "window_array": [],
    }

    if expected_error:
        with pytest.raises(expected_error):
            DemandCharge(import_demand=import_demand, export_demand=export_demand, **required_params)
    else:
        DemandCharge(import_demand=import_demand, export_demand=export_demand, **required_params)


@pytest.mark.parametrize(
    "override_params,expected_uid,expected_name",
    [
        ({"uid": "1234", "name": "demand-charge"}, "1234", "demand-charge"),
        ({"name": "demand-charge"}, None, "demand-charge"),
        ({"uid": "1234"}, "1234", None),
        ({}, None, None),
    ],
)
def test_demandcharge_validation_set_uid_and_name(override_params, expected_uid, expected_name):
    required_params = {
        "name": None,
        "rate": 1,
        "window_array": [],
        "import_demand": True,
    }
    params = {**required_params, **override_params}

    dc = DemandCharge(**params)

    if expected_uid:
        assert dc.uid == expected_uid
    else:
        assert len(dc.uid) == SHORTUUID_LENGTH
    if expected_name:
        assert dc.name == expected_name
    else:
        assert dc.name.endswith(dc.uid)
