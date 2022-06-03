
import os
from tqdm import tqdm
import pandas as pd
import glob

def munger(data_file_path, output_folder_name, output_file_name):

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


def get_cleaned_data(file_path_name):
    df = pd.read_csv(file_path_name + '.csv').set_index("timestamp")
    return df