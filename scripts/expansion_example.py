from __future__ import division

import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints

from echo.echo_optimiser import EchoOptimiser
from echo.objectives import *

""" 
            Example of optimising a behind the meter battery where there is also a load and pv at the location

             our graph is going to look like

                   grid----connection_point----|----load
                                               |----inverter----|----battery
                                                                |----pv

"""

# set up seaborn the way you like
sns.set_style({'axes.linewidth': 1, 'axes.edgecolor': 'black', 'xtick.direction': \
    'out', 'xtick.major.size': 4.0, 'ytick.direction': 'out', 'ytick.major.size': 4.0, \
               'axes.facecolor': 'white', 'grid.color': '.8', 'grid.linestyle': u'-', 'grid.linewidth': 0.5})

############################ Define an Example Optimisation Problem ########################################

# The load and pv arrays below are in average kw consumed per 15 minutes
# define load (loads must be positive values)
test_load = np.array(
    [2.13, 2.09, 2.3, 2.11, 2.2, 2.23, 15, 15, 15, 2.19, 2.19, 2.19, 2.12, 2.15, 2.25, 2.12, 2.21, 2.16,
     2.26, 2.13, 2.08, 2.15, 2.42, 2.02, 2.3, 2.26, 2.35, 2.55, 3.23, 2.98, 3.49, 3.5, 3.12, 3.52, 3.94, 3.55,
     3.99, 3.71, 3.38, 3.76, 3.71, 3.78, 3.29, 3.65, 3.61, 3.75, 3.38, 3.66, 3.56, 3.69, 3.3, 3.61, 3.71, 3.82,
     3.17, 3.69, 3.74, 3.86, 3.57, 3.55, 3.75, 3.6, 3.67, 3.48, 3.51, 3.46, 3.19, 3.38, 3.19, 3.38, 3.04, 3.12,
     2.91, 3.11, 3.13, 2.77, 2.24, 2.54, 2.24, 2.24, 2.09, 2.33, 2.17, 2.16, 1.97, 2.16, 2.21, 2.18, 2.01, 2.16,
     2.19, 2.11, 2.17, 2.13, 12, 12])

# define PV, generation is negative values
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
time_periods = len(test_load)  # number of time periods to run the optimisation for
interval_duration = 15  # each time period is 15 mins long
expansion_periods = 2  # not yet implemented leave as 1
discount_rate = 0  # not yet implemented leave as 0

# Create graph in echo
system = OptimisationGraph()

# Create assets
grid = Node()  # create node representing upstream grid
grid.add_electrical_ports_from_list(
    ['grid'])  # create a port which will be used to connect this with the connection_point

connection_point = TellegenNode()  # create the connection point
connection_point.add_electrical_ports_from_list(
    ['load', 'inv', 'grid'])  # create ports to connect to the grid, the load, and the inverter


load = Node()  # create a node to represent the load
l1 = ElectricalDemand()  # create an electrical demand to attach to this node
l1.add_demand_profile_from_array(test_load, expansion_periods)
load.ports['load'] = l1  # add the electrical demand to a port of the load node

# create an inverter node with some properties,
# if the constraints are not none then they should be max_export <= 0 <= max_import
# can also set efficiency on the dc and the ac side in the range 0-1
inverter = Inverter(max_import=None, max_export=None, dc_ac_efficiency=1, ac_dc_efficiency=1)
inverter.add_ac_port('inv')  # add a port that is used to connect back to the connection_point
inverter.add_dc_port('bess')  # add a port to connect to the battery
inverter.add_dc_port('pv')  # add a port to connect to the pv

# create a node for the battery
battery = Node()
# create an electrical storage object
b = ElectricalStorage(max_capacity=15.0,  # max capacity of battery in kwh
                      depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
                      charging_power_limit=1.25,  # max charging rate in kW
                      discharging_power_limit=-1.25,  # max discharging rate in kW
                      charging_efficiency=1,  # charging efficiency in range [0,1]
                      discharging_efficiency=1,  # discharging efficiency in range [0,1]
                      initial_state_of_charge=0.0)  # initial state of charge in kWh
# connect the electrical storage to a port on the battery node
battery.ports['bess'] = b

battery_future = Node()
# create an electrical storage object
b_future = ElectricalStorage(max_capacity=0.0,  # max capacity of battery in kwh
                      depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
                      charging_power_limit=1.25,  # max charging rate in kW
                      discharging_power_limit=-1.25,  # max discharging rate in kW
                      charging_efficiency=1,  # charging efficiency in range [0,1]
                      discharging_efficiency=1,  # discharging efficiency in range [0,1]
                      initial_state_of_charge=0.0)  # initial state of charge in kWh
# connect the electrical storage to a port on the battery node
battery_future.ports['bess'] = b_future
inverter.add_dc_port('bess_future')

# create a node for the solar
solar = Node()
pv = ElectricalGeneration()  # create an electrical generation object
pv.curtailable = False  # set whether this can be curtailed or not
pv.add_generation_profile_from_array(test_pv, expansion_periods)
solar.ports['pv'] = pv  # add the electrical generation to a port on the solar node

# Populate graph with assets (nodes)
system.add_node_obj([grid, battery, load, solar, connection_point, inverter, battery_future])

# Add edges to graph (i.e. connect up the graph structure how we want it)
system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['load'], load.ports['load'])
system.connect_ports_and_create_edge(connection_point.ports['inv'], inverter.ports['inv'])
system.connect_ports_and_create_edge(inverter.ports['bess'], battery.ports['bess'])
system.connect_ports_and_create_edge(inverter.ports['pv'], solar.ports['pv'])
system.connect_ports_and_create_edge(inverter.ports['bess_future'], battery_future.ports['bess'])

# Create objectives/tariffs
throughput_cost = ThroughputCost(component=b, rate=0.000001)  # assign a throughput cost to the battery
peak_power_obj = PeakNegativePower(component=grid.ports['grid'])  # assign a cost on the peak negative power
import_cost = ImportTariff(component=connection_point.ports['grid'],
                           tariff_array=import_tariff_array,
                           expansion_periods=expansion_periods)  # create the import objective cost
import_cost2 = ImportTariff(component=connection_point.ports['grid'],
                            tariff_array=import_tariff_array,
                            expansion_periods=expansion_periods)  # create the import objective cost
export_cost = ExportTariff(component=connection_point.ports['grid'],
                           tariff_array=export_tariff_array,
                           expansion_periods=expansion_periods)  # create the export objective cost

objective_set = ObjectiveSet(objective_list=[import_cost, import_cost2, export_cost, peak_power_obj, throughput_cost])

############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=objective_set,
                          optimiser_engine='cplex')

optimiser.optimise(tee=True)

log_infeasible_constraints(optimiser.model)

############################ Analyse the Optimisation ########################################

storage_energy_delta = optimiser.values(b.port_name, 0)
storage_energy_soc = optimiser.values(b.soc_value, 0)
optimised_connection_point_load = optimiser.values(connection_point.ports['grid'].port_name, 0)

colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(3, 1, 1)
line1, = ax1.plot(hrs, test_load, color=colors[0])
line2, = ax1.plot(hrs, test_pv, color=colors[1])
# line3, = ax1.plot(hrs, optimised_connection_point_load,colocolors[2])
line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load', 'PV', 'aggregate'], ncol=2)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(3, 1, 2)
line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])

ax3 = fig.add_subplot(3, 1, 3)
line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
plt.show()

storage_energy_delta = optimiser.values(b.port_name, 1)
storage_energy_soc = optimiser.values(b.soc_value, 1)
optimised_connection_point_load = optimiser.values(connection_point.ports['grid'].port_name, 1)


colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(3, 1, 1)
line1, = ax1.plot(hrs, test_load, color=colors[0])
line2, = ax1.plot(hrs, test_pv, color=colors[1])
# line3, = ax1.plot(hrs, optimised_connection_point_load,colocolors[2])
line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
ax1.legend([line1, line2, line3], ['Load exp2', 'PV', 'aggregate'], ncol=2)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(3, 1, 2)
line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])

ax3 = fig.add_subplot(3, 1, 3)
line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
plt.show()