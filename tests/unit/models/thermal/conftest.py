import pytest

from echo.utils import TimeSeriesData, expand_as_dict


@pytest.fixture
def cooling_cop_dict():
    raw_cops = [2, 3, 1, 2, 2.5]
    return expand_as_dict(
        TimeSeriesData(
            value=raw_cops,
            num_time_intervals=len(raw_cops),
            num_expansion_intervals=1,
        )
    )


@pytest.fixture
def heating_cop_dict():
    raw_cops = [4, 3, 5, 2, 2.5]
    return expand_as_dict(
        TimeSeriesData(
            value=raw_cops,
            num_time_intervals=len(raw_cops),
            num_expansion_intervals=1,
        )
    )
