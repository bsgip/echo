import os

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import OptimisationGraph
from echo.models.prebuilt import Battery, FlexNode, Load
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import DemandTariffObjective, ImportDemandCharge, ThroughputCost
from echo.optimiser import optimise

SOLVER = os.environ.get("OPTIMISER_ENGINE", "cplex")
SOLVER_EXECUTABLE = None

########## DEFINE MODEL OPTIONS ##################

expansion_periods = 1
time_periods = 48
interval_duration = 30

########## DEFINE MODEL ##################

system = OptimisationGraph()

grid = FlexNode(node_name="grid", port_name="grid", port_unit=Units.KW)

battery = Battery(
    node_name="battery",
    port_name="battery",
    max_capacity=10,
    depth_of_discharge_limit=0,
    charging_power_limit=2.0,
    discharging_power_limit=-2.0,
    charging_efficiency=1,
    discharging_efficiency=1,
    initial_state_of_charge=0.0,
)

load = Load(node_name="load", port_name="load", port_unit=Units.KW, profile=[2] * time_periods)

site = TellegenNode()
site.add_ports_from_list(["cp", "load", "battery"], FlexPort, units=Units.KW)

system.add_node_obj([grid, battery, load, site])

system.connect_ports_and_create_edge(grid.ports["grid"], site.ports["cp"])
system.connect_ports_and_create_edge(battery.ports["battery"], site.ports["battery"])
system.connect_ports_and_create_edge(load.ports["load"], site.ports["load"])

########## DEFINE TARIFFS ##################

# peak usage
peak_rate = 2.0
peak_window = [0] * 14 + [1] * 4 + [0] * 16 + [1] * 6 + [0] * 8

peak_charge = ImportDemandCharge(rate=peak_rate, window_array=peak_window, min_demand=0.0)

# shoulder usage
shoulder_rate = 1.0
shoulder_window = [0] * 18 + [1] * 16 + [0] * 6 + [1] * 4 + [0] * 4

shoulder_charge = ImportDemandCharge(rate=shoulder_rate, window_array=shoulder_window, min_demand=0.0)

# off peak usage
off_peak_rate = 0.5
off_peak_window = np.subtract(1, np.add(shoulder_window, peak_window))

off_peak_charge = ImportDemandCharge(rate=off_peak_rate, window_array=off_peak_window, min_demand=0.0)

demand_tariff = DemandTariffObjective(
    component=site.ports["cp"], demand_charges=[peak_charge, shoulder_charge, off_peak_charge]
)

throughput_cost = ThroughputCost(component=battery.ports["battery"], rate=0.0001)
objective_set = ObjectiveSet(objective_list=[demand_tariff, throughput_cost])

optimise_results = optimise(
    scenario_settings=ScenarioSettings(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
    ),
    engine_settings=engine_settings_from_environment(),
    graph=system,
    objective_set=objective_set,
    verbose=True,
)

# Retrieve some useful port objects
b = battery.ports["battery"]
cp = site.ports["cp"]

storage_energy_delta = optimise_results.values(b.port_name, 0)
max_demand_peak = optimise_results.values(peak_charge.max_demand_val, 0)
storage_energy_soc = optimise_results.values(b.soc_value, 0)
optimised_connection_point_load = optimise_results.values(cp.port_name, 0)

colors = sns.color_palette()
hrs = np.arange(0, 48) / 2
fig = plt.figure(figsize=(14, 7))
ax2 = fig.add_subplot(2, 1, 1)
(line1,) = ax2.plot(hrs, np.multiply(peak_window, peak_rate), color=colors[0])
(line2,) = ax2.plot(hrs, np.multiply(shoulder_window, shoulder_rate), color=colors[1])
(line3,) = ax2.plot(hrs, np.multiply(off_peak_window, off_peak_rate), color=colors[2])

ax2.set_xlabel("hour"), ax2.set_ylabel("price")
ax2.legend([line1, line2, line3], ["peak", "shoulder", "off peak"])
ax2.set_xlim([0, 24])

ax3 = fig.add_subplot(2, 1, 2)
(line1,) = ax3.plot(hrs, storage_energy_delta, color=colors[1])
(line2,) = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, 24])
ax3.set_xlabel("hour"), ax3.set_ylabel("Battery action")
ax3.legend([line1, line2], ["Charging action (kW)", "SOC (kWh)"])
plt.show()
