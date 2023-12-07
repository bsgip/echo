import numpy as np
import pytest

from echo.utils import (
    TimeSeriesData,
    UnexpandableTimeSeriesDataError,
    expand_as_array,
    expand_as_dict,
)


@pytest.mark.parametrize(
    "timeseriesdata,expected",
    [
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4},
        ),  # array with no expansion periods
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=4, num_expansion_intervals=1),
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
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=2),
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
            TimeSeriesData(value=[[0, 1, 2, 3, 4], [0, 1, 2, 3, 4]], num_time_intervals=5, num_expansion_intervals=2),
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
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=5, num_expansion_intervals=1)
        ),  # number of time intervals bigger than array
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=3, num_expansion_intervals=1)
        ),  # number of time invervals smaller than array
    ],
)
def test_expand_as_dict_should_raise_exception(timeseriesdata):
    with pytest.raises(UnexpandableTimeSeriesDataError):
        expand_as_dict(data=timeseriesdata)


@pytest.mark.parametrize(
    "timeseriesdata,expected",
    [
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=1),
            [[0, 1, 2, 3, 4]],
        ),  # array with no additional expansion periods
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=4, num_expansion_intervals=1),
            [[0, 1, 2, 3]],
        ),  # smaller array with no additional expansion periods
        (
            TimeSeriesData(value=42, num_time_intervals=5, num_expansion_intervals=1),
            [[42, 42, 42, 42, 42]],
        ),  # scalar with no additional expansion periods
        (
            TimeSeriesData(value=[42], num_time_intervals=5, num_expansion_intervals=1),
            [[42, 42, 42, 42, 42]],
        ),  # "wrapped" scalar with no expansion periods
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=2),
            [[0, 1, 2, 3, 4], [0, 1, 2, 3, 4]],
        ),  # array with 2 expansion periods
        (
            TimeSeriesData(value=[[0, 1, 2, 3, 4], [0, 1, 2, 3, 4]], num_time_intervals=5, num_expansion_intervals=2),
            [[0, 1, 2, 3, 4], [0, 1, 2, 3, 4]],
        ),  # 2d list and 2 expansion periods [[time period for first expansion],[time period for second expansion]]
    ],
)
def test_expand_as_array(timeseriesdata, expected):
    np.testing.assert_equal(expand_as_array(data=timeseriesdata), np.asarray(expected))


@pytest.mark.parametrize(
    "timeseriesdata",
    [
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=5, num_expansion_intervals=1)
        ),  # number of time intervals bigger than array
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=3, num_expansion_intervals=1)
        ),  # number of time invervals smaller than array
    ],
)
def test_expand_as_array_should_raise_exception(timeseriesdata):
    with pytest.raises(UnexpandableTimeSeriesDataError):
        expand_as_array(data=timeseriesdata)
