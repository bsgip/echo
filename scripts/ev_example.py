from __future__ import division

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pyomo.core import Var
from pyomo.util.infeasible import log_infeasible_constraints

import sys

from echo.objectives import ObjectiveSet, ThroughputCost, PeakPositivePower

from echo.echo_models import *
from echo.echo_optimiser import EchoOptimiser
from echo.configuration import *
from echo.objectives import *
from networkx import Graph, draw


"""
        Example of optimising the charging of two evs, where there is also a load at the site
"""

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

# The load and pv arrays below are in average kw consumed per 15 minutes
# define load (loads must be positive values)
test_load = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 2.2, 2.15, 2.02, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 2.05, 2.19])


# Tariffs are in $ / kwh
import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff_array = np.array(([0.0] * 96))

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

## Set up hyper params
time_periods = len(test_load)   # number of time periods to run the optimisation for
interval_duration = 15          # each time period is 15 mins long
expansion_periods = 1           # not yet implemented leave as 1
discount_rate = 0               # not yet implemented leave as 0

# Create graph
system = OptimisationGraph()

# Create assets
grid = Node()                                   # create node representing upstream grid
grid.add_named_electrical_ports(['grid'])       # create a port which will be used to connect this with the connection_point

# create the connection point (where we will sum everything up)
connection_point = ElectricalTellegenNode()
connection_point.add_named_electrical_ports(['load', 'ev1', 'ev2', 'grid'])  # create ports to connect to the grid, the load, and the inverter
# set constraints on how power can flow from connection point to the evs
# i.e. export here would be exporting from grid to the ev battery
# and import would be from the ev to the grid
# hence this is possibly the opposite of what you might think. A more intuitive
# place for constraints on ev charging is found later
connection_point.ports['ev1'].set_flow_constraints(max_import=7.5, max_export=-7.5)
connection_point.ports['ev2'].set_flow_constraints(max_import=7.5, max_export=-5.)

load = Node()                       # create a node to represent the load
l1 = ElectricalDemand()             # create an electrical demand to attach to this node
l1.add_demand_profile_from_array(test_load, expansion_periods)
load.ports['load'] = l1             # add the electrical demand to a port of the load node

# create the evs
# each ev consists of three nodes, a connecting node, a usage (electrical demand),
# and a storage node.

# Create vehicle 1
available1 = np.array([1] * 24 + [0] * 24 + [1] * 24 + [0] * 24)    # bool when at charger
usage1 = np.array([0.0]*24 + [0.5]*24 + [0.0]*24 + [1.0]*24)        # kw average during use

ev1_cp = ElectricalTellegenNode()       # create teh connecting point
ev1_cp.add_named_electrical_ports(['cp', 'ev', 'usage'])    # create the ports required
# allow the connecting point to only be actively conencted to the grid when the vehicle is available
ev1_cp.ports['cp'].add_active_periods_from_array(available1, expansion_periods)

# create the electrical storage
ev1 = ElectricalStorage(max_capacity=40.0,              # max capacity of battery in kwh
                        depth_of_discharge_limit=0,     # allowable depth of discharge in range [0,100] (i.e. percent)
                        charging_power_limit=10,        # max charging rate in kW
                        discharging_power_limit=-10,    # max discharging rate in kW
                        charging_efficiency=1,          # charging efficiency in range [0,1]
                        discharging_efficiency=1,       # discharging efficiency in range [0,1]
                        initial_state_of_charge=10)     # initial state of charge in kWh

# create a node to connect this storage to
vehicle1 = Node()
# hacky implemetnation of ev user conservativeness while plugged in
vehicle1.ports['ev'] = ev1
# next few setting are to replicate a conservative user who wants to keep a mininum SOC while plugged in
vehicle1.ports['ev'].soc_conserv = 20.  # set a value that the user wants the battery to stay above while plugged in (kWh)
vehicle1.ports['ev'].soc_conserv_cost = 100.    # set the cost above which the user would be willing to let it go below this
vehicle1.ports['ev'].available = available1     # set the availability for the conservative value (i.e. needs to know when plugged in)
# next setting is to deal with infeasible trip data
vehicle1.ports['ev'].enable_trip_slack = False  # make true to allow infeasible trips to be public charged


# create a node for the usage
trip1 = Node()
us1 = ElectricalDemand()    # create an electrical demand object for this
us1.add_demand_profile_from_array(usage1, expansion_periods=expansion_periods)
trip1.ports['usage'] = us1

# craete a second vehicle (same options)
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
vehicle2.ports['ev'].enable_trip_slack = False

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
# create an import tariff
import_tariff = ImportTariff(component=connection_point.ports['grid'],
                             tariff_array=import_tariff_array,
                             expansion_periods=expansion_periods)

# add a throughput cost to the ev battery
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
line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line3], ['Load', 'Connection Point'], ncol=3)
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
plt.show()