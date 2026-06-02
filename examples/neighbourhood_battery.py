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
)
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import PathTariff, ThroughputCost
from echo.optimiser import optimise

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
test_load = data_df["load"].to_numpy()

# convert solar generation to negative to match convention.
test_pv = -1 * 2 * data_df["solar"].to_numpy()

# Tariffs are in $ / kwh
remote_energy_tariff = np.array(([0.1] * 28 + [0.25] * 8 + [0.1] * 32 + [0.25] * 16 + [0.1] * 12))
remote_transport_import = np.array([0.15] * 96)
local_energy_tariff = remote_energy_tariff
# local_energy_tariff = np.array(([0.1] * 28 + [0.2] * 8 + [0.0] * 32 + [0.2] * 16 + [0.1] * 12))
local_transport_import = np.array([0.05] * 96)

remote_transport_export = np.array([0.0] * 96)
local_transport_export = np.array([0.0] * 96)

import_tariff_array = np.array(([0.1] * 28 + [0.3] * 8 + [0.2] * 32 + [0.3] * 16 + [0.1] * 12))
export_tariff_array = np.array(([0.0] * 96))

# Optimise this Example

np.set_printoptions(suppress=True)

# Set up optimisastion parameters
time_periods = len(test_load)
interval_duration = 15
expansion_periods = 1
discount_rate = 0

# Create graph
system = OptimisationGraph()

# Create assets
grid = Node()
grid.add_port("grid", FlexPort(units=Units.KW))

connection_point = TellegenNode()
connection_point.add_ports_from_list(["load", "bess", "pv", "grid"], FlexPort, units=Units.KW)

load = Node()
l1 = ElectricalDemand()
l1.add_demand_profile_from_array(test_load, expansion_periods)
load.ports["load"] = l1

battery = Node()
b = ElectricalStorage(
    max_capacity=15.0,
    depth_of_discharge_limit=0,
    charging_power_limit=1.25,
    discharging_power_limit=-1.25,
    charging_efficiency=1,
    discharging_efficiency=1,
    initial_state_of_charge=0.0,
)
battery.ports["bess"] = b

solar = Node()
pv = ElectricalGeneration()
pv.curtailable = False
pv.add_generation_profile_from_array(test_pv, expansion_periods)
solar.ports["pv"] = pv

# Populate graph with assets (nodes)
system.add_node_obj([grid, battery, load, solar, connection_point])

# Add edges to graph
system.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
system.connect_ports_and_create_edge(connection_point.ports["load"], load.ports["load"])
system.connect_ports_and_create_edge(connection_point.ports["bess"], battery.ports["bess"])
system.connect_ports_and_create_edge(connection_point.ports["pv"], solar.ports["pv"])

# Generate path objects from graph representation
system.create_path_objects(sources=[grid, battery, solar], sinks=[grid, battery, load])

# Create objectives/tariffs
# Retrieve paths
grid_to_bess = system.get_path([grid, connection_point, battery])
bess_to_grid = system.get_path([battery, connection_point, grid])
bess_to_load = system.get_path([battery, connection_point, load])
grid_to_load = system.get_path([grid, connection_point, load])
solar_to_load = system.get_path([solar, connection_point, load])
solar_to_bess = system.get_path([solar, connection_point, battery])
solar_to_grid = system.get_path([solar, connection_point, grid])

# Construct tariffs per path

# Cost for customers with solar (1)
cws = [
    PathTariff(
        component=grid_to_load,
        tariff_array=remote_energy_tariff + remote_transport_import,
    ),
    PathTariff(
        component=bess_to_load,
        tariff_array=local_energy_tariff + local_transport_import,
    ),
    PathTariff(
        component=solar_to_grid,
        tariff_array=(remote_energy_tariff - remote_transport_export) * -1,
    ),
    PathTariff(
        component=solar_to_bess,
        tariff_array=(local_energy_tariff - local_transport_export) * -1,
    ),
]

# Cost for storage operator
cstorage = [
    PathTariff(
        component=solar_to_bess,
        tariff_array=local_energy_tariff + local_transport_import,
    ),
    PathTariff(
        component=bess_to_grid,
        tariff_array=(local_energy_tariff - local_transport_export) * -1,
    ),
    PathTariff(
        component=grid_to_bess,
        tariff_array=remote_energy_tariff + remote_transport_import,
    ),
    PathTariff(
        component=bess_to_grid,
        tariff_array=(remote_energy_tariff - remote_transport_export) * -1,
    ),
]

# Revenue for network operator
rnetwork = [
    PathTariff(component=grid_to_load, tariff_array=remote_transport_import),
    PathTariff(component=grid_to_bess, tariff_array=remote_transport_import),
    PathTariff(component=bess_to_load, tariff_array=local_transport_import),
    PathTariff(component=solar_to_bess, tariff_array=local_transport_import),
    PathTariff(component=solar_to_load, tariff_array=local_transport_import),
    PathTariff(component=solar_to_grid, tariff_array=remote_transport_export),
    PathTariff(component=bess_to_grid, tariff_array=remote_transport_export),
    PathTariff(component=bess_to_load, tariff_array=local_transport_export),
    PathTariff(component=solar_to_bess, tariff_array=local_transport_export),
    PathTariff(component=solar_to_load, tariff_array=local_transport_export),
]

throughput_cost = ThroughputCost(component=b, rate=0.000001)

objective_set = ObjectiveSet(objective_list=cws + cstorage + rnetwork + [throughput_cost])

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
optimised_connection_point_load = optimise_results.values(connection_point.ports["grid"].port_name, 0)

optimise_results.get_single_objective_total_value(rnetwork[0])
optimise_results.get_single_objective_total_value(throughput_cost)

colors = sns.color_palette()
hrs = np.arange(0, len(test_load)) / 4
fig = plt.figure(figsize=(14, 7))
ax1 = fig.add_subplot(3, 1, 1)
(line1,) = ax1.plot(hrs, test_load, color=colors[0])
(line2,) = ax1.plot(hrs, test_pv, color=colors[1])
(line3,) = ax1.plot(hrs, optimised_connection_point_load, color=colors[2])
ax1.set_xlabel("hour"), ax1.set_ylabel("kW")
ax1.legend([line1, line2, line3], ["Load", "PV", "Connection Point"], ncol=3)
ax1.set_xlim([0, len(test_load) / 4])

ax2 = fig.add_subplot(3, 1, 2)
(line1,) = ax2.plot(hrs, remote_energy_tariff, color=colors[0])
(line2,) = ax2.plot(hrs, remote_transport_import, color=colors[1])
(line3,) = ax2.plot(hrs, remote_transport_export, color=colors[2])
(line4,) = ax2.plot(hrs, local_energy_tariff, color=colors[3])
(line5,) = ax2.plot(hrs, local_transport_import, color=colors[4])
(line6,) = ax2.plot(hrs, local_transport_export, color=colors[5])

ax2.set_xlabel("hour"), ax2.set_ylabel("price")
ax2.legend(
    [line1, line2, line3, line4, line5, line6],
    ["re", "rt+", "rt-", "le", "lt+", "lt-"],
    ncol=2,
)
ax2.set_xlim([0, len(test_load) / 4])

ax3 = fig.add_subplot(3, 1, 3)
(line1,) = ax3.plot(hrs, storage_energy_delta, color=colors[1])
(line2,) = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, len(test_load) / 4])
ax3.set_xlabel("hour"), ax3.set_ylabel("Battery action")
ax3.legend([line1, line2], ["Charging action (kW)", "SOC (kWh)"])
plt.show()
