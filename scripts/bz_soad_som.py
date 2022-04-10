from __future__ import division

import random

import matplotlib.pyplot as plt
import matplotlib.dates as mdate
import numpy as np
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints
import networkx as nx
import pandas as pd
import time as time_


from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.objectives import *

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})


# Get data

# SOM
som_power_df = pd.read_csv('C:\\Users\\61405\\Documents\\BZ_data\\som_cp_meter.csv')
som_boiler1_df = pd.read_csv('C:\\Users\\61405\\Documents\\BZ_data\\som_boiler1.csv')
som_boiler2_df = pd.read_csv('C:\\Users\\61405\\Documents\\BZ_data\\som_boiler2.csv')

# SOAD
soad_solar_df = pd.read_csv('C:\\Users\\61405\\Documents\\BZ_data\\soad_solar.csv')

def data_cleaner_numeric(dp):
    output = 0
    x = str(dp)
    if x == 'nan': #todo - how to handle nan values
        output = 0
    else:
        n = str()
        for j in x:
            if j.isnumeric() or j=='.':
                n += str(j)
        if len(n) > 0:
            output = float(n)
    return output

def clean_ems_dataframe(df, data_col, data_name):
    time_col = df.columns[0]  # Time column is always first
    t = df[time_col] # Pull out time col for dataframe
    d = df[data_col]  # Pull out col that contains data
    index = []  # for storing cleaned times
    data_pts = [] # for storing data corresponding to cleaned times
    new_df = pd.DataFrame()
    for i in range(len(t)):
        # Only take times with 0 secs, or times where the data column has a value
        if t[i][17:19] == '00':
            index.append(datetime(year=int(t[i][0:4]),
                                month=int(t[i][5:7]),
                                day=int(t[i][8:10]),
                                hour=int(t[i][11:13]),
                                minute=int(t[i][14:16]),
                                second=0))
            data_pts.append(data_cleaner_numeric(d[i]))

    new_df['time'] = index
    new_df[data_name] = data_pts
    return new_df


power_col = [col for col in som_power_df.columns if 'Power' in col]
som_power_data = clean_ems_dataframe(som_power_df, power_col[0], 'som_power')

temp_col = [col for col in som_boiler1_df.columns if 'Flow-Temp' in col]
som_boiler1_data = clean_ems_dataframe(som_boiler1_df, temp_col[0], 'b1_temp')

temp_col = [col for col in som_boiler2_df.columns if 'Flow-Temp' in col]
som_boiler2_data = clean_ems_dataframe(som_boiler2_df, temp_col[0], 'b2_temp')

solar_col = [col for col in soad_solar_df.columns if 'Power' in col]
soad_solar_data = clean_ems_dataframe(soad_solar_df, solar_col[0], 'pv')

all_dfs = [som_power_data, som_boiler1_data, som_boiler2_data, soad_solar_data]
df = all_dfs[0]
i = 0
for df_ in all_dfs[1:]:
    df = df.merge(df_, on='time', suffixes=(None, df_.columns[-1]))
    i += 1


# New data :)
df_elec = pd.read_excel("C:\\Users\\61405\\Documents\\BZ_data\\soad_som_combined_data.xlsx", sheet_name='Electricity')
df_gas = pd.read_excel("C:\\Users\\61405\\Documents\\BZ_data\\soad_som_combined_data.xlsx", sheet_name='Gas2')

def convert_to_datetime(df):
    date_col = df.columns[0]
    time_col = df.columns[1]
    t = df[time_col] # Pull out time col for dataframe
    d = df[date_col]  # Pull out col that contains data
    index = []  # for storing cleaned times
    for i in range(len(t)):
        index.append(datetime(year=d[i].year,
                            month=d[i].month,
                            day=d[i].day,
                            hour=t[i].hour,
                            minute=t[i].minute,
                            second=t[i].second))

    df['datetime'] = index
    df.set_index('datetime')

# Convert both to datetime
convert_to_datetime(df_elec)
convert_to_datetime(df_gas)

# Downsample the electricity data to be hourly
df_elec_new = df_elec.set_index('datetime').resample(rule='1h').mean()
# todo there is something weird happening with the first entry
assert (df_elec_new.index == df_gas.set_index('datetime').index).all()  # check we have the timestamps lined up

# Do time period calcs

num_intervals = len(df_elec_new)
interval_duration = 60
expansion_intervals = 1

# Initialise graph
system = OptimisationGraph()

# For plotting
labels = {}

# Whole system nodes
bulk_grid = Node()
bulk_grid.ports['grid'] = ElectricalPort()
labels[bulk_grid] = 'bulk_grid'

bulk_gas = Node()
bulk_gas.ports['gas'] = GasPort()
bulk_gas.ports['emissions'] = CarbonSource()
bulk_gas.emission_factor = 60  # 60 kg per GJ gas
bulk_gas.add_emission_transformation(bulk_gas.ports['gas'], bulk_gas.ports['emissions'], bulk_gas.emission_factor)  # units
labels[bulk_gas] = 'bulk_gas'

connection_point = ElectricalTellegenNode()
connection_point.add_named_electrical_ports(['grid', 'soad', 'som'])
labels[connection_point] = 'elec_cp'

gas_cp = GasTellegenNode()
gas_cp.ports['bulk'] = GasPort()
gas_cp.ports['soad'] = GasPort()
gas_cp.ports['som'] = GasPort()
labels[gas_cp] = 'gas_cp'

### School of Art and Design (SoAD)

# Electrical assets
elec_conn_pt_soad = ElectricalTellegenNode()
elec_conn_pt_soad.add_named_electrical_ports(['heat_pump', 'pv', 'kiln'])
elec_conn_pt_soad.ports['cp'] = ElectricalDemand()
elec_conn_pt_soad.ports['cp'].add_demand_profile_from_array(df_elec_new['SoA_kW'].values, expansion_intervals)
labels[elec_conn_pt_soad] = 'soad_elec_cp'

elec_kiln = Node()
ek = ElectricalPort()
elec_kiln.ports['kiln'] = ek
labels[elec_kiln] = 'elec_kiln'

heat_pump_soad = Node()
hp_soad = ElectricalPort()
heat_pump_soad.ports['heat_pump'] = hp_soad
labels[heat_pump_soad] = 'soad_heat_pump'

solar = Node()
pv = ElectricalPort()#ElectricalGeneration() # Todo get EMS PV data into same format as excel data
#pv.add_generation_profile_from_array(df['pv'].values * -1, expansion_intervals)
solar.ports['pv'] = pv
labels[solar] = 'soad_solar'

# Gas assets
gas_cp_soad = GasTellegenNode()
gas_cp_soad.ports['cp'] = GasDemand()
gas_cp_soad.ports['cp'].add_demand_profile_from_array(df_gas['SoA_Gj'].values/interval_duration, expansion_intervals)

gas_cp_soad.ports['b1'] = GasPort()
gas_cp_soad.ports['b2'] = GasPort()
gas_cp_soad.ports['kiln'] = GasPort()
labels[gas_cp_soad] = 'soad_gas_cp'

boiler1_soad = Node()
b1_soad = GasPort()
boiler1_soad.ports['b1'] = b1_soad
labels[boiler1_soad] = 'soad_boiler1'

boiler2_soad = Node()
b2_soad = GasPort()
boiler2_soad.ports['b2'] = b2_soad
labels[boiler2_soad] = 'soad_boiler2'

gas_kiln = Node()
gk = GasPort()
gk.set_flow_constraints(max_export=0, max_import=0)
gas_kiln.ports['kiln'] = gk
labels[gas_kiln] = 'gas_kiln'


# Add assets and do connections
system.add_node_obj([bulk_grid,
                     bulk_gas,
                     connection_point,
                     elec_conn_pt_soad,
                     gas_cp,
                     gas_cp_soad,
                     elec_kiln,
                     heat_pump_soad,
                     solar,
                     boiler2_soad,
                     boiler1_soad,
                     gas_kiln])

# Electrical connections
system.connect_ports_and_create_edge(bulk_grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['soad'], elec_conn_pt_soad.ports['cp'])
system.connect_ports_and_create_edge(elec_conn_pt_soad.ports['pv'], solar.ports['pv'])
system.connect_ports_and_create_edge(elec_conn_pt_soad.ports['heat_pump'], heat_pump_soad.ports['heat_pump'])
system.connect_ports_and_create_edge(elec_conn_pt_soad.ports['kiln'], elec_kiln.ports['kiln'])

# Gas connections
system.connect_ports_and_create_edge(bulk_gas.ports['gas'], gas_cp.ports['bulk'])
system.connect_ports_and_create_edge(gas_cp.ports['soad'], gas_cp_soad.ports['cp'])
system.connect_ports_and_create_edge(gas_cp_soad.ports['b1'], boiler1_soad.ports['b1'])
system.connect_ports_and_create_edge(gas_cp_soad.ports['b2'], boiler2_soad.ports['b2'])
system.connect_ports_and_create_edge(gas_cp_soad.ports['kiln'], gas_kiln.ports['kiln'])


### School of Music (SoM)

# Electrical assets
elec_conn_pt_som = ElectricalTellegenNode()
metered_cp = ElectricalDemand()
metered_cp.add_demand_profile_from_array(df_elec_new['SoM_kW'].values, expansion_periods=expansion_intervals)
elec_conn_pt_som.ports['cp'] = metered_cp
elec_conn_pt_som.add_named_electrical_ports(['chiller', 'other'])
labels[elec_conn_pt_som] = 'som_elec_cp'

chiller = Node()
ch = ElectricalPort()
chiller.ports['chiller'] = ch
labels[chiller] = 'som_chiller'

other = Node()
ot = ElectricalPort()
other.ports['other'] = ot
labels[other] = 'som_other_elec'

# Gas assets
gas_cp_som = GasTellegenNode()
gas_cp_som.ports['cp'] = GasDemand()
gas_cp_som.ports['cp'].add_demand_profile_from_array(df_gas['SoM_Gj'].values/interval_duration, expansion_intervals)
gas_cp_som.ports['som'] = GasPort()
gas_cp_som.ports['pk'] = GasPort()
labels[gas_cp_som] = 'som_gas_cp'

som_boiler = Node()
som_b = GasPort()
som_boiler.ports['som'] = som_b
labels[som_boiler] = 'som_boiler1'

pk_boiler = Node()
pk_b = GasPort()
pk_boiler.ports['pk'] = pk_b
labels[pk_boiler] = 'som_boiler2'

# Add assets and do connections
system.add_node_obj([elec_conn_pt_som,
                     gas_cp_som,
                     chiller,
                     som_boiler,
                     pk_boiler,
                     other])

# Electrical connections

system.connect_ports_and_create_edge(connection_point.ports['som'], elec_conn_pt_som.ports['cp'])
system.connect_ports_and_create_edge(elec_conn_pt_som.ports['chiller'], chiller.ports['chiller'])
system.connect_ports_and_create_edge(elec_conn_pt_som.ports['other'], other.ports['other'])

# Gas connections
system.connect_ports_and_create_edge(gas_cp.ports['som'], gas_cp_som.ports['cp'])
system.connect_ports_and_create_edge(gas_cp_som.ports['som'], som_boiler.ports['som'])
system.connect_ports_and_create_edge(gas_cp_som.ports['pk'], pk_boiler.ports['pk'])

opt_build_start = time_.time()
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=num_intervals,
                          number_of_expansion_intervals=expansion_intervals,
                          discount_rate=0,
                          ES=system,
                          objective_set=None,
                          optimiser_engine='cplex')
print('Time to build optimiser: ', time_.time() - opt_build_start)
opt_start_time = time_.time()
optimiser.optimise(tee=True)
print('Time to run optimiser: ', time_.time() - opt_start_time)


# Plot results
fig = plt.figure(figsize=(14, 14))
fig.add_subplot(3, 1, 1)
hrs = df_gas['datetime'].values
myFmt = mdate.DateFormatter('%m')

plt.plot(hrs, optimiser.values(elec_conn_pt_soad.ports['cp'].port_name, 0))
plt.plot(hrs, optimiser.values(elec_conn_pt_som.ports['cp'].port_name, 0))
plt.plot(hrs, optimiser.values(pv.port_name, 0))
plt.gca().xaxis.set_major_formatter(myFmt)
plt.xticks(rotation=45)
plt.ylabel('kW')
plt.autoscale(enable=True, axis='x', tight=True)
plt.legend(['meter_soad', 'meter_som', 'solar_soad'])
plt.title('elec-2021, gas-2019')

fig.add_subplot(3, 1, 2)

plt.plot(hrs, optimiser.values(gas_cp_soad.ports['cp'].port_name, 0))
plt.plot(hrs, optimiser.values(gas_cp_som.ports['cp'].port_name, 0))
plt.gca().xaxis.set_major_formatter(myFmt)
plt.xticks(rotation=45)
plt.autoscale(enable=True, axis='x', tight=True)
plt.legend(['gas_meter_soad', 'gas_meter_som'])
plt.ylabel('GJ/s')

fig.add_subplot(3, 1, 3)
plt.plot(hrs, optimiser.values(bulk_gas.ports['emissions'].port_name, 0)*-1)
plt.gca().xaxis.set_major_formatter(myFmt)
plt.xticks(rotation=45)
plt.autoscale(enable=True, axis='x', tight=True)
plt.ylabel('Instantaneous emissions (kg CO2e)')

gas_total = sum(optimiser.values(bulk_gas.ports['gas'].port_name, 0))*-1
emissions_total = sum(optimiser.values(bulk_gas.ports['emissions'].port_name, 0))*-1
#print(gas_total)
print('Total kgCO2e emissions: ', emissions_total)
#print(gas_total*bulk_gas.emission_factor)


# fig = plt.figure(figsize=(14, 7))
# nx.draw(system, labels=labels, with_labels=True, node_color=(1,0.5,1))
