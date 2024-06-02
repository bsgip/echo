from dataclasses import dataclass
from typing import Optional, Union

import numpy as np
import numpy.typing as npt
import orjson as orjson
import pandas as pd
import pyomo.environ as en
from sklearn import linear_model

from echo.configuration import Flows
from echo.exceptions import validate
from echo.functional import maybe_list
from echo.models.scenario import EchoConcreteModel
from echo.validators import ArrayType


def clamp(n, smallest, largest):
    return max(smallest, min(n, largest))


def _to_values(profile, key):
    if isinstance(profile, dict):
        return profile[key]
    return dict(enumerate(profile[key].values))


TimeExpandableType = Union[int, float, list[int | float], list[list[int | float]]]
"""TimeExpandableType

Variables with type `TimeExpandableType` should only contain numbers (int or float).
They should be either a single number e.g 37.3, a list containing a single number e.g. [5],
a 1-dimensional list of numbers e.g. [1.1, 2.2, 3.3, 4.4, ...]
or a 2-dimensional list of number e.g. [[1,2,3,4, ...], [5, 6, 7, 8, ...]].
"""


class UnexpandableTimeSeriesDataError(Exception):
    pass


@dataclass
class TimeSeriesData:
    """A dataclass to hold a compressed way of describing time series data.

    The TimeSeriesData object describes a potentially compressed form of time-series data by
    allowing you to store only a minimal set of values.

    `value` has type ``TimeExpandableType``. It should only contain numbers (int or float).
    It should be either a single number e.g 37.3, a list containing a single number e.g. [5],
    a 1-dimensional list of numbers e.g. [1.1, 2.2, 3.3, 4.4, ...]
    or a 2-dimensional list of number e.g. [[1,2,3,4, ...], [5, 6, 7, 8, ...]].

    For 1-dimensional and 2-dimensional lists, it is important to match the number of elements in the lists to the
    `num_time_intervals` and `num_expansion_intervals`.
    1-dimensional lists:
        `len(value) == num_time_intervals * num_expansion_intervals`
    2-dimensional lists:
        `len(value) == num_expansion_intervals` AND the sublists in `value` should have
        `len(sublist) == num_time_intervals`

    For example, if we have 4 time-intervals and 2 expansion-intervals, then the following would be valid:
    value = [[1, 2, 3, 4], [5, 6, 7, 8]] (2-dimensional list). Remember: the first index into a 2-dimensional list is
    the expansion interval and the second index is the time interval.

    or we could flatten the above list into a 1-dimensional list:
    value = [1, 2, 3, 4, 5, 6, 7, 8] since len(value) == 4 * 2. The first four value (1, 2, 3, 4) would apply to the
    first expansion period and the next four values (5, 6, 7, 8) would apply to the second expansion period.

    Note:
        TimeSeriesData performs no validation. In other words it is possible to create invalid TimeSeriesData objects.
        For example, `TimeSeriesData(value=[1,2,3], num_time_intervals=5, num_expansion_intervals=1)`
        would be invalid because the `num_time_intervals` (5) is greater than the number of elements in the value
        (only 3).

    TimeSeriesData objects serve as input to the `expand_as_array` and `expand_as_dict` functions. These functions
    serve to expand a TimeSeriesData description into a full set of time series data.

    Attributes:
        value (TimeExpandableType): time series data. See above for more information on valid values.
        num_time_intervals (int): the number of time intervals for the time series data.
        num_expansion_intervals (int): the number of expansion intervals for the time series data. Minimum value is 1,
         which can be thought as having no expansion intervals.
    """

    value: TimeExpandableType
    num_time_intervals: int
    num_expansion_intervals: int


def expand_as_dict(data: TimeSeriesData) -> dict[tuple[int, int], Union[int, float]]:
    """Converts a TimeSeriesData object to a dictionary of time-series values keyed by the expansion and time intervals.

    Calls `expand_as_array` internally to produce enough values for the time and expansion intervals.
    See `expand_as_array` for an explanation of how this works.

    Example:
        >>> expand_as_dict(TimeSeriesData(value=[[1,2],[3,4]],num_time_intervals=2,num_expansion_intervals=2))
        {(0, 0): 1, (0, 1): 2, (1, 0): 3, (1, 1): 4}

    Args:
        data (TimeSeriesData): A TimeSeriesData object.

    Returns:
        dictionary of time series values keyed by a tuple of the form: (expansion interval, time interval)

    Raises:
        UnexpandableTimeSeriesDataError: If there are too few or too many time series values for the given number of
        time periods/expansion periods.

    """
    expanded_data = expand_as_array(data).flatten()

    keys = [(x, i) for x in range(data.num_expansion_intervals) for i in range(data.num_time_intervals)]
    return dict(zip(keys, expanded_data))


def expand_as_array(data: TimeSeriesData) -> npt.NDArray:
    """Expands a TimeSeriesData object into a numpy array.

    The TimeSeriesData object described (potentially) compressed form of time-series data by only
    stor

    Example:
        >>> t = TimeSeriesData(value=[1,2,3,4],num_time_intervals=2,num_expansion_intervals=2)
        >>> expand_as_array()
        array([[1, 2],
            [3, 4]])

    Example:
        >>> t = TimeSeriesData(value=89.2,num_time_intervals=3,num_expansion_intervals=2)
        >>> expand_as_array(t)
        array([[89.2, 89.2, 89.2],
            [89.2, 89.2, 89.2]])

    Example:
        >>> t = TimeSeriesData(value=[12.1,12.2],num_time_intervals=2,num_expansion_intervals=4)
        >>> expand_as_array(t)
        array([[12.1, 12.2],
            [12.1, 12.2],
            [12.1, 12.2],
            [12.1, 12.2]])


    Args:
        data (TimeSeriesData): A TimeSeriesData object.

    Returns:
        An 2-dimensional array of time series data. The first index is the expansion interval
        and the second index is the time period.

    Raises:
        UnexpandableTimeSeriesDataError: If there are too few or too many time series values for the given number of
        time periods/expansion periods.

    """
    if data.num_expansion_intervals < 1:
        raise UnexpandableTimeSeriesDataError(
            f"num_expansion_intervals is less than one ('{data.num_expansion_intervals}' provided). See TimeSeriesData for more information"  # noqa E501
        )

    value = maybe_list(data.value)
    flat_array = np.array(value).flatten()

    if len(flat_array) == 1:
        num_repeats = data.num_time_intervals * data.num_expansion_intervals
        return np.repeat(flat_array[0], num_repeats).reshape((data.num_expansion_intervals, data.num_time_intervals))

    if len(flat_array) == data.num_time_intervals:  # tile across expansion periods
        return np.vstack([flat_array] * data.num_expansion_intervals)

    if len(flat_array) == data.num_time_intervals * data.num_expansion_intervals:
        return np.reshape(flat_array, (data.num_expansion_intervals, data.num_time_intervals))

    raise UnexpandableTimeSeriesDataError(
        "Mismatch between the number of time intervals/expansion periods and the number of elements in `value`. See TimeSeriesData for more information"  # noqa E501
    )


def set_float_var_bounds(model: EchoConcreteModel, var_name: str, ub: Optional[float], lb: Optional[float]) -> None:
    """
    Updates the bounds on a pyomo variable. Only floats can be used as bounds.
    Args:
        model: pyomo concrete model
        var_name: variable name (str) corresponding to a variable in the model
        ub: upper bound value, or None
        lb: lower bound value, or None
    Returns:
        None
    """
    var = getattr(model, var_name)
    if lb is not None:
        var.setlb(lb)
    if ub is not None:
        var.setub(ub)


def set_var_bounds_from_dict(model: EchoConcreteModel, var_name: str, ub: Optional[dict], lb: Optional[dict]) -> None:
    """
    Updates the bounds on a pyomo variable using an array of floats.
    Args:
        var: pyomo variable
        ub: dict of floats, where dict keys match variable index sets, or None
        lb: dict of floats, where dict keys match variable index sets, or None
    Returns:
        None
    """
    var = getattr(model, var_name)
    if lb is not None:
        for k, i in lb.items():
            var[k].setlb(i)
    if ub is not None:
        for k, i in ub.items():
            var[k].setub(i)


def generate_array_constraint(constraint, time_periods: int, expansion_periods: int) -> dict:
    """
    Args:
        constraint: float or array
    Returns:
        d: a formatted dict to be used in constraining a variable
    """
    d = {}
    if (type(constraint) is float) or (type(constraint) is int):
        for p in range(expansion_periods):
            for t in range(time_periods):
                d[(p, t)] = constraint
    elif hasattr(constraint, "__iter__"):
        # Check length
        if (len(constraint) != time_periods) or (len(constraint) != time_periods * expansion_periods):
            raise ValueError("Array constraint length is not consistent with time periods/expansion periods.")
        if len(constraint) == time_periods:
            # Can tile across expansion periods
            for p in range(expansion_periods):
                for t in range(time_periods):
                    d[(p, t)] = constraint[t]
        if len(constraint) == time_periods * expansion_periods:
            # No tiling
            i = 0
            for p in range(expansion_periods):
                for t in range(time_periods):
                    d[(p, t)] = constraint[i]
                    i += 1
    return d


# class PretendArray:
#     def __init__(self, var):
#         self.var = var
#
#     # initialisation check


def fix_port_variable(model: EchoConcreteModel, var_name: str, new_values: ArrayType, expansion_periods=1):
    """
    Updates existing pyomo variable to have fixed values.
    Args:
        model: pyomo concrete model
        var_name: pyomo variable name (str)
        new_values: array or list of new values
        expansion_periods: number of expansion periods (int)

    """
    var = getattr(model, var_name)
    keys = [(x, i) for x in range(expansion_periods) for i in range(len(var))]
    fixed_vals = dict(zip(keys, new_values))
    var.set_values(fixed_vals)
    var.fix()


def generate_input_output_values_from_polynomial_coeff_array(coeff_array, pts):
    """
    Generates x and y values for the polynomial function with coefficients defined by the coeff array
    Args:
        coeff array: list of polynomial function coefficients
        pts: list of x values for which we want to evaluate the function described by the coeff array
    """

    x = pts
    y = np.zeros(len(x))
    n = len(coeff_array)
    for i in range(len(y)):
        for j in range(n):
            y[i] += np.power(x[i], n - j) * coeff_array[j]
    return x, y


def generate_piecewise_input_output_arrays(coeff_array, pts):
    """
    Generates x and y values for the polynomial function with coefficients defined by the coeff array
    Args:
        coeff array: list of polynomial function coefficients, indexed by time
        pts: list of x values for which we want to evaluate the function described by the coeff array
    """

    x = pts
    y = np.zeros(len(x))
    n = len(coeff_array)
    for i in range(len(y)):
        for j in range(n):
            y[i] += np.power(x[i], n - j) * coeff_array[j]
    return x, y


def do_multivariate_regression(X, y):
    """
    Performs multivariate regression on provided data.
    Args:
        X:
        Y:
    Returns:
        coefficient array
        R^2

    """
    regr = linear_model.LinearRegression()
    regr.fit(X, y)

    return regr.coef_, regr.score(X, y)


def create_input_output_pts_from_coefficients(temp_coef, input_coef, temperature_array, xpts, time_periods):
    """Generates a set of output (y) points based on two coefficient arrays,
    one that applies to the input variable and one that applies to temperature, and non decreasing xpts.
    Args:
        temp_coef: list of coefficients, right to left in increasing order
        input_coef: list of coefficients, right to left in increasing order
        temperature_array: list of temperature data for time intervals T
        xpts: number of x points we want to do our piecewise evaluation over
        time_periods: number of optimisation time periods

    Returns:
        x: a dict of lists, where keys are the index set, defining the set of domain breakpoints for
           the piecewise linear function.
        y: a dict of lists, where keys are the index set, defining the set of domain breakpoints for
           the piecewise linear function.

    """

    # todo generalise this further to take an arbitrary number of arrays (eg temp array) + corresponding
    # coeff array, so we can do arbitrary number of variables
    x = {}
    y = {}
    num_temp_cols = len(temp_coef)
    num_input_cols = len(input_coef)
    # Need to account for coefs being defined R->L, so pre-calculate the order for each column in our coef arrays
    temp_orders = [i for i in range(num_temp_cols)][::-1]
    input_orders = [i for i in range(num_input_cols)][::-1]

    T = time_periods  # get the optimisation time period

    for t in range(T):
        # collect our temperature terms into a single term for this time period
        temp_term = 0
        for temp_col in range(num_temp_cols):  # Iterate through all our temperature terms and add them up
            # Format is temp**order * coeff
            temp_term += np.power(temperature_array[t], temp_orders[temp_col]) * temp_coef[temp_col]

        y_vals = []
        # Iterate through our x breakpoints
        for i in range(len(xpts)):
            output_term = 0
            # Collect all RHS terms by calculating x^2*coeff, x*coeff, etc and summing them together
            for input_col in range(num_input_cols):
                output_term += np.power(xpts[i], input_orders[input_col]) * input_coef[input_col] + temp_term
            y_vals.append(output_term)  # Populate our y values
        # Format as dict of lists
        y[(0, t)] = list(np.array(y_vals) * -1)  # Account for output being -ve
        x[(0, t)] = list(xpts)

    return x, y


def populate_values_across_time_and_expansion_indices(values, time_periods, expansion_periods):
    """Takes some input (values) - could be array, or int. Adds a time_period and expansion period key.

    Example:
        {(0, 0): 10, (0, 1): 10, (0, 2): 10, (0, 3): 10, (1, 0): 10, (1, 1): 10, (1, 2): 10, (1, 3): 10}
    """
    output = {}
    for p in range(expansion_periods):
        for t in range(time_periods):
            output[(p, t)] = values

    return output


def create_named_constraint_with_rule(model: EchoConcreteModel, con_name: str, rule):
    """Util function for creating pyomo constraints from a rule."""
    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=rule))


def tile_array_over_expansion_periods(array, expansion_periods):
    """Constructs an array by repeating 'array' input x times where x = num of expansion periods"""
    output = np.tile(np.array(array), expansion_periods)
    return output


def to_initial_values(profile: pd.DataFrame, key: str, time_periods: int, expansion_periods: int, scaling: int = 1):
    if profile is None:
        raise ValueError("No profile dataframe defined. Check that you added the profile to the optimiser.")
    values = profile[key].values * scaling
    validate(len(values) == time_periods, "Initial values are wrong length.")
    keys = [(x, i) for x in range(expansion_periods) for i in range(time_periods)]
    d = dict(zip(keys, values))
    return d


def orjson_dumps(v, *, default):
    for key, value in v.items():
        if isinstance(value, dict):
            v[key] = ":".join(value)

    # orjson.dumps returns bytes, to match standard json.dumps we need to decode
    return orjson.dumps(v, default=default).decode()


def generate_dict_with_pyomo_keys_from_array(array, time_periods: int, expansion_periods: int = 1):
    """
    Generates a dict suitable for initializing a pyomo var or param.
    The dict keys are a tuple (expansion period, time period)
    """
    d = {}
    validate(hasattr(array, "__iter__"), "Please enter an iterable array")
    if (len(array) != time_periods) or (len(array) != time_periods * expansion_periods):
        raise ValueError("Array constraint length is not consistent with combination of time/expansion periods.")
    if len(array) == time_periods:
        print("Repeating array across {} expansion period(s).".format(expansion_periods))
        for p in range(expansion_periods):
            for t in range(time_periods):
                d[(p, t)] = array[t]
    elif len(array) == time_periods * expansion_periods:
        print("Dividing array between {} expansion period(s).".format(expansion_periods))
        i = 0
        for p in range(expansion_periods):
            for t in range(time_periods):
                d[(p, t)] = array[i]
                i += 1
    return d


def domain_from_flow(flow: Flows):
    match flow:
        case Flows.Both:
            domain = en.Reals
        case Flows.Export:
            domain = en.NonPositiveReals
        case Flows.Import:
            domain = en.NonNegativeReals
        case Flows.NA:
            raise ValueError("Cannot add flow variable to port with flows=Flows.NA")
    return domain
