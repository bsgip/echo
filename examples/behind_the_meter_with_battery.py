import time

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import (ElectricalDemand, ElectricalGeneration,
                                    ElectricalStorage, Inverter)
from echo.models.scenario import EngineSettings, ScenarioSettings
from echo.objectives.base import ObjectiveSet
from echo.objectives.power import PeakNegativePower
from echo.objectives.tariff import ExportTariff, ImportTariff, ThroughputCost
from echo.optimiser import optimise

""" Optimising a behind-the-meter battery example

Usage:
    python btm_battery_example.py

    A load and pv are also connected resulting in this graph:

                       +------+
                    +--+ load |
+------+  +------+  |  +------+         +---------+
| grid +--+ C.P. +--+                +--+ battery |
+------+  +------+  |  +----------+  |  +---------+
                    +--+ inverter +--+
                       +----------+  |  +------+
                                     +--+ P.V. |
                                        +------+
"""

# ----------------------------------------------------------------------------------------------------------------------
#   1. Choose solver and solver options
# ----------------------------------------------------------------------------------------------------------------------

engine_settings = EngineSettings(
    engine="cplex",
    engine_executable="",
    bigM=5000000,  # This value has been arbitrarily chosen
    smallM=0.0001,  # This value has been arbitrarily chosen
)

# ----------------------------------------------------------------------------------------------------------------------
#   2. Define the scenario data
# ----------------------------------------------------------------------------------------------------------------------

duration_multiplication = 1

# The load and pv arrays below are in average kw consumed per 15 minutes
# define load (loads must be positive values)
data_df = pd.read_csv("examples/data.csv")
test_load = data_df["load"].to_numpy()

# convert solar generation to negative to match convention.
test_pv = -1 * 2 * data_df["solar"].to_numpy()

# Tariffs are in $ / kwh
import_tariff_array = np.array(
    ([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12) * duration_multiplication
)
export_tariff_array = np.array(([0.0] * 96 * duration_multiplication))

# Set up hyper parameters
time_periods = len(test_load)  # number of time periods to run the optimisation for
interval_duration = 15  # each time period is 15 mins long
expansion_periods = 1  # not yet implemented leave as 1
discount_rate = 0  # not yet implemented leave as 0
scenario_settings = ScenarioSettings(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=discount_rate,
)

# ----------------------------------------------------------------------------------------------------------------------
#   3. Define the nodes and edges
# ----------------------------------------------------------------------------------------------------------------------

# Create a node representing upstream grid
grid = Node(node_name="grid")
grid.add_port(
    "grid", FlexPort(units=Units.KW)
)  # create a port which will be used to connect this with the connection_point

# Create a connection point
connection_point = TellegenNode(node_name="cp")
connection_point.add_ports_from_list(
    ["load", "inv", "grid"], FlexPort, units=Units.KW
)  # create ports to connect to the grid, the load, and the inverter
# set flow constraints for the port that connects to the grid,
# such that         max_export <= 0 <= max_import
# set slack=True to allow the constraints to be violated if the optimisation problem would be infeasible otherwise
connection_point.ports["grid"].set_flow_constraints(max_import=15, max_export=-15, slack=True)
# todo: value of slack

# Create a load
load = Node(node_name="load")
l1 = ElectricalDemand()  # create an electrical demand to attach to this node
l1.add_demand_profile_from_array(test_load, expansion_periods)
load.ports["load"] = l1  # add the electrical demand to a port of the load node

# Create an inverter node with some properties,
# if the constraints are not none then they should be max_export <= 0 <= max_import
# can also set efficiency on the dc and the ac side in the range 0-1
inverter = Inverter(
    node_name="inv",
    max_import=None,
    max_export=None,
    dc_ac_efficiency=1,
    ac_dc_efficiency=1,
    ac_port_name="inv",
    dc_port_names=["bess", "pv"],
)

# Create a node for the battery
battery = Node(node_name="battery")
b = ElectricalStorage(
    max_capacity=15.0,  # max capacity of battery in kwh
    depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
    charging_power_limit=1.25,  # max charging rate in kW
    discharging_power_limit=-1.25,  # max discharging rate in kW
    charging_efficiency=1,  # charging efficiency in range [0,1]
    discharging_efficiency=1,  # discharging efficiency in range [0,1]
    initial_state_of_charge=0.0,
)  # initial state of charge in kWh
# connect the electrical storage to a port on the battery node
battery.ports["bess"] = b

# create a node for the solar panel
solar = Node(node_name="solar")
pv = ElectricalGeneration()  # create an electrical generation object
pv.curtailable = False  # set whether this can be curtailed or not
pv.add_generation_profile_from_array(test_pv, expansion_periods)
solar.ports["pv"] = pv  # add the electrical generation to a port on the solar node


# ----------------------------------------------------------------------------------------------------------------------
#   4. Build the optimisation graph
# ----------------------------------------------------------------------------------------------------------------------

network = OptimisationGraph()

# Populate graph with assets (nodes)
network.add_node_obj([grid, battery, load, solar, connection_point, inverter])

# Add edges to graph (i.e. connect up the graph structure how we want it)
network.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
network.connect_ports_and_create_edge(connection_point.ports["load"], load.ports["load"])
network.connect_ports_and_create_edge(connection_point.ports["inv"], inverter.ports["inv"])
network.connect_ports_and_create_edge(inverter.ports["bess"], battery.ports["bess"])
network.connect_ports_and_create_edge(inverter.ports["pv"], solar.ports["pv"])

# ----------------------------------------------------------------------------------------------------------------------
#   5. Define the objectives/tariffs
# ----------------------------------------------------------------------------------------------------------------------

# assign a throughput cost to the battery
throughput_cost = ThroughputCost(component=b, rate=0.000001)

# assign a cost on the peak negative power
peak_power_obj = PeakNegativePower(component=grid.ports["grid"])

# create the import objective cost
import_cost = ImportTariff(
    component=connection_point.ports["grid"],
    tariff_array=import_tariff_array,
    expansion_periods=expansion_periods,
)

# create the export objective cost
export_cost = ExportTariff(
    component=connection_point.ports["grid"],
    tariff_array=export_tariff_array,
    expansion_periods=expansion_periods,
)

objective_set = ObjectiveSet(objective_list=[import_cost, export_cost, peak_power_obj, throughput_cost])

# ----------------------------------------------------------------------------------------------------------------------
#   6. Perform the optimisation
# ----------------------------------------------------------------------------------------------------------------------

t1 = time.time()
optimise_results = optimise(
    scenario_settings=scenario_settings,
    engine_settings=engine_settings,
    graph=network,
    objective_set=objective_set,
)
t2 = time.time()
optimisation_time = t2 - t1

# ----------------------------------------------------------------------------------------------------------------------
#   7. Analyse the results of the optimisation
# ----------------------------------------------------------------------------------------------------------------------

np.set_printoptions(suppress=True)

print("optimisation time = ", optimisation_time)

log_infeasible_constraints(optimise_results.model)

storage_energy_delta = optimise_results.values(b.port_name, 0)
storage_energy_soc = optimise_results.values(b.soc_value, 0)
optimised_connection_point_load = optimise_results.values(connection_point.ports["grid"].port_name, 0)

# Set up seaborn (plotting) style
sns.set_style(
    {
        "axes.linewidth": 1,
        "axes.edgecolor": "black",
        "xtick.direction": "out",
        "xtick.major.size": 4.0,
        "ytick.direction": "out",
        "ytick.major.size": 4.0,
        "axes.facecolor": "white",
        "grid.color": ".8",
        "grid.linestyle": "-",
        "grid.linewidth": 0.5,
    }
)
colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4

# Create a figure that will have 3 subplots
fig = plt.figure(figsize=(14, 7))

# First subplot is load (kW)/pv (kw)/aggregate(load+pv) vs time (hr)
ax1 = fig.add_subplot(3, 1, 1)
(line1,) = ax1.plot(hrs, test_load, color=colors[0])
(line2,) = ax1.plot(hrs, test_pv, color=colors[1])
(line3,) = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel("hour"), ax1.set_ylabel("kW")
ax1.legend([line1, line2, line3], ["Load", "PV", "aggregate"], ncol=2)
ax1.set_xlim([0, len(test_load) / 4])

# Second subplot is buy/sell price vs time (hr)
ax2 = fig.add_subplot(3, 1, 2)
(line1,) = ax2.plot(hrs, import_tariff_array, color=colors[3])
(line2,) = ax2.plot(hrs, export_tariff_array, color=colors[4])
ax2.set_xlabel("hour"), ax2.set_ylabel("price")
ax2.legend([line1, line2], ["buy price", "sell price"], ncol=2)
ax2.set_xlim([0, len(test_load) / 4])

# Third subplot is Charging Action(kW) and State of Charge (kWh) vs time (hr)
ax3 = fig.add_subplot(3, 1, 3)
(line1,) = ax3.plot(hrs, storage_energy_delta, color=colors[1])
(line2,) = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel("hour"), ax3.set_ylabel("Battery action")
ax3.legend([line1, line2], ["Charging action (kW)", "SOC (kWh)"])

if matplotlib.get_backend() != "agg":
    plt.show()
else:
    print(
        "Warning: Unable to show plot with AGG backend. See "
        "https://matplotlib.org/stable/users/explain/figure/backends.html for more information."
    )
    figure_filename = "btm_battery_example_result.png"
    print(f"-> Saving figure to file '{figure_filename}' instead.")
    plt.savefig(figure_filename)


# print(optimiser.get_objective_value())
# network.draw(with_labels=True)
# network.print_network_hierarchy()
# df = optimiser.df()
# df1 = optimiser.df_by_node()
# df1.plot()
# plt.show()
# df2 = optimiser.df_by_port()
# df2.plot()
# plt.show()
