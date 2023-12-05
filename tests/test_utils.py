import pytest

from echo.utils import TimeSeriesData, expand, expand_as_dict


@pytest.mark.parametrize(
    "array,time_periods,expansion_periods,expected",
    [
        (range(5), 5, 1, {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4}),  # array with no expansion periods
        (range(4), 4, 1, {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3}),  # smaller array with no expansion periods
        (42, 5, 1, {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42}),  # scalar with no expansion periods
        (
            [42],
            5,
            1,
            {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42},
        ),  # "wrapped" scalar with no expansion periods
        (
            range(5),
            5,
            2,
            {
                (0, 0): 0,
                (0, 1): 1,
                (0, 2): 2,
                (0, 3): 3,
                (0, 4): 4,
                (1, 0): 0,
                (1, 1): 1,
                (1, 2): 2,
                (1, 3): 3,
                (1, 4): 4,
            },
        ),  # array with 2 expansion periods
        (
            [range(5), range(5)],
            5,
            2,
            {
                (0, 0): 0,
                (0, 1): 1,
                (0, 2): 2,
                (0, 3): 3,
                (0, 4): 4,
                (1, 0): 0,
                (1, 1): 1,
                (1, 2): 2,
                (1, 3): 3,
                (1, 4): 4,
            },
        ),  # 2d list and 2 expansion periods [[time period for first expansion],[time period for second expansion]]
    ],
)
def test_expand(array, time_periods, expansion_periods, expected):
    result = expand(array=array, time_periods=time_periods, expansion_periods=expansion_periods)

    # Assert
    assert result == expected


@pytest.mark.parametrize(
    "array,time_periods,expansion_periods,expected",
    [
        (range(4), 5, 1, {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3}),  # time periods bigger than array
        (range(4), 3, 1, {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3}),  # time periods smaller than array
    ],
)
def test_expand_should_raise_exception(array, time_periods, expansion_periods, expected):
    with pytest.raises(Exception):
        expand(array=array, time_periods=time_periods, expansion_periods=expansion_periods)


@pytest.mark.parametrize(
    "timeseriesdata,expected",
    [
        (
            TimeSeriesData(value=range(5), num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4},
        ),  # array with no expansion periods
        (
            TimeSeriesData(value=range(4), num_time_intervals=4, num_expansion_intervals=1),
            {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3},
        ),  # smaller array with no expansion periods
        (
            TimeSeriesData(value=42, num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42},
        ),  # scalar with no expansion periods
        (
            TimeSeriesData(value=[42], num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42},
        ),  # "wrapped" scalar with no expansion periods
        (
            TimeSeriesData(value=range(5), num_time_intervals=5, num_expansion_intervals=2),
            {
                (0, 0): 0,
                (0, 1): 1,
                (0, 2): 2,
                (0, 3): 3,
                (0, 4): 4,
                (1, 0): 0,
                (1, 1): 1,
                (1, 2): 2,
                (1, 3): 3,
                (1, 4): 4,
            },
        ),  # array with 2 expansion periods
        (
            TimeSeriesData(value=[range(5), range(5)], num_time_intervals=5, num_expansion_intervals=2),
            {
                (0, 0): 0,
                (0, 1): 1,
                (0, 2): 2,
                (0, 3): 3,
                (0, 4): 4,
                (1, 0): 0,
                (1, 1): 1,
                (1, 2): 2,
                (1, 3): 3,
                (1, 4): 4,
            },
        ),  # 2d list and 2 expansion periods [[time period for first expansion],[time period for second expansion]]
    ],
)
def test_expand_as_dict(timeseriesdata, expected):
    assert expand_as_dict(data=timeseriesdata) == expected


@pytest.mark.parametrize(
    "timeseriesdata",
    [
        (
            TimeSeriesData(value=range(4), num_time_intervals=5, num_expansion_intervals=1),
        ),  # number of time intervals bigger than array
        (
            TimeSeriesData(value=range(4), num_time_intervals=3, num_expansion_intervals=1),
        ),  # number of time invervals smaller than array
    ],
)
def test_expand_as_dict_should_raise_exception(timeseriesdata):
    with pytest.raises(Exception):
        expand_as_dict(data=timeseriesdata)
