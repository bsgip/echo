import numpy as np

def _to_values(profile, key):
    if isinstance(profile, dict):
        return profile[key]
    return dict(enumerate(profile[key].values))


def set_var_bounds(var_name, model, ub, lb):
    """ For setting bounds on pyomo variables"""
    v = getattr(model, var_name)
    v.setlb(lb)
    v.setub(ub)


def fix_port_variable(model, var_name, new_values, expansion_periods=1):
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


def generate_input_output_values_from_coeff_array(coeff_array, pts):
    """
    Generates x and y values for the function described by the coeff array
    Args:
        coeff array: list of polynomial function coefficients
        pts: list of x values for which we want to evaluate the function described by the coeff array
    """

    x = pts
    y = np.zeros(len(x))
    n = len(coeff_array)
    for i in range(len(y)):
        for j in range(n):
            y[i] += np.power(x[i], n-j)*coeff_array[j]
    return x, y

