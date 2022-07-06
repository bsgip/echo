import pandas as pd
from sklearn import linear_model
import json
import os

from sklearn.linear_model import LinearRegression
from tqdm import tqdm
import pandas as pd
import glob
import numpy as np

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


def gas_profiler(
        seasonal_profile_df: pd.DataFrame,
        season_multiplier: dict,
        start_date: str,
        end_date: str
) -> pd.DataFrame:
    """Construct an hourly gas profile given a seasonal profile, start/end dates.

    Keeping everything in timezone unaware local time for now. #TODO see if this needs changing.


    Args:
        seasonal_profile_df: Seasonal profile dataframe. Columns must be "Timestamp", "Autumn",
            "Winter", "Spring", "Summer". Values in "Timestamp" column must be 0:00 to 23:00 in
            hourly increments and be strings. All other values are floats.
        season_multiplier: A dictionary containing a multiplier for each season. Keys of dict must
            be strings "Autumn", "Winter", "Spring", "Summer". Values to be floats.
        start_date: "YYYY-MM-DD" format. TODO: Test if works with other datetime formats.
        end_date: "YYYY-MM-DD" format. TODO: Test if works with other datetime formats.

    Returns:
        hourly_gas_profile_df: Dataframe of hourly gas profiles for specified date range.
    """

    # Map each numeric month to string month (from data files)
    month_to_season_map = {
        12: "Summer", 1: "Summer", 2: "Summer",
        3: "Autumn", 4: "Autumn", 5: "Autumn",
        6: "Winter", 7: "Winter", 8: "Winter",
        9: "Spring", 10: "Spring", 11: "Spring"
    }

    # Multiply hourly profile by seasonal constant.
    for season in set(month_to_season_map.values()):
        seasonal_profile_df[season] = seasonal_profile_df[season] * season_multiplier[season]

    # Unpivot gas profile to make it easier to access
    seasonal_profile_df = seasonal_profile_df.melt(
        id_vars=["Timestamp"],
        value_vars=["Summer", "Autumn", "Winter", "Spring"],
        var_name="Season",
        value_name="profile"
    )

    # Get hour of each timestamp for profile
    seasonal_profile_df["Hour"] = seasonal_profile_df["Timestamp"].str.split(":", expand=True)[0].astype(int)

    # Generate datetimes for range specified
    hourly_gas_profile_df = pd.DataFrame(
        index=pd.date_range(start=start_date, end=end_date, freq="1H"),
    )

    # Extract out variables to merge on with profile
    hourly_gas_profile_df["Season"] = hourly_gas_profile_df.index.month.map(month_to_season_map)
    hourly_gas_profile_df["Hour"] = hourly_gas_profile_df.index.hour

    # Merge on season and hour
    hourly_gas_profile_df = hourly_gas_profile_df.reset_index().merge(
        seasonal_profile_df[["Season", "Hour", "profile"]],
        on=["Season", "Hour"]
    )

    # Clean up and format dataframe for returning
    hourly_gas_profile_df = hourly_gas_profile_df[["index", "profile"]]
    hourly_gas_profile_df = hourly_gas_profile_df.rename(columns={"index": "Timestamp"})

    # Sort by date and time
    hourly_gas_profile_df = hourly_gas_profile_df.sort_values("Timestamp")

    return hourly_gas_profile_df

def train_arx_on_data(u: pd.DataFrame, y: pd.DataFrame, na: int, nb: int, training_test_split: int):
    """
    Trains an ARX model on the provided data. Returns the model parameters as well as the absoulte % error for the test dataset and training dataset.
    """

    def build_phi_matrix(na, nb, u, y):
        """ Builds the regressor matrix phi"""
        n = len(y)
        ns = max(na, nb)
        phi = np.zeros([n - ns, na + nb])
        for row in range(n - ns):
            phi[row, 0:na] = y[row:row + na]
            phi[row, na:na + nb] = u[row + 1:row + nb + 1]  # why the plus one?
        return phi

    def calculate_mse(y, yhat):
        """ Calculates mean squared error between y and yhat"""
        assert len(y) == len(yhat)
        sum = 0
        for i in range(len(y)):
            sum += (y[i] - yhat[i]) ** 2
        return sum/len(y)

    def use_coef_to_predict_y(phi, model):
        """ Uses coefficients from regression, as well as regressor matrix, to predict y values"""
        y_predicted = np.matmul(phi, model.coef_)
        return y_predicted

    def split_training_validation(y, u, split_percentage):
        total = len(y)
        assert total // split_percentage == 0, 'Test/train split % does not give an unambiguous split'
        training_y = y[0:int(total * split_percentage / 100)]
        training_u = u[0:int(total * split_percentage / 100)]
        validation_y = y[int(total * split_percentage / 100):]
        validation_u = u[int(total * split_percentage / 100):]
        return training_y, training_u, validation_y, validation_u

    def fit_model_params(phi, y):
        """ Creates a linear regression model and fits the params, returning the model object"""
        model = LinearRegression()
        model.fit(phi, y)
        return model

    # 1. Split data
    training_y, training_u, test_y, test_u = split_training_validation(y.values, u.values, training_test_split)
    # 2. Calculate phi from training data
    training_phi = build_phi_matrix(na=na, nb=nb, u=training_u, y=training_y)
    # 3. Fit model params (and trim y in the process)
    trained_model = fit_model_params(training_phi, training_y[max(na, nb):])
    # 4. Calculate phi test
    test_phi = build_phi_matrix(na=na, nb=nb, u=test_u, y=test_y)
    # 5. Predict outputs of test set
    yhat_test = use_coef_to_predict_y(test_phi, trained_model)
    # 6. Calculate MSE for test and training data
    mse_test = calculate_mse(test_y[max(na, nb):], yhat_test)
    # 7. Do the same for training data, for comparison
    yhat_training = use_coef_to_predict_y(training_phi, trained_model)
    mse_trained = calculate_mse(training_y[max(na, nb):], yhat_training)

    return mse_test, mse_trained, trained_model.coef_


