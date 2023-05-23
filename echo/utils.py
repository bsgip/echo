import numpy as np
from echo.echo_validators import *
from sklearn import linear_model
import pandas as pd
import pyomo.environ as en
from collections.abc import Sequence
import orjson as orjson

def _to_values(profile, key):
    if isinstance(profile, dict):
        return profile[key]
    return dict(enumerate(profile[key].values))


class ArrayWrap(Sequence):
    def __init__(self, var):            # scalar, 1d list, 2d list,
        self.var = var
        if not hasattr(var, "__len__"):
            self.get_func = self.get_scalar
            self.is_scalar = True
        elif (len(var)==1) and (not hasattr(var[0], "__len__")) :
            self.get_func = self.get_scalar
            self.is_scalar = True
            self.var = var[0]
        else:
            self.get_func = self.get_dummy
            self.is_scalar = False
        self.time_periods = None
        self.expansion_periods = None
        self.tp_set = False  # for indicating whether the time period has been set

        super().__init__()


    def dict(self):
        """ For converting array wrap to a dict"""
        assert self.tp_set is True, 'Set time periods before converting to dict'
        keys = [(x, i) for x in range(self.expansion_periods) for i in range(self.time_periods)]
        if not self.is_scalar:
            vals = np.reshape(self.var, self.expansion_periods*self.time_periods)
        else:
            vals = self.var * np.ones(self.expansion_periods*self.time_periods)
        d = dict(zip(keys, vals))
        return d

    def set_periods(self, expansion_periods: int, time_periods: int)->None:
        self.time_periods = time_periods
        self.expansion_periods = expansion_periods
        self.tp_set = True
        if not self.is_scalar:
            self.get_func = self.get_array
            var_array = np.array(self.var).flatten()
            if len(var_array) == time_periods:   # tile across expansion periods
                self.var = np.vstack([var_array]*expansion_periods)
            elif len(var_array) == time_periods*expansion_periods:
                self.var = np.reshape(var_array, (expansion_periods, time_periods))
            else:
                raise Exception("must have shape of scalar, (expansion_periods,time_periods), (time periods,) or (expansion_periods * time_periods,)")

    def __getitem__(self, i):
        return self.get_func(i)

    def get_scalar(self, i):
        #todo this will return valid numbers even if the index is out of range
        return self.var

    def get_dummy(self, i):
        assert self.tp_set, "for non scalar values must set time and expansion periods of ArrayWrap"
        return None

    def get_array(self, i):
        return self.var[i]
    #
    # def get_non_scalar(self, i):
    #     if isinstance(i, tuple):
    #         p = i[0], t=i[1]


    def __len__(self):
        return len(self.var)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ArrayWrap):
            return v
        if isinstance(v, (float, int, list, np.ndarray)):
            return cls(v)
        else:
            raise TypeError('requires float, int, list or arraylike')

def set_float_var_bounds(model, var_name: str, ub: float or None, lb: float or None) -> None:
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
    v = getattr(model, var_name)
    if lb is not None:
        v.setlb(lb)
    if ub is not None:
        v.setub(ub)

def set_var_bounds_from_dict(var, ub: dict or None, lb: dict or None) -> None:
    """
    Updates the bounds on a pyomo variable using an array of floats.
    Args:
        var: pyomo variable
        ub: dict of floats, where dict keys match variable index sets, or None
        lb: dict of floats, where dict keys match variable index sets, or None
    Returns:
        None
    """
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
    elif hasattr(constraint, '__iter__'):
        # Check length
        if (len(constraint) != time_periods) or (len(constraint) != time_periods*expansion_periods):
            raise ValueError('Array constraint length is not consistent with time periods/expansion periods.')
        if len(constraint) == time_periods:
            # Can tile across expansion periods
            for p in range(expansion_periods):
                for t in range(time_periods):
                    d[(p, t)] = constraint[t]
        if len(constraint) == time_periods*expansion_periods:
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


def fix_port_variable(model, var_name: str, new_values: ArrayType, expansion_periods=1):
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
    """ Generates a set of output (y) points based on two coefficient arrays,
    one that applies to the input variable and one that applies to temperature, and non decreasing xpts.
    Args:
        temp_coef: list of coefficients, right to left in increasing order
        input_coef: list of coefficients, right to left in increasing order
        temperature_array: list of temperature data for time intervals T
        xpts: number of x points we want to do our piecewise evaluation over
        time_periods: number of optimisation time periods

    Returns:
        x: a dict of lists, where keys are the index set, defining the set of domain breakpoints for the piecewise linear function.
        y: a dict of lists, where keys are the index set, defining the set of domain breakpoints for the piecewise linear function.

        """

    # todo generalise this further to take an arbitrary number of arrays (eg temp array) + corresponding coeff array, so we can do arbitrary number of variables
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
    """ Takes some input (values) - could be array, or int. Adds a time_period and expansion period key.
    Eg for inputs:
        values = 10
        time_periods = 4
        expansion_periods = 2
    the output dict would be:
    Output = {(0,0): 10,
              (0,1): 10,
              ...
              (2,2): 10
              (2,3): 10}
    """
    output = {}
    for p in range(expansion_periods):
        for t in range(time_periods):
            output[(p, t)] = values

    return output


def create_named_constraint_with_rule(model, con_name, rule):
    """ Util function for creating pyomo constraints from a rule."""
    setattr(model, con_name, en.Constraint(model.Expansion, model.Time, rule=rule))

def tile_array_over_expansion_periods(array, expansion_periods):
    """ Constructs an array by repeating 'array' input x times where x = num of expansion periods"""
    output = np.tile(np.array(array), expansion_periods)
    return output


def to_initial_values(profile: pd.DataFrame, key: str, time_periods: int, expansion_periods: int, scaling: int = 1):
    if profile is None:
        raise ValueError('No profile dataframe defined. Check that you added the profile to the optimiser.')
    values = profile[key].values * scaling
    assert len(values) == time_periods, 'Initial values are wrong length.'
    keys = [(x, i) for x in range(expansion_periods) for i in range(time_periods)]
    d = dict(zip(keys, values))
    return d

def orjson_dumps(v, *, default):
    # orjson.dumps returns bytes, to match standard json.dumps we need to decode
    return orjson.dumps(v, default=default).decode()

def orjson_dumps(v, *, default):
    for key, value in v.items():
        if isinstance(value, dict):
            v[key] = ':'.join(value)

    # orjson.dumps returns bytes, to match standard json.dumps we need to decode
    return orjson.dumps(v, default=default).decode()



def process_time_series_data(array: np.ndarray, time_periods: int, expansion_periods: int = 1):
    x = ArrayWrap(array)
    x.set_periods(time_periods=time_periods, expansion_periods=expansion_periods)


def generate_dict_with_pyomo_keys_from_array(array, time_periods: int, expansion_periods: int = 1):
    """
    Generates a dict suitable for initializing a pyomo var or param.
    The dict keys are a tuple (expansion period, time period)
    """
    d = {}
    assert hasattr(array, '__iter__'), 'Please enter an iterable array'
    if (len(array) != time_periods) or (len(array) != time_periods*expansion_periods):
        raise ValueError('Array constraint length is not consistent with combination of time/expansion periods.')
    if len(array) == time_periods:
        print('Repeating array across {} expansion period(s).'.format(expansion_periods))
        for p in range(expansion_periods):
            for t in range(time_periods):
                d[(p, t)] = array[t]
    elif len(array) == time_periods*expansion_periods:
        print('Dividing array between {} expansion period(s).'.format(expansion_periods))
        i = 0
        for p in range(expansion_periods):
            for t in range(time_periods):
                d[(p, t)] = array[i]
                i += 1
    return d
