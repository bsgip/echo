import pytest

from echo.utils import expand


@pytest.mark.parametrize(
    "array,time_periods,expansion_periods,expected",
    [
        (range(5), 5, 1, {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3, (0, 4): 4}),  # array with no expansion periods
        (range(4), 4, 1, {(0, 0): 0, (0, 1): 1, (0, 2): 2, (0, 3): 3}),  # smaller array with no expansion periods
        (42, 5, 1, {(0, 0): 42, (0, 1): 42, (0, 2): 42, (0, 3): 42, (0, 4): 42}),  # scalar with no expansion periods
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
