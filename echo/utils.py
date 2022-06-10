import numpy as np
from echo.echo_validators import *
from sklearn import linear_model
import pandas as pd


def _to_values(profile, key):
    if isinstance(profile, dict):
        return profile[key]
    return dict(enumerate(profile[key].values))


def set_var_bounds(var_name: str, model, ub: float, lb: float) -> None:
    """ For setting bounds on pyomo variables"""
    v = getattr(model, var_name)
    v.setlb(lb)
    v.setub(ub)


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


def create_input_output_pts_from_coefficients(temp_coef, input_coef, temperature_array, xpts, model):
    """ Generates a set of output (y) points based on two coefficient arrays,
    one that applies to the input variable and one that applies to temperature, and non decreasing xpts.
    Args:
        temp_coef: list of coefficients, right to left in increasing order
        input_coef: list of coefficients, right to left in increasing order
        temperature_array: list of temperature data for time intervals T
        xpts: number of x points we want to do our piecewise evaluation over
        model: pyomo concrete model

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

    T = len(model.Time)  # get the optimisation time period

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


def add_time_and_expansion_index_to_values(values, time_periods, expansion_periods):
    """ Takes some input (values) - could be array, or int. Adds a time_period and expansion period key."""
    output = {}
    for p in range(expansion_periods):
        for t in range(time_periods):
            output[(p, t)] = values

    return output
