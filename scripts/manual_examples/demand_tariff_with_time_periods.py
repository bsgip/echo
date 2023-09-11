from datetime import datetime, time

import pandas as pd

from echo.configuration import Units
from echo.echo_optimiser import EchoOptimiser
from echo.models.agnostic import FlexPort, TellegenNode
from echo.models.base import Node, OptimisationGraph
from echo.models.electrical import ElectricalDemand, ElectricalStorage
from echo.objectives.base import ObjectiveSet
from echo.objectives.tariff import (
    Day,
    DemandTariffObjective,
    ImportDemandCharge,
    ResetPeriod,
    ThroughputCost,
    TimePeriod,
    Window,
)

expansion_periods = 1
profile = pd.DataFrame(
    index=pd.date_range(start=datetime(2021, 1, 4), end=datetime(2021, 1, 11), freq="30min", closed="left")
)

time_periods = len(profile)
interval_duration = 30

system = OptimisationGraph()

grid = Node()
grid.add_port("grid", FlexPort(units=Units.KW))

battery1 = Node()
b1 = ElectricalStorage(
    max_capacity=15.0,
    depth_of_discharge_limit=0,
    charging_power_limit=2.0,
    discharging_power_limit=-2.0,
    charging_efficiency=1,
    discharging_efficiency=1,
    initial_state_of_charge=0.0,
)
battery1.ports["battery"] = b1

load1 = Node()
l1 = ElectricalDemand()

l1.add_demand_profile_from_array([10] * time_periods, expansion_periods)
load1.ports["demand"] = l1

site1 = TellegenNode()
site1.add_ports_from_list(["cp", "load", "bess"], FlexPort, units=Units.KW)
cp1 = site1.ports["cp"]

system.add_node_obj([grid, battery1, load1, site1])

system.connect_ports_and_create_edge(grid.ports["grid"], cp1)
system.connect_ports_and_create_edge(site1.ports["bess"], b1)
system.connect_ports_and_create_edge(site1.ports["load"], l1)


# peak usage
peak_window_new = Window(
    time_periods=[TimePeriod(start_time=time(18, 0), end_time=time(21, 0), day_type=[Day.weekday, Day.weekend])],
    reset_periods=ResetPeriod.day,
)

peak_charge = ImportDemandCharge(
    name="peak",
    rate=10.0,
    window_array=peak_window_new.to_bool_periods(profile),
    min_demand=0.0,
    reset_periods=peak_window_new.get_reset_period_array(profile),
)

demand_tariff = DemandTariffObjective(component=cp1, demand_charges=[peak_charge])

throughput_cost = ThroughputCost(component=b1, rate=0.0001)
objective_set = ObjectiveSet(objective_list=[demand_tariff, throughput_cost])


optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=objective_set,
    profile=profile,
)

optimiser.optimise()
print(optimiser.opt_status)

print(optimiser.values(peak_charge.max_demand_val))

# print(optimiser.values(b1.port_name))
#
# plt.plot(optimiser.values(cp1.port_name))
# plt.plot(peak_charge.window_array+10)
# plt.show()
# plt.legend(['demand', 'active demand periods'])
