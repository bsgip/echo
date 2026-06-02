import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from pyomo.util.infeasible import log_infeasible_constraints

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import (
    ElectricalDemand,
    ElectricalGeneration,
    ElectricalStorage,
    Inverter,
)
from echo.models.prebuilt import DieselGenerator
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import ImportTariff
from echo.optimiser import optimise

"""
            Example of optimising a behind operation of a stand alone power system

             our graph is going to look like

                   connection_point----|----load
                                       |----diesel generator
                                       |----inverter----|----battery
                                                        |----pv

"""

# set up seaborn the way you like
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

# Define an Example Optimisation Problem

# The load and pv arrays below are in average kw consumed per 15 minutes
# define load (loads must be positive values)
data_df = pd.read_csv("examples/data.csv")
test_load = 5 * data_df["load"].to_numpy()

# convert solar generation to negative to match convention.
test_pv = -1 * 5 * data_df["solar"].to_numpy()

# Optimise this Example

np.set_printoptions(suppress=True)

# Set up optimisation parameters
time_periods = len(test_load)  # number of time periods to run the optimisation for
interval_duration = 15  # each time period is 15 mins long
expansion_periods = 1  # not yet implemented leave as 1
discount_rate = 0  # not yet implemented leave as 0

# Create graph in echo
system = OptimisationGraph()

# Create assets
connection_point = TellegenNode(node_name="cp")  # create the connection point
connection_point.add_ports_from_list(["load", "inv", "diesel_gen"], FlexPort, units=Units.KW)

load = Node(node_name="load")  # create a node to represent the load
l1 = ElectricalDemand()  # create an electrical demand to attach to this node
l1.add_demand_profile_from_array(test_load, expansion_periods)
load.ports["load"] = l1  # add the electrical demand to a port of the load node

# create an inverter node with some properties,
# if the constraints are not none then they should be max_export <= 0 <= max_import
# can also set efficiency on the dc and the ac side in the range 0-1
inverter = Inverter(
    node_name="inv",
    max_import=None,
    max_export=None,
    dc_ac_efficiency=1,
    ac_dc_efficiency=1,
)
inverter.add_ac_port("inv")  # add a port that is used to connect back to the connection_point
inverter.add_dc_port("bess")  # add a port to connect to the battery
inverter.add_dc_port("pv")  # add a port to connect to the pv

# create a node for the battery
battery = Node(node_name="battery")
# create an electrical storage object
b = ElectricalStorage(
    max_capacity=15.0,  # max capacity of battery in kwh
    depth_of_discharge_limit=0,  # allowable depth of discharge in range [0,100] (i.e. percent)
    charging_power_limit=15,  # max charging rate in kW
    discharging_power_limit=-15,  # max discharging rate in kW
    charging_efficiency=1,  # charging efficiency in range [0,1]
    discharging_efficiency=1,  # discharging efficiency in range [0,1]
    initial_state_of_charge=15,
)  # initial state of charge in kWh
# connect the electrical storage to a port on the battery node
battery.ports["bess"] = b

# create a node for the solar
solar = Node(node_name="solar")
pv = ElectricalGeneration()  # create an electrical generation object
pv.curtailable = True  # set whether this can be curtailed or not
pv.add_generation_profile_from_array(test_pv, expansion_periods)
solar.ports["pv"] = pv  # add the electrical generation to a port on the solar node

# add diesel generator node
diesel_gen = DieselGenerator(max_output=-5, min_output=-5 * 0.3, startup_efficiency=0.5)
# diesel_supply = Node(node_name="diesel_supply")
# diesel_supply.add_flex_port(name="diesel",unit=Units.LPS)


# Populate graph with assets (nodes)
system.add_node_obj([battery, load, solar, connection_point, inverter, diesel_gen])

# Add edges to graph (i.e. connect up the graph structure how we want it)
# system.connect_ports_and_create_edge(grid.ports['grid'], connection_point.ports['grid'])
system.connect_ports_and_create_edge(connection_point.ports["load"], load.ports["load"])
system.connect_ports_and_create_edge(connection_point.ports["inv"], inverter.ports["inv"])
system.connect_ports_and_create_edge(inverter.ports["bess"], battery.ports["bess"])
system.connect_ports_and_create_edge(inverter.ports["pv"], solar.ports["pv"])
system.connect_ports_and_create_edge(diesel_gen.ports["output"], connection_point.ports["diesel_gen"])

# Create objectives/tariffs
diesel_cost = ImportTariff(
    component=diesel_gen.ports["input"],
    tariff_array=[1] * time_periods,
    expansion_periods=expansion_periods,
)

objective_set = ObjectiveSet(objective_list=[diesel_cost])

# Invoke the optimiser and optimise
optimise_results = optimise(
    scenario_settings=ScenarioSettings(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=discount_rate,
    ),
    engine_settings=engine_settings_from_environment(),
    graph=system,
    verbose=True,
)

log_infeasible_constraints(optimise_results.model)

# Analyse the Optimisation

storage_energy_delta = optimise_results.values(b.port_name, 0)
storage_energy_soc = optimise_results.values(b.soc_value, 0)
# grid_supply = optimiser.values(connection_point.ports['grid'].port_name, 0)
diesel_power = optimise_results.values(connection_point.ports["diesel_gen"].port_name, 0)
curtailed_solar = optimise_results.values(solar.ports["pv"].port_name, 0)
diesel_use_lps = optimise_results.values(diesel_gen.ports["input"].port_name, 0)
# optimised_connection_point_load = optimise_results.values(connection_point.ports['grid'].port_name, 0)

colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(3, 1, 1)
(line1,) = ax1.plot(hrs, test_load, color=colors[0])
(line2,) = ax1.plot(hrs, test_pv, color=colors[1])
(line3,) = ax1.plot(hrs, curtailed_solar, color=colors[2])
ax1.set_xlabel("hour"), ax1.set_ylabel("kW")
ax1.legend([line1, line2, line3], ["Load", "PV", "curtailed PV"], ncol=2)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(3, 1, 2)
# line1, = ax2.plot(hrs, grid_supply)
(line1,) = ax2.plot(hrs, diesel_power)
ax2.legend([line1], ["diesel"], ncol=1)

ax3 = fig.add_subplot(3, 1, 3)
(line1,) = ax3.plot(hrs, storage_energy_delta, color=colors[1])
(line2,) = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel("hour"), ax3.set_ylabel("Battery action")
ax3.legend([line1, line2], ["Charging action (kW)", "SOC (kWh)"])
plt.show()
