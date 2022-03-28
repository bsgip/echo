import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from echo_models import *
from echo_optimiser import EchoOptimiser
from configuration import *
from objectives import *

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
peak_window = [0]*14 + [1]*4 + [0]*16 + [1]*6 + [0]*8

peak_charge = DemandCharge(rate=peak_rate, window_array=peak_window, min_demand=0.0)

# shoulder usage
shoulder_rate = 1.0
shoulder_window = [0]*18 + [1]*16 + [0]*6 + [1]*4 + [0]*4

shoulder_charge = DemandCharge(rate=shoulder_rate, window_array=shoulder_window, min_demand=0.0)

# off peak usage
off_peak_rate = 0.5
off_peak_window = np.subtract(1, np.add(shoulder_window, peak_window))

off_peak_charge = DemandCharge(rate=off_peak_rate, window_array=off_peak_window, min_demand=0.0)


demand_tariff = DemandTariffObjective(component=cp1,
                                      demand_charges=[peak_charge,
                                                      shoulder_charge,
                                                      off_peak_charge],
                                      excess_demand_charge=0.0,
                                      off_peak_demand_charge=0.0)

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
line1, = ax2.plot(hrs, np.multiply(peak_window,peak_rate), color=colors[0])
line2, = ax2.plot(hrs, np.multiply(shoulder_window,shoulder_rate), color=colors[1])
line3, = ax2.plot(hrs, np.multiply(off_peak_window,off_peak_rate), color=colors[2])

ax2.set_xlabel('hour'), ax2.set_ylabel('price')
ax2.legend([line1, line2, line3], ['peak', 'shoulder', 'off peak'])
ax2.set_xlim([0, 24])

ax3 = fig.add_subplot(2, 1, 2)
line1, = ax3.plot(hrs, storage_energy_delta, color=colors[1])
line2, = ax3.plot(hrs, storage_energy_soc, color=colors[2])
ax3.set_xlim([0, 24])
ax3.set_xlabel('hour'), ax3.set_ylabel('Battery action')
ax3.legend([line1, line2], ['Charging action (kW)', 'SOC (kWh)'])
