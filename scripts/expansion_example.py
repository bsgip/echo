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

############################ Optimise this Example ########################################

np.set_printoptions(suppress=True)

## Set up hyper params
time_periods = 12 # number of time periods to run the optimisation for
interval_duration = 60  # each time period is 15 mins long
expansion_periods = 2
discount_rate = 0  # not yet implemented leave as 0

# Create graph in echo
system = OptimisationGraph()

# Create assets
grid = Node()  # create node representing upstream grid
grid.add_electrical_ports_from_list(['grid'])

connection_point = TellegenNode()  # create the connection point
connection_point.add_electrical_ports_from_list(['load', 'inv', 'grid'])


load = Node()  # create a node to represent the load
l1 = ElectricalDemand()  # create an electrical demand to attach to this node
keys = generate_pyomo_indices(time_periods, expansion_periods)
l1.add_demand_profile_from_array([0]*time_periods + [30]*time_periods, keys=keys)
load.ports['load'] = l1  # add the electrical demand to a port of the load node


inverter = Inverter(max_import=None, max_export=None, dc_ac_efficiency=1, ac_dc_efficiency=1)
inverter.add_ac_port('inv')  # add a port that is used to connect back to the connection_point
inverter.add_dc_port('bess')  # add a port to connect to the battery

# create a node for the battery
battery = Node()
# create an electrical storage object
b = ElectricalStorage(max_capacity=10.0,  # max capacity of battery in kwh
                      depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
                      charging_power_limit=2,  # max charging rate in kW
                      discharging_power_limit=-2,  # max discharging rate in kW
                      charging_efficiency=1,  # charging efficiency in range [0,1]
                      discharging_efficiency=1,  # discharging efficiency in range [0,1]
                      initial_state_of_charge=0.0)  # initial state of charge in kWh
# connect the electrical storage to a port on the battery node
battery.ports['bess'] = b

battery_future = Node()
# create an electrical storage object
b_future = ElectricalStorage(max_capacity=10.0,  # max capacity of battery in kwh
                      depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
                      charging_power_limit=2,  # max charging rate in kW
                      discharging_power_limit=-2,  # max discharging rate in kW
                      charging_efficiency=1,  # charging efficiency in range [0,1]
                      discharging_efficiency=1,  # discharging efficiency in range [0,1]
                      initial_state_of_charge=0.0)  # initial state of charge in kWh
b_future.planning = True
b_future.install_cost = 50000  # $/unit capacity
# connect the electrical storage to a port on the battery node
battery_future.ports['bess'] = b_future
inverter.add_dc_port('bess_future')

# Populate graph with assets (nodes)
system.add_node_obj([grid, battery, load, connection_point, inverter, battery_future])

# Add edges to graph (i.e. connect up the graph structure how we want it)
system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports['load'], load.ports['load'])
system.connect_ports_and_create_edge(connection_point.ports['inv'], inverter.ports['inv'])
system.connect_ports_and_create_edge(inverter.ports['bess'], battery.ports['bess'])
system.connect_ports_and_create_edge(inverter.ports['bess_future'], battery_future.ports['bess'])

# Create objectives/tariffs
import_cost = ImportTariff(component=connection_point.ports['grid'],
                           tariff_array=[2]*6 + [1]*6,
                           expansion_periods=expansion_periods)  # create the import objective cost
import_cost.name = 'import_cost'

objective_set = ObjectiveSet(objective_list=[import_cost])

############################ ----------------------- ########################################

# Invoke the optimiser and optimise
optimiser = EchoOptimiser(interval_duration=interval_duration,
                          number_of_intervals=time_periods,
                          number_of_expansion_intervals=expansion_periods,
                          discount_rate=discount_rate,
                          ES=system,
                          objective_set=objective_set,
                          optimiser_engine='cplex')

optimiser.optimise(tee=False)

log_infeasible_constraints(optimiser.model)

print('total cost:', optimiser.get_total_objective_value())
print(optimiser.values(b_future.is_installed, 0))
print(optimiser.values(b_future.installed_when))
############################ Analyse the Optimisation ########################################

storage_energy_delta = optimiser.values(b.port_name, 0)
storage_energy_soc = optimiser.values(b.soc_value, 0)
optimised_connection_point_load = optimiser.values(connection_point.ports['grid'].port_name, 0)
#
# colors = sns.color_palette()
# hrs = np.arange(0, len(test_load)) / 4
# fig = plt.figure(figsize=(14, 7))
# ax1 = fig.add_subplot(3, 1, 1)
# line1, = ax1.plot(hrs, test_load, color=colors[0])
# line2, = ax1.plot(hrs, test_pv, color=colors[1])
# # line3, = ax1.plot(hrs, optimised_connection_point_load,colocolors[2])
# line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
# ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
# ax1.legend([line1, line2, line3], ['Load', 'PV', 'aggregate'], ncol=2)
# ax1.set_xlim([0, len(test_load) / 4])
#
# ax2 = fig.add_subplot(3, 1, 2)
# line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
# line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
# ax2.set_xlabel('hour'), ax2.set_ylabel('price')
# ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
# ax2.set_xlim([0, len(test_load) / 4])
#
# ax3 = fig.add_subplot(3, 1, 3)
# line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
# line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
# ax3.set_xlim([0, len(test_load) / 4])
# ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
# ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
# plt.show()
#
# storage_energy_delta = optimiser.values(b.port_name, 1)
# storage_energy_soc = optimiser.values(b.soc_value, 1)
# optimised_connection_point_load = optimiser.values(connection_point.ports['grid'].port_name, 1)
#
#
# colors = sns.color_palette()
# hrs = np.arange(0, len(test_load)) / 4
# fig = plt.figure(figsize=(14, 7))
# ax1 = fig.add_subplot(3, 1, 1)
# line1, = ax1.plot(hrs, test_load, color=colors[0])
# line2, = ax1.plot(hrs, test_pv, color=colors[1])
# # line3, = ax1.plot(hrs, optimised_connection_point_load,colocolors[2])
# line3, = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
# ax1.set_xlabel('hour'), ax1.set_ylabel('kW')
# ax1.legend([line1, line2, line3], ['Load exp2', 'PV', 'aggregate'], ncol=2)
# ax1.set_xlim([0, len(test_load) / 4])
#
# ax2 = fig.add_subplot(3, 1, 2)
# line1, = ax2.plot(hrs, import_tariff_array, color=colors[3])
# line2, = ax2.plot(hrs, export_tariff_array, color=colors[4])
# ax2.set_xlabel('hour'), ax2.set_ylabel('price')
# ax2.legend([line1, line2], ['buy price', 'sell price'], ncol=2)
# ax2.set_xlim([0, len(test_load) / 4])
#
# ax3 = fig.add_subplot(3, 1, 3)
# line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
# line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
# ax3.set_xlim([0, len(test_load) / 4])
# ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
# ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
# plt.show()