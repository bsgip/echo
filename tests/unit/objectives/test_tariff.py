from datetime import time

import pyomo.environ as en
import pytest
from pydantic import ValidationError

from echo.exceptions import ConfigurationError
from echo.models.base.port import Port
from echo.objectives.tariff import (
    BlockTariff,
    Day,
    DemandCharge,
    DemandTariffObjective,
    ExportDemandCharge,
    ImportDemandCharge,
    Tariff,
    ThroughputCost,
    TimePeriod,
    Window,
)

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
        with pytest.raises(expected_error):
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


@pytest.mark.parametrize("min_demand,expected_error", [(1, None), (0, None), (-1, ValidationError)])
def test_importdemandcharge_validation(min_demand, expected_error):
    required_params = {
        "rate": 1,
        "window_array": [],
    }

    if expected_error:
        with pytest.raises(expected_error):
            ImportDemandCharge(min_demand=min_demand, **required_params)
    else:
        ImportDemandCharge(min_demand=min_demand, **required_params)


@pytest.mark.parametrize("min_demand,expected_error", [(-1, None), (0, None), (1, ValidationError)])
def test_exportdemandcharge_validation(min_demand, expected_error):
    required_params = {
        "rate": 1,
        "window_array": [],
    }

    if expected_error:
        with pytest.raises(expected_error):
            ExportDemandCharge(min_demand=min_demand, **required_params)
    else:
        ExportDemandCharge(min_demand=min_demand, **required_params)


@pytest.mark.parametrize(
    "time_periods,expected_error",
    [
        (
            [
                TimePeriod(start_time=time(0, 0), end_time=time(14, 0), day_type=[Day.weekday]),
                TimePeriod(start_time=time(18, 0), end_time=time(23, 59), day_type=[Day.weekday]),
            ],
            None,
        ),  # no overlap
        (
            [
                TimePeriod(start_time=time(0, 0), end_time=time(18, 0), day_type=[Day.weekday]),
                TimePeriod(start_time=time(18, 0), end_time=time(23, 59), day_type=[Day.weekday]),
            ],
            None,
        ),  # no overlap
        (
            [
                TimePeriod(start_time=time(0, 0), end_time=time(19, 0), day_type=[Day.weekday]),
                TimePeriod(start_time=time(18, 0), end_time=time(23, 59), day_type=[Day.weekday]),
            ],
            ValidationError,
        ),  # 1 hour overlap
        (
            [
                TimePeriod(start_time=time(0, 0), end_time=time(19, 0), day_type=[Day.weekday, Day.holiday]),
                TimePeriod(start_time=time(18, 0), end_time=time(23, 59), day_type=[Day.holiday]),
            ],
            ValidationError,
        ),  # 1 hour overlap on holidays
    ],
)
def test_window_validation_non_overlapping_periods(time_periods, expected_error):

    if expected_error:
        with pytest.raises(expected_error):
            Window(time_periods=time_periods)
    else:
        Window(time_periods=time_periods)


@pytest.mark.parametrize(
    "expansion_periods, expected_error",
    [
        (1, None),
        (0, ValidationError),  # 0 is not a pydantic PositiveFloat
        (-1, ValidationError),  # not a PostiveFloat
        (-1.0, ValidationError),  # not an int
        (0.0, ValidationError),  # not an int
        (-1.0, ValidationError),  # not an int
    ],
)
def test_demandtariffobjective_validation(expansion_periods, expected_error):
    required_params = {"component": Port(), "demand_charges": []}

    if expected_error:
        with pytest.raises(expected_error):
            DemandTariffObjective(expansion_periods=expansion_periods, **required_params)
    else:
        DemandTariffObjective(expansion_periods=expansion_periods, **required_params)


@pytest.mark.parametrize(
    "rate, expected_error",
    [
        (1.0, None),
        (0.0, ValidationError),  # 0 is not a pydantic PositiveFloat
        (-1.0, ValidationError),  # not a PostiveFloat
    ],
)
def test_throughputcost_validation(rate, expected_error):
    required_params = {"component": Port(), "demand_charges": []}

    if expected_error:
        with pytest.raises(expected_error):
            ThroughputCost(rate=rate, **required_params)
    else:
        ThroughputCost(rate=rate, **required_params)


@pytest.mark.parametrize(
    "expansion_periods, expected_error",
    [
        (1, None),
        (0, ValidationError),  # 0 is not a pydantic PositiveFloat
        (-1, ValidationError),  # not a PostiveFloat
        (-1.0, ValidationError),  # not an int
        (0.0, ValidationError),  # not an int
        (-1.0, ValidationError),  # not an int
    ],
)
def test_tariff_validation(expansion_periods, expected_error):
    required_params = {"tariff_array": []}

    if expected_error:
        with pytest.raises(expected_error):
            Tariff(expansion_periods=expansion_periods, **required_params)
    else:
        Tariff(expansion_periods=expansion_periods, **required_params)


@pytest.mark.parametrize(
    "blocks,rates,expected_error",
    [
        ([], [1], None),
        ([], [], ConfigurationError),  # rates should be 1 larger than blocks
        ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6], None),
        ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], ConfigurationError),  # rates should be 1 larger than blocks
    ],
)
def test_blocktariff_validation_check_block_rates(blocks, rates, expected_error):
    if expected_error:
        with pytest.raises(expected_error):
            BlockTariff(component=Port(), blocks=blocks, rates=rates)
    else:
        BlockTariff(component=Port(), blocks=blocks, rates=rates)


@pytest.mark.parametrize(
    "reset_periods,expected_reset_index",
    [
        ([], en.RangeSet(0, -1)),  # TODO this passes but a negative index is probably not correct
        (list(range(1)), en.RangeSet(0, 1 - 1)),
        (list(range(157)), en.RangeSet(0, 157 - 1)),
    ],
)
def test_blocktariff_validation_set_reset_index(reset_periods, expected_reset_index):
    required_params = {
        "component": Port(),
        "blocks": [],
        "rates": [1],
    }
    bt = BlockTariff(reset_periods=reset_periods, **required_params)

    assert bt.reset_index == expected_reset_index
