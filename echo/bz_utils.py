import pandas as pd
from sklearn import linear_model
import json
import os
from tqdm import tqdm
import pandas as pd
import glob

from bz_data import anu_hv_network


def munger(data_file_path, output_folder_name, output_file_name):
    """ Data munger for electrical data out of the ANU ems portal"""

    # Get file names of uncleaned data files
    all_files = glob.glob(data_file_path+"/*.csv")

    dfs = []
    for file in tqdm(all_files, desc='Cleaning files'):
        # Read file into data frame
        df = pd.read_csv(file)
        # Change timestamp column name to something less crap
        df = df.rename(columns={"ui::timestamp": "timestamp"})
        # Drop the "Sydney" part of the timestamp, presumably a text representation of the timezone
        df["timestamp"] = df["timestamp"].str.split(" ").str[0]
        # Make timestamp a datetime object
        df["timestamp"] = pd.to_datetime(df.timestamp)
        # make timestamp the index
        df = df.set_index("timestamp")
        dfs.append(df)

    # Merge files
    df = pd.concat(dfs, axis=1)
    # Strip units out of readings
    df = df.apply(lambda x: x.str.extract(r'(\d+)', expand=False))
    # Make all power and energy values an float (nans are floats)
    df = df.astype(float)
    # Convert to SI
    df = df*1000

    # Check if output folder exists, if not create one
    if not os.path.isdir(data_file_path + '/' + output_folder_name):
        os.makedirs(data_file_path + '/' + output_folder_name)

    # Write to file
    df.to_csv(data_file_path + '/' + output_folder_name + '/' + output_file_name + '.csv')


def convert_network_dict_to_json(file_name='acton_network.json'):
    print('Converting components dict to json')
    # Import the custom defined components dict
    from bz_data.anu_hv_network import feeder_dict
    with open(file_name, 'w+') as f:
        json_obj = json.dumps(feeder_dict, indent=2)
        # Write it to a json file
        f.write(json_obj)


def get_anu_electrical_network_json(file_name='../bz_data/acton_network.json'):
    print('Importing components data as json')
    with open(file_name) as f:
        netw_jsn = json.load(f)
    return netw_jsn


def clean_electrical_data(
        data_file_path="C:/Users/61405/Australian National University/BSGIP Staff - Below Zero (1)/Data/Echo modelling/AC 2019 data",
        output_folder_name='output1',
        output_file_name='data'):
    """ Performs data munging on ANU ems data"""
    munger(data_file_path, output_folder_name, output_file_name)


def get_cleaned_electrical_data():
    """ Loads cleaned electrical data"""
    file_path = "C:/Users/61405/Australian National University/BSGIP Staff - Below Zero (1)/Data/Echo modelling/AC 2019 data/output1/data.csv"
    df = pd.read_csv(file_path).set_index("timestamp")
    return df


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
    y = df['Cooling Load'] * -1  # Need to make output negative to confirm to echo convention

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


def match_network_building_name_to_time_series(netw_name: str, df: pd.DataFrame):
    """
    Args:
        netw_name: name as defined in the components json
        df: df of time series data
    Returns:
        col_name: col name of dataframe which matches netw_name, or None if there is no match.
    """
    def name_check(target_name: str):
        candidate_cols = []
        for col in df.columns:
            if target_name.lower() in col.lower():
                candidate_cols.append(col)
        return candidate_cols

    def get_energy_col(x: list):
        if 'Energy' in x[0]:
            return x[0]
        else:
            return x[1]

    x = name_check(netw_name)
    if len(x) == 2:  # There should always be two matching entries  - power and energy
        return get_energy_col(x)
    else:
        # Second pass - add a space either side of the netw_name
        new_name = ' ' + netw_name + ' '
        x = name_check(new_name)
        if len(x) == 2:
            return get_energy_col(x)
        elif len(x) < 2:
            return 'No matching column found.'
        elif len(x) > 2:
            return 'Multiple values found.'


def building_name_match_wrapper(building_names: list, df: pd.DataFrame):
    """ Matches a list of building names to columns in the dataframe."""
    col_names = []
    for name in building_names:
        col_names.append(match_network_building_name_to_time_series(name, df))

    return col_names


