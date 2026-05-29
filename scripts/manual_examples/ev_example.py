"""

Example of electric vehicle optimisation, using evs with V0G, V1G, and V2G charge modes.

"""

from __future__ import division

import pprint

import matplotlib.pyplot as plt
import numpy as np
from pyomo.util.infeasible import log_infeasible_constraints

from echo.configuration import Units
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import OptimisationGraph
from echo.models.electrical import EVV0G, EVV1G, EVV2G, EVWithProfile
from echo.models.prebuilt import FlexElectricalNode
from echo.models.scenario import ScenarioSettings, engine_settings_from_environment
from echo.optimiser import optimise

## Set up hyper params
time_periods = 48  # number of time periods to run the optimisation for
interval_duration = 30  # each time period is 15 mins long
expansion_periods = 1  # not yet implemented leave as 1
discount_rate = 0  # not yet implemented leave as 0

# Create graph
system = OptimisationGraph()

# Create an infinite grid node with one downstream port
grid = FlexElectricalNode(port_name="grid")

# Create a connection point (zero sum) node with ports for our three EVs
connection_point = TellegenNode()
connection_point.add_ports_from_list(
    ["grid", "ev_v0g", "ev_v1g", "ev_v2g", "ev_with_profile"], FlexPort, units=Units.KW
)

# Create V0G vehicle
ev_v0g_available = [1] * 24 + [0] * 24  # bool when at charger
ev_v0g_usage = [0.0] * 24 + [5] * 24  # kw average during use

ev_v0g = EVV0G(
    available=ev_v0g_available,
    usage=ev_v0g_usage,
    connection_port_name="cp",
    max_capacity=40,
    depth_of_discharge_limit=0,
    charging_power_limit=10,
    discharging_power_limit=-1e4,
    charging_efficiency=1,
    discharging_efficiency=1,
    initial_state_of_charge=20,
    soc_conserv=None,
    soc_conserv_cost=0.0,
    interval_duration=interval_duration,
    tod_charging=None,
    trip_slack=True,
)

# Create V1G vehicle
ev_v1g_available = np.array([1] * 24 + [0] * 24)  # bool when at charger
ev_v1g_usage = np.array([0.0] * 24 + [5] * 24)  # kw average during use

ev_v1g = EVV1G(
    available=ev_v1g_available,
    usage=ev_v1g_usage,
    connection_port_name="cp",
    max_capacity=40,
    depth_of_discharge_limit=0,
    charging_power_limit=10,
    discharging_power_limit=-1e4,
    charging_efficiency=1,
    discharging_efficiency=1,
    initial_state_of_charge=0,
    soc_conserv=None,
    soc_conserv_cost=0.0,
    interval_duration=interval_duration,
    tod_charging=False,
    trip_slack=True,
)

# Create a V2G vehicle
ev_v2g_available = np.array([1] * 24 + [0] * 24)  # bool when at charger
ev_v2g_usage = np.array([0.0] * 24 + [2] * 24)  # kw average during use

ev_v2g = EVV2G(
    available=ev_v2g_available,
    usage=ev_v2g_usage,
    connection_port_name="cp",
    max_capacity=40,
    depth_of_discharge_limit=0,
    charging_power_limit=10,
    discharging_power_limit=-1e4,
    charging_efficiency=1,
    discharging_efficiency=1,
    initial_state_of_charge=20,
    soc_conserv=[30] * 20 + [10] * 28,
    soc_conserv_cost=1.0,
    interval_duration=interval_duration,
    tod_charging=False,
    trip_slack=False,
    set_stateful_attrs_at_init=True,
)

# Create a EVWithProfile
ev_with_profile = EVWithProfile(
    port_name="cp",
    charging_power_limit=10,
    set_stateful_attrs_at_init=True,
    demand=[5] * 24 + [0] * 12 + [9] * 12,
)

system.add_node_obj([grid, ev_v0g, ev_v1g, ev_v2g, ev_with_profile, connection_point])

# Create edge objects and add to graph
system.connect_ports_and_create_edge(grid.ports["grid"], connection_point.ports["grid"])
system.connect_ports_and_create_edge(
    connection_point.ports["ev_v0g"], ev_v0g.ports["cp"]
)
system.connect_ports_and_create_edge(
    connection_point.ports["ev_v1g"], ev_v1g.ports["cp"]
)
system.connect_ports_and_create_edge(
    connection_point.ports["ev_v2g"], ev_v2g.ports["cp"]
)
system.connect_ports_and_create_edge(
    connection_point.ports["ev_with_profile"], ev_with_profile.ports["cp"]
)

############################ ----------------------- ########################################

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
)

log_infeasible_constraints(optimise_results.model)

############################ Analyse the Optimisation ########################################
ev_cp = ev_v0g

print("EV V0G NODE ATTRIBUTES:")
pprint.pprint(vars(ev_cp))
print("\n OPTIMISATION RESULTS: ")
print(optimise_results.node_values(ev_cp, 0))
print("EV soc: ", optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0))
print("Infeasibility: ", optimise_results.values(ev_cp.ports["vehicle"].trip_slack, 0))

plt.plot(usage)
plt.plot(optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0))
plt.plot(optimise_results.values(ev_cp.ports["vehicle"].trip_slack, 0))
plt.legend(["Usage", "EV soc", "infeasibility"])
plt.xlim([0, 47])
plt.show()

ev_cp = ev_v1g

print("EV V1G NODE ATTRIBUTES:")
pprint.pprint(vars(ev_cp))
print("\n OPTIMISATION RESULTS: ")
print(optimise_results.node_values(ev_cp, 0))
print("EV soc: ", optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0))
print("Infeasibility: ", optimise_results.values(ev_cp.ports["vehicle"].trip_slack, 0))

plt.plot(usage)
plt.plot(optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0))
plt.plot(optimise_results.values(ev_cp.ports["vehicle"].trip_slack, 0))
plt.legend(["Usage", "EV soc", "infeasibility"])
plt.xlim([0, 47])
plt.show()

ev_cp = ev_v2g

print("EV V2G NODE ATTRIBUTES:")
pprint.pprint(vars(ev_cp))
print("\n OPTIMISATION RESULTS: ")
print(optimise_results.node_values(ev_cp, 0))
print("EV soc: ", optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0))
print("Infeasibility: ", optimise_results.values(ev_cp.ports["vehicle"].trip_slack, 0))

plt.plot(usage)
plt.plot(optimise_results.values(ev_cp.ports["vehicle"].soc_value, 0))
plt.plot(optimise_results.values(ev_cp.ports["vehicle"].trip_slack, 0))
plt.legend(["Usage", "EV soc", "infeasibility"])
plt.xlim([0, 47])
plt.show()
