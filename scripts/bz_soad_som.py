from __future__ import division
import matplotlib.pyplot as plt
import matplotlib.dates as mdate
import numpy as np
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints
import networkx as nx
import pandas as pd


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

def clean_dataframe(df, data_col, data_name):
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
power_data = clean_dataframe(som_power_df, power_col[0], 'power')

temp_col = [col for col in som_boiler1_df.columns if 'Flow-Temp' in col]
boiler1_data = clean_dataframe(som_boiler1_df, temp_col[0], 'b1_temp')

temp_col = [col for col in som_boiler2_df.columns if 'Flow-Temp' in col]
boiler2_data = clean_dataframe(som_boiler2_df, temp_col[0], 'b2_temp')

solar_col = [col for col in soad_solar_df.columns if 'Power' in col]
soad_solar_data = clean_dataframe(soad_solar_df, solar_col[0], 'pv')

all_dfs = [power_data, boiler1_data, boiler2_data, soad_solar_data]
df_merged = all_dfs[0]
i = 0
for df_ in all_dfs[1:]:
    df_merged = df_merged.merge(df_, on='time', suffixes=(None, df_.columns[-1]))
    i += 1

# Do time period calcs

num_intervals = len(df_merged)
interval_duration = 5
expansion_intervals = 1

# Initialise graph
system = OptimisationGraph()

# Whole system nodes
bulk_grid = BulkGrid()
bulk_gas = BulkGas()

connection_point = ElectricalTellegenNode()
connection_point.add_named_electrical_ports(['grid', 'soad', 'som'])

gas_cp = GasTellegenNode()
gas_cp.ports['bulk'] = GasPort()
gas_cp.ports['soad'] = GasPort()
gas_cp.ports['som'] = GasPort()

### School of Art and Design (SoAD)

# Electrical assets
elec_conn_pt_soad = ElectricalTellegenNode()
elec_conn_pt_soad.add_named_electrical_ports(['cp', 'heat_pump', 'pv', 'kiln'])

elec_kiln = Node()
ek = ElectricalPort()
elec_kiln.ports['kiln'] = ek

heat_pump_soad = Node()
hp_soad = ElectricalPort()
heat_pump_soad.ports['heat_pump'] = hp_soad

solar = Node()
pv = ElectricalGeneration()
pv.add_generation_profile_from_array(df_merged['pv'].values*-1, expansion_intervals)
solar.ports['pv'] = pv

# Gas assets
gas_cp_soad = GasTellegenNode()
gas_cp_soad.ports['cp'] = GasPort()
gas_cp_soad.ports['b1'] = GasPort()
gas_cp_soad.ports['b2'] = GasPort()
gas_cp_soad.ports['kiln'] = GasPort()

boiler1_soad = Node()
b1_soad = GasPort()
b1_soad.set_flow_constraints(max_import=None, max_export=None)
boiler1_soad.ports['b1'] = b1_soad

boiler2_soad = Node()
b2_soad = GasPort()
b2_soad.set_flow_constraints(max_import=None, max_export=None)
boiler2_soad.ports['b2'] = b2_soad

gas_kiln = Node()
gk = GasPort()
gas_kiln.ports['kiln'] = gk


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
metered_cp.add_demand_profile_from_array(df_merged['power'].values, expansion_periods=expansion_intervals)
elec_conn_pt_som.ports['cp'] = metered_cp
elec_conn_pt_som.add_named_electrical_ports(['chiller', 'other'])

chiller = Node()
ch = ElectricalPort()
chiller.ports['chiller'] = ch

other = Node()
ot = ElectricalPort()
other.ports['other'] = ot

# Gas assets
gas_cp_som = GasTellegenNode()
gas_cp_som.ports['cp'] = GasPort()
gas_cp_som.ports['som'] = GasPort()
gas_cp_som.ports['pk'] = GasPort()

som_boiler = Node()
som_b = GasPort()
som_b.set_flow_constraints(max_import=None, max_export=None)
som_boiler.ports['som'] = som_b

pk_boiler = Node()
pk_b = GasPort()
pk_b.set_flow_constraints(max_import=None, max_export=None)
pk_boiler.ports['pk'] = pk_b

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

# nx.draw(system)

optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=num_intervals,
                          number_of_expansion_intervals=expansion_intervals,
                          discount_rate=0,
                          ES=system,
                          objective_set=None,
                          optimiser_engine='cplex')

optimiser.optimise(tee=True)

# Plot results
fig = plt.figure(figsize=(14, 7))
hrs = df_merged['time'].values
myFmt = mdate.DateFormatter('%H:%M:%S')
# for _, node in system.node_obj.items():
#     for _, p in node.ports.items():
#         if hasattr(p, 'port_name'):
#             plt.plot(hrs, optimiser.values(p.port_name, 0))

plt.plot(hrs, optimiser.values(elec_conn_pt_soad.ports['cp'].port_name, 0))
plt.plot(hrs, optimiser.values(elec_conn_pt_som.ports['cp'].port_name, 0))
plt.plot(hrs, optimiser.values(pv.port_name, 0))

plt.gca().xaxis.set_major_formatter(myFmt)
plt.xticks(rotation=45)
plt.autoscale(enable=True, axis='x', tight=True)
plt.legend(['meter_soad', 'meter_som', 'solar_soad'])







