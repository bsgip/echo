import numpy as np
import pytest

from echo.utils import (TimeSeriesData, UnexpandableTimeSeriesDataError,
                        expand_as_array, expand_as_dict)


@pytest.mark.parametrize(
    "timeseriesdata,expected",
    [
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4},
        ),  # array with no expansion intervals
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=4, num_expansion_intervals=1),
            {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3},
        ),  # smaller array with no expansion intervals
        (
            TimeSeriesData(value=42, num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42},
        ),  # scalar with no expansion intervals
        (
            TimeSeriesData(value=[42], num_time_intervals=5, num_expansion_intervals=1),
            {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42},
        ),  # "wrapped" scalar with no expansion intervals
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
        ),  # array with 2 expansion intervals
        (
            TimeSeriesData(value=[[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]], num_time_intervals=5, num_expansion_intervals=2),
            {
                (0, 0): 0,
                (0, 1): 1,
                (0, 2): 2,
                (0, 3): 3,
                (0, 4): 4,
                (1, 0): 5,
                (1, 1): 6,
                (1, 2): 7,
                (1, 3): 8,
                (1, 4): 9,
            },
        ),  # 2d list and 2 expansion intervals [[time interval for first expansion],[time interval for second expansion]]  # noqa E501
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
        ),  # number of time intervals smaller than array
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
        ),  # array with no additional expansion intervals
        (
            TimeSeriesData(value=[0, 1, 2, 3], num_time_intervals=4, num_expansion_intervals=1),
            [[0, 1, 2, 3]],
        ),  # smaller array with no additional expansion intervals
        (
            TimeSeriesData(value=42, num_time_intervals=5, num_expansion_intervals=1),
            [[42, 42, 42, 42, 42]],
        ),  # scalar with no additional expansion intervals
        (
            TimeSeriesData(value=[42], num_time_intervals=5, num_expansion_intervals=1),
            [[42, 42, 42, 42, 42]],
        ),  # "wrapped" scalar with no expansion intervals
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=2),
            [[0, 1, 2, 3, 4], [0, 1, 2, 3, 4]],
        ),  # array with 2 expansion intervals
        (
            TimeSeriesData(value=[[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]], num_time_intervals=5, num_expansion_intervals=2),
            [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]],
        ),  # 2d list and 2 expansion intervals [[time interval for first expansion],[time interval for second expansion]]  # noqa E501
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
        ),  # number of time intervals smaller than array
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=5, num_expansion_intervals=0)
        ),  # array with expansion intervals set to 0
        (
            TimeSeriesData(value=[0, 1, 2, 3, 4], num_time_intervals=0, num_expansion_intervals=1)
        ),  # array with time intervals set to 0
    ],
)
def test_expand_as_array_should_raise_exception(timeseriesdata):
    with pytest.raises(UnexpandableTimeSeriesDataError):
        expand_as_array(data=timeseriesdata)
