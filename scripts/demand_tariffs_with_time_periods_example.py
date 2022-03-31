import numpy as np
import matplotlib.pyplot as plt
import pandas
import pandas as pd
import seaborn as sns

from echo_models import *
from echo_optimiser import EchoOptimiser
from configuration import *
from objectives import *
from datetime import datetime, time

import os

SOLVER = os.environ.get('OPTIMISER_ENGINE','cplex')
SOLVER_EXECUTABLE = None

expansion_periods = 1
time_periods = 48
interval_duration = 30

system = OptimisationGraph()

grid = Node()
grid.add_named_electrical_ports(['grid'])

battery1 = Node()
b1 = ElectricalStorage(max_capacity=10,
                       depth_of_discharge_limit=0,
                       charging_power_limit=2.0,
                       discharging_power_limit=-2.0,
                       charging_efficiency=1,
                       discharging_efficiency=1,
                       initial_state_of_charge=0.0)
battery1.ports['battery'] = b1

load1 = Node()
l1 = ElectricalDemand()
l1.add_demand_profile_from_array([2] * time_periods, expansion_periods)
load1.ports['demand'] = l1

site1 = ElectricalTellegenNode()
site1.add_named_electrical_ports(['cp', 'load', 'bess'])
cp1 = site1.ports['cp']

system.add_node_obj([grid, battery1, load1, site1])

bess_edge1 = Edge(vertices=[site1.ports['bess'], b1])
load_edge1 = Edge(vertices=[site1.ports['load'], l1])
grid_edge = Edge(vertices=[cp1, grid.ports['grid']])

system.add_edge_obj([bess_edge1, load_edge1, grid_edge])

# peak usage
peak_rate = 2.0

peak_window = Window(time_periods=[
    TimePeriod(start_time=time(7, 0), end_time=time(9, 0), day_type=[Day.weekday, Day.weekend]),
    TimePeriod(start_time=time(17, 0), end_time=time(19, 0), day_type=[Day.weekend])
])

peak_charge = DemandCharge(rate=peak_rate, window=peak_window, min_demand=0.0)

df = pd.DataFrame(index=pd.date_range(start=datetime(2021, 1, 1), end=datetime(2021, 1, 2), inclusive='left', freq='30min'))

demand_tariff = ImportDemandTariffObjective(component=cp1,
                                            demand_charges=[peak_charge],
                                            df=df)

throughput_cost = ThroughputCost(component=b1, rate=0.0001)
objective_set = ObjectiveSet(objective_list=[demand_tariff, throughput_cost])

optimiser = EchoOptimiser(
    interval_duration=interval_duration,
    number_of_intervals=time_periods,
    number_of_expansion_intervals=expansion_periods,
    discount_rate=0,
    ES=system,
    objective_set=objective_set
)

optimiser.optimise()


storage_energy_delta = optimiser.values(b1.port_name, 0)
storage_energy_soc = optimiser.values(b1.soc_value, 0)
optimised_connection_point_load = optimiser.values(site1.ports['cp'].port_name, 0)

colors = sns.color_palette()
hrs = np.arange(0, 48) / 2
fig = plt.figure(figsize=(14, 7))
ax2 = fig.add_subplot(2, 1, 1)
line1, = ax2.plot(hrs, np.multiply(optimiser.values(peak_charge.window_active,0),peak_rate), color=colors[0])

ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([line1], ['peak'])
ax2.set_xlim([0, 23])

ax3 = fig.add_subplot(2, 1, 2)
line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, 23])
ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])

