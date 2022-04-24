from __future__ import division

import datetime
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
df_elec = pd.read_excel("C:\\Users\\61405\\Documents\\BZ_data\\soad_som_combined_data.xlsx", sheet_name='Electricity_15min')
df_solar = pd.read_excel("C:\\Users\\61405\\Documents\\BZ_data\\soad_som_combined_data.xlsx", sheet_name='Solar_1hr')
df_gas = pd.read_excel("C:\\Users\\61405\\Documents\\BZ_data\\soad_som_combined_data.xlsx", sheet_name='Gas2')

def convert_to_datetime(df, date_col_name, time_col_name, date_fmt, time_fmt):
    times = df[time_col_name] # Pull out times
    dates = df[date_col_name]  # Pull out dates
    index = []  # for storing cleaned times
    for i in range(len(times)):
        if type(times[i]) is str:
            t = datetime.strptime(times[i], time_fmt)
        else:
            t = times[i]
        if type(dates[i]) is str:
            d = datetime.strptime(dates[i], date_fmt)
        else:
            d = dates[i]
        index.append(datetime(year=d.year,
                            month=d.month,
                            day=d.day,
                            hour=t.hour,
                            minute=t.minute,
                            second=t.second))

    df['datetime'] = index


# Convert dataframe timestamps to a consistent datetime column
convert_to_datetime(df_elec, 'Date', 'Time', None, None)
convert_to_datetime(df_gas, 'Date', 'Time', None, None)
convert_to_datetime(df_solar, 'Date', 'Time', '%Y-%m-%d', '%H:%M:%S')

# Downsample the electricity data to be hourly
df_elec_new = df_elec.set_index('datetime').resample(rule='1h').mean()
# todo there is something weird happening with the first entry

# Check dataframes are same length
assert (len(df_elec_new)==len(df_gas) and len(df_elec_new)==len(df_solar))

# Check times in timestamps are lined up (years won't be)
assert (df_elec_new.index.time == df_gas.set_index('datetime').index.time).all()
#assert (df_elec_new.index.time == df_solar.set_index('datetime').index.time).all()

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
pv = ElectricalGeneration()
pv.add_generation_profile_from_array(df_solar['Power (kW)'].values * -1, expansion_intervals)
solar.ports['pv'] = pv
labels[solar] = 'soad_solar'

# Gas assets
gas_cp_soad = GasTellegenNode()
gas_cp_soad.ports['cp'] = GasPort()
gas_cp_soad.ports['b1'] = GasPort()
gas_cp_soad.ports['b2'] = GasPort()
labels[gas_cp_soad] = 'soad_gas_cp'

boiler1_soad = Node()
b1_soad = GasDemand()
b1_soad.add_demand_profile_from_array(df_gas['SoA_Gj'].values/2, expansion_intervals)
boiler1_soad.ports['b1'] = b1_soad
labels[boiler1_soad] = 'soad_boiler1'

boiler2_soad = Node()
b2_soad = GasDemand()
b2_soad.add_demand_profile_from_array(df_gas['SoA_Gj'].values/2, expansion_intervals)
boiler2_soad.ports['b2'] = b2_soad
labels[boiler2_soad] = 'soad_boiler2'


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
                     boiler1_soad])

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


### School of Music (SoM)

# Electrical assets
elec_conn_pt_som = ElectricalTellegenNode()
metered_cp = ElectricalPort()
elec_conn_pt_som.ports['cp'] = metered_cp
elec_conn_pt_som.add_named_electrical_ports(['chiller', 'other'])
labels[elec_conn_pt_som] = 'som_elec_cp'

chiller = Node()
ch = ElectricalDemand()
ch.add_demand_profile_from_array(df_elec_new['SoM_kW'].values*3/4, 1)
chiller.ports['chiller'] = ch
labels[chiller] = 'som_chiller'

other = Node()
ot = ElectricalDemand()
ot.add_demand_profile_from_array(df_elec_new['SoM_kW'].values*1/4, 1)
other.ports['other'] = ot
labels[other] = 'som_other_elec'

# Gas assets
gas_cp_som = GasTellegenNode()
gas_cp_som.ports['cp'] = GasDemand()
gas_cp_som.ports['cp'].add_demand_profile_from_array(df_gas['SoM_Gj'].values, expansion_intervals)
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


# Tariffs
# Energy tariffs

# shoulder usage
# Shoulder is 9-5, 8-10 daily
shoulder_rate = 0.09
shoulder_window_daily = [0]*8 + [1]*8 + [0]*3 + [1]*2 + [0]*3
shoulder_tariff_array = np.array(shoulder_window_daily)*shoulder_rate

# off peak usage
# off peak is 7-9, 5-8 daily
off_peak_rate = 0.5
off_peak_window = [0]*24
off_peak_array = np.array(off_peak_window)*off_peak_rate

import_tariff_array = [0.5]*24

# Add these tariffs together
tariff_array = np.array(shoulder_tariff_array + off_peak_array + import_tariff_array).repeat(365)
import_tariff = ImportTariff(component=connection_point.ports['grid'],
                             tariff_array=tariff_array)

objective_set = ObjectiveSet(objective_list=[import_tariff])

opt_build_start = time_.time()
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=num_intervals,
                          number_of_expansion_intervals=expansion_intervals,
                          discount_rate=0,
                          ES=system,
                          objective_set=objective_set,
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
plt.title('Data: elec-2021, gas-2019, solar-2019')

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

print('Predicted total gas consumption: ', 5436)
print('Total gas consumption: ', sum(optimiser.values(gas_cp_soad.ports['cp'].port_name, 0)))
print('Total cost: ', optimiser.opt_status['Termination message'])


# fig = plt.figure(figsize=(14, 7))
# nx.draw(system, labels=labels, with_labels=True, node_color=(1,0.5,1))
