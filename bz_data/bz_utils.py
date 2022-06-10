import pandas as pd
from sklearn import linear_model


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



def get_default_chiller_coefficients():
    df = pd.read_csv('../bz_data/chiller_data.csv')
    X = df[['Temp', 'Temp^2', 'Demand', 'Demand^2']]
    y = df['Cooling Load']*-1  # Need to make output negative to confirm to echo convention

    coef_array, r_sq = do_multivariate_regression(X, y)
    print('Chiller R^2: ', r_sq)
    temp_coef = coef_array[0:2]
    input_coef = coef_array[2:4]

    return temp_coef, input_coef


def get_default_heat_pump_coefficients():
    df = pd.read_csv('../bz_data/heat_pump_data.csv.csv')
    x = df['Ambient Temp']
    y = df['COP']

    coef_array, r_sq = do_multivariate_regression(x, y)
    print('HP R^2: ', r_sq)
    return coef_array


def get_temp_data_from_chiller_data():
    df = pd.read_csv('../bz_data/chiller_data.csv')
    x = df['Temp'].values

    return x