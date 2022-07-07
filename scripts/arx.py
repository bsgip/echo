
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from echo.bz_utils import *

# df = pd.read_csv('../../lab5_data.csv')
#
# mse_test, mse_trained, model_coef = train_arx_on_data(df['u'], df['y'], na=6, nb=5, training_test_split=67)

df = pd.read_csv('../bz_data/thermal_load_arx_b155_data.csv')

# mse_test, mse_trained, model_coef = train_arx_on_data(u=df['energy_in'], y=df['avg_temp'], na=1, nb=1, training_test_split=67)

mse_test, mse_trained, model_coef = train_arx_multiple_inputs(u=df[['energy_in', 'temp_out', 'temp_sp', 'bld_hrs']],
                                                              y=df['avg_temp'],
                                                              na=2,
                                                              n_inputs=[2, 2, 0, 0],
                                                              training_test_split=67)