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

# Example problem - 2 separate hubs (loads/sites) supplied from a single supply point that is connected to the grid.
# Site 1 has a load + pv
# Site 2 has the same load + pv

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

# Site 1
net_load = test_load + test_pv
# split load into import and export, so we can have load = import, and solar = export.
connection_point_import = np.copy(net_load)
connection_point_export = np.copy(net_load)

for j, e in enumerate(net_load):
    if e >= 0:
        connection_point_export[j] = 0

    else:
        connection_point_import[j] = 0

# Tariffs are in $ / kwh
import_tariff = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff = np.array(([0.0] * 96))

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

## Set up graph and parameters
expansion_periods = 1
discount_rate = 0

ES = OptimisationGraph()
ES.expansion_periods = expansion_periods

grid = Node()

g = ElectricalPort()
grid.ports['grid'] = g


battery1 = Node()

b1 = ElectricalStorage(max_capacity=15.0,
                       depth_of_discharge_limit=0,
                       charging_power_limit=1.25,
                       discharging_power_limit=-1.25,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       initial_state_of_charge=0.0)
battery1.ports['battery_asset'] = b1


load1 = Node()

l1 = ElectricalDemand()
l1.add_demand_profile_from_array(connection_point_import, expansion_periods)
load1.ports['demand'] = l1

solar1 = Node()

pv1 = ElectricalGeneration()
pv1.add_generation_profile_from_array(connection_point_export, expansion_periods)
solar1.ports['solar'] = pv1

site1 = ElectricalNode()
site1.node_rule = NodeRule.Tellegen
cp1 = ElectricalPort()
site1.ports['CP'] = cp1
site1.add_named_electrical_ports(['loadCP', 'bessCP', 'pvCP'])

ES.add_node_obj([grid, battery1, load1, solar1, site1])

# Create edge objects
bess_edge1 = Edge(vertices=[site1.ports['bessCP'], b1])
load_edge1 = Edge(vertices=[site1.ports['loadCP'], l1])
pv_edge1 = Edge(vertices=[site1.ports['pvCP'], pv1])
grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

ES.add_edge_obj([bess_edge1, load_edge1, pv_edge1, grid_edge])

# Testing settings

# battery_to_load = [battery1, site1, load1]
# path_tariff = PathTariff(component=battery_to_load,
#                          tariff_array=[0.1] * 96,
#                          expansion_periods=expansion_periods)

it = ImportTariff(component=site1.ports['CP'],
                             tariff_array=import_tariff,
                             expansion_periods=expansion_periods)
et = ExportTariff(component=site1.ports['CP'],
                             tariff_array=export_tariff,
                             expansion_periods=expansion_periods)

throughput_cost = ThroughputCost(component=b1, rate=0.009)

objective_set = ObjectiveSet(objective_list=[it, et, throughput_cost])

############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(interval_duration=15,
                          number_of_intervals=96,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=ES,
                          objective_set=objective_set)

optimiser.optimise()

log_infeasible_constraints(optimiser.model)


############################ Analyse the Optimisation ########################################

storage_energy_delta = optimiser.values(b1.port_name, 0)
optimised_connection_point_load = optimiser.values(cp1.port_name, 0)

colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(3, 1, 1)
line1, = ax1.plot(hrs, test_load, color=colors[0])
line2, = ax1.plot(hrs, test_pv, color=colors[1])
line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'Connection Point'], ncol=3)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(3, 1, 2)
line1, = ax2.plot(hrs, import_tariff, color=colors[3])
line2, = ax2.plot(hrs, export_tariff, color=colors[4])
ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])

ax3 = fig.add_subplot(3, 1, 3)
line1, = ax3.plot(hrs, optimiser.values(b1.port_name, 0), color=colors[1])
line2, = ax3.plot(hrs, optimiser.values(b1.soc_value, 0), color=colors[2])
ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])

if ES.paths:

    grid_to_load = optimiser.values(ES.path_obj[(grid, site1, load1)].flow_value,0)
    grid_to_bess = optimiser.values(ES.path_obj[(grid, site1, battery1)].flow_value,0)
    bess_to_load = optimiser.values(ES.path_obj[(battery1, site1, load1)].flow_value,0)
    bess_to_grid = optimiser.values(ES.path_obj[(battery1, site1, grid)].flow_value,0)
    pv_to_load = optimiser.values(ES.path_obj[(solar1, site1, load1)].flow_value,0)
    pv_to_bess = optimiser.values(ES.path_obj[(solar1, site1, battery1)].flow_value,0)
    pv_to_grid = optimiser.values(ES.path_obj[solar1, site1, grid].flow_value,0)

    grid_to_pv = optimiser.values(ES.path_obj[(grid, site1, solar1)].flow_value,0)
    bess_to_pv = optimiser.values(ES.path_obj[(battery1, site1, solar1)].flow_value,0)
    load_to_pv = optimiser.values(ES.path_obj[load1, site1, solar1].flow_value,0)
    load_to_grid = optimiser.values(ES.path_obj[load1, site1, grid].flow_value,0)
    load_to_bess = optimiser.values(ES.path_obj[load1, site1, battery1].flow_value,0)

    fig = plt.figure(figsize=(14, 7))
    ax1 = fig.add_subplot(4, 1, 1)
    line1, = ax1.plot(hrs, grid_to_load + bess_to_load + pv_to_load, color=colors[0])
    line2, = ax1.plot(hrs, load_to_bess + load_to_grid + load_to_pv, color=colors[1])
    line3, = ax1.plot(hrs, load_to_bess + load_to_grid + load_to_pv -(grid_to_load + bess_to_load + pv_to_load), color=colors[2])
    line4, = ax1.plot(hrs, connection_point_import*-1, color=colors[3])
    ax1.lines[3].set_linestyle("--")
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1, line2, line3, line4], ['Flows to load', 'Flows from load', 'Sum of flows', 'Load'])
    ax1.set_xlim([0, len(test_load) / 4])

    ax1 = fig.add_subplot(4, 1, 2)
    line1, = ax1.plot(hrs, grid_to_bess + pv_to_bess + load_to_bess, color=colors[0])
    line2, = ax1.plot(hrs, bess_to_grid + bess_to_load + bess_to_pv, color=colors[1])
    line3, = ax1.plot(hrs, bess_to_grid + bess_to_load + bess_to_pv - (grid_to_bess + pv_to_bess + load_to_bess), color=colors[2])
    line4, = ax1.plot(hrs, optimiser.values(b1.port_name, 0)*-1, color=colors[3])
    ax1.lines[3].set_linestyle("--")
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1, line2, line3, line4], ['Flows to bess', 'Flows from bess', 'Sum of flows', 'Bess'])
    ax1.set_xlim([0, len(test_load) / 4])

    ax1 = fig.add_subplot(4, 1, 3)
    line1, = ax1.plot(hrs, bess_to_pv + grid_to_pv + load_to_pv, color=colors[0])
    line2, = ax1.plot(hrs, pv_to_load + pv_to_bess + pv_to_grid, color=colors[1])
    line3, = ax1.plot(hrs, pv_to_load + pv_to_bess + pv_to_grid - (bess_to_pv + grid_to_pv + load_to_pv), color=colors[2])
    line4, = ax1.plot(hrs, connection_point_export*-1, color=colors[3])
    ax1.lines[3].set_linestyle("--")
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1, line2, line3, line4], ['Flows to pv', 'Flows from pv', 'Sum of flows', 'PV'])
    ax1.set_xlim([0, len(test_load) / 4])

    ax1 = fig.add_subplot(4, 1, 4)
    line1, = ax1.plot(hrs, bess_to_grid + pv_to_grid + load_to_grid, color=colors[0])
    line2, = ax1.plot(hrs, grid_to_load + grid_to_pv + grid_to_bess, color=colors[1])
    line3, = ax1.plot(hrs, grid_to_load + grid_to_pv + grid_to_bess - (bess_to_grid + pv_to_grid + load_to_grid), color=colors[2])
    line4, = ax1.plot(hrs, optimiser.values(grid.ports['grid'].port_name, 0)*-1, color=colors[3])
    ax1.lines[3].set_linestyle("--")
    ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
    ax1.legend([line1, line2, line3, line4], ['Flows to grid', 'Flows from grid', 'Sum of flows', 'Grid'])
    ax1.set_xlim([0, len(test_load) / 4])
