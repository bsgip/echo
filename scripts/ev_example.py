from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.core import Var
from pyomo.util.infeasible import log_infeasible_constraints

import sys

from objectives import ObjectiveSet, ThroughputCost, PeakPositivePower

sys.path.append("../")
from echo_models import *
from echo_optimiser import EchoOptimiser
from configuration import *
from objectives import *
from networkx import Graph, draw

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

# The load and pv arrays below are in kwh consumed per 15 minutes
test_load = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 2.05, 2.19])

test_pv = 2 * np.array(
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.23, 0.52,
     0.74, 0.71, 0.63, 0.68, 0.97, 0.01, 0.52, 0.83, 0.83, 0.79, 1.22, 1.36, 1.27, 1.42, 1.97, 2.56, 2.91, 3.24,
     3.8, 4.3, 4.62, 4.84, 4.6, 4.17, 3.77, 3.76, 3.38, 2.64, 1.96, 1.76, 1.85, 2.4, 3.82, 5.13, 4.97, 5.02, 5.43,
     5.32, 3.56, 1.75, 1.43, 1.65, 1.69, 2.3, 2.71, 2.41, 2.63, 2.6, 1.9, 0.78, 0.13, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
     0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
test_pv *= -1  # convert solar generation to negative to match convention.

# Tariffs are in $ / kwh
import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff_array = np.array(([0.0] * 96))

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

## Set up hyper params
time_periods = len(test_load)
interval_duration = 15
expansion_periods = 1
discount_rate = 0

# Create graph
system = OptimisationGraph()

# Create assets
grid = Node()
grid.add_named_electrical_ports(['grid'])

connection_point = ElectricalTellegenNode()
connection_point.add_named_electrical_ports(['load', 'ev1', 'ev2', 'grid'])
connection_point.ports['ev1'].set_flow_constraints(max_import=7.5, max_export=-7.5)
connection_point.ports['ev2'].set_flow_constraints(max_import=7.5, max_export=-7.5)

load = Node()
l1 = ElectricalDemand()
l1.add_demand_profile_from_array(test_load, expansion_periods)
load.ports['load'] = l1

# Create vehicle 1
available1 = np.array([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24)
usage1 = np.array([0.0]*24 + [0.5]*24 + [0.0]*24 + [1.0]*24)

ev1_cp = ElectricalTellegenNode()
ev1_cp.add_named_electrical_ports(['cp', 'ev', 'usage'])
ev1_cp.ports['cp'].add_active_periods_from_array(available1, expansion_periods)

ev1 = ElectricalStorage(max_capacity=40.0,
                        depth_of_discharge_limit=0,
                        charging_power_limit=10,
                        discharging_power_limit=-10,
                        charging_efficiency=1,
                        discharging_efficiency=1,
                        initial_state_of_charge=0.0)

vehicle1 = Node()
vehicle1.ports['ev'] = ev1

trip1 = Node()
us1 = ElectricalDemand()
us1.add_demand_profile_from_array(usage1, expansion_periods=expansion_periods)
trip1.ports['usage'] = us1

# Create vehicle 2
available2 = np.array([1]*10 + [0]*10 + [1]*28 + [0]*48)
usage2 = np.array([0.0]*10 + [0.4]*10 + [0.0]*28 + [0.5]*48)

ev2_cp = ElectricalTellegenNode()
ev2_cp.add_named_electrical_ports(['cp', 'ev', 'usage'])
ev2_cp.ports['cp'].add_active_periods_from_array(available2, expansion_periods)

ev2 = ElectricalStorage(max_capacity=40.0,
                        depth_of_discharge_limit=0,
                        charging_power_limit=10,
                        discharging_power_limit=-10,
                        charging_efficiency=1,
                        discharging_efficiency=1,
                        initial_state_of_charge=0.0)

vehicle2 = Node()
vehicle2.ports['ev'] = ev2

trip2 = Node()
us2 = ElectricalDemand()
us2.add_demand_profile_from_array(usage2, expansion_periods=expansion_periods)
trip2.ports['usage'] = us2

# Add nodes to graph object
system.add_node_obj([grid, load, ev1_cp, ev2_cp, vehicle1, vehicle2, trip1, trip2, connection_point])

# Create edge objects and add to graph
system.connect_ports_and_create_edge(connection_point.ports['ev1'], ev1_cp.ports['cp'])
system.connect_ports_and_create_edge(ev1_cp.ports['ev'], ev1)
system.connect_ports_and_create_edge(ev1_cp.ports['usage'], us1)

system.connect_ports_and_create_edge(connection_point.ports['ev2'], ev2_cp.ports['cp'])
system.connect_ports_and_create_edge(ev2_cp.ports['ev'], ev2)
system.connect_ports_and_create_edge(ev2_cp.ports['usage'], us2)

system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['load'], load.ports['load'])

# Create objectives/tariffs
import_tariff = ImportTariff(component=connection_point.ports['grid'],
                             tariff_array=import_tariff_array,
                             expansion_periods=expansion_periods)

throughput_cost = ThroughputCost(component=ev1, rate=0.000001)

objective_set = ObjectiveSet(objective_list=[throughput_cost, import_tariff])


############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=objective_set)

optimiser.optimise()

log_infeasible_constraints(optimiser.model)


############################ Analyse the Optimisation ########################################

storage_energy_delta = optimiser.values(ev1.port_name, 0)
storage_energy_soc = optimiser.values(ev1.soc_value, 0)
optimised_connection_point_load = optimiser.values(connection_point.ports['grid'].port_name, 0)

colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(4, 1, 1)
line1, = ax1.plot(hrs, test_load, color=colors[0])
line2, = ax1.plot(hrs, test_pv, color=colors[1])
line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'Connection Point'], ncol=3)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(4, 1, 2)
line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])

ax3 = fig.add_subplot(4, 1, 3)
line1, = ax3.plot(hrs, usage1, color=colors[1])
line2, = ax3.plot(hrs, usage2, color=colors[2])

ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel('hour'), ax3.set_ylabel('Trip usage (kW)')
ax3.legend([line1, line2], ['EV1 usage', 'EV2 usage'])

ax3 = fig.add_subplot(4, 1, 4)
line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
line3, = ax3.plot(hrs, optimiser.values(ev2.port_name, 0), color=colors[3])
line4, = ax3.plot(hrs, optimiser.values(ev2.soc_value, 0), color=colors[4])

ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
ax3.legend([line1, line2, line3, line4], ['EV1 Charging action (kW)', 'EV1 SOC (kWh)','EV2 Charging action (kW)', 'EV2 SOC (kWh)'])
