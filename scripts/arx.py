
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from echo.bz_utils import *

df = pd.read_csv('../../lab5_data.csv')

mse_test, mse_trained, model_coef = train_arx_on_data(df['u'], df['y'], na=6, nb=5, training_test_split=67)